"""The app's long work, one job per match: commands run one after the other in a process of their own, apart from the
server's, so that a job outlives the server switching matches or stopping. Each job is a record in `outputs/jobs/`
(`ID.json`) and its output (`ID.log`); the runner writes there how it ended.

    python -m volleyball_stats.jobs outputs/jobs/ID.json   # the runner, started by `start`
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from volleyball_stats import files

FOLDER = "jobs"
# A line of a command's output telling its progress (0-1) or its stage (match.STAGE).
PROGRESS, STAGE = "::progress ", "::stage "
# ffmpeg's -stats line: how far it went in the output.
FFMPEG_TIME = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
TAIL_BYTES = 64 << 10
# A job's id, a file name in FOLDER.
JOB_ID = re.compile(r"[\w.-]+")


# How often a job's Stages tell the share done, and the most of a stage's share told before it ends.
TELL_EVERY_S, STAGE_CAP = 1.0, 0.95


class Stages:
    """A command's stages told as it goes, for the app's job: `::stage KIND K/N` ("match 2/5": the second of five
    "match:NAME" stages of the `plan`, `::stage KIND` for one alone), then every TELL_EVERY_S the share done, from each
    stage's last duration on this machine kept in `path`, else its kind's in `took`. `plan` may change as it goes. Not
    `told`, it only keeps the durations."""

    def __init__(self, path: Path, plan: list[str], took: dict[str, float], told: bool = True):
        self.path, self.plan, self.told = path, plan, told
        try:
            self.took = {**took, **json.loads(path.read_text())}
        except (OSError, ValueError):
            self.took = dict(took)
        self.key, self.done, self.since = None, 0.0, time.time()
        self.stopped = threading.Event()
        if told:
            threading.Thread(target=self.tell, daemon=True).start()

    def expected(self, key: str) -> float:
        return self.took.get(key, self.took.get(key.split(":")[0], 0.0))

    def share(self) -> float:
        now = min(time.time() - self.since, STAGE_CAP * self.expected(self.key or ""))
        return min(1.0, (self.done + now) / max(sum(self.expected(k) for k in self.plan), 1.0))

    def tell(self) -> None:
        while not self.stopped.wait(TELL_EVERY_S):
            if self.key:
                print(f"{PROGRESS}{self.share():.3f}", flush=True)

    def start(self, key: str | None) -> None:
        """The stage `key` of the plan starts, the last one's duration kept; None: the command ends."""
        now = time.time()
        if self.key:
            self.took[self.key] = now - self.since
            self.done += self.took[self.key]
            files.write_text(self.path, json.dumps(self.took, indent=1) + "\n")
        self.key, self.since = key, now
        if key is None:
            self.stopped.set()
        if key is None or not self.told:
            return
        kind = key.split(":")[0]
        alike = [k for k in self.plan if k.split(":")[0] == kind]
        print(f"{STAGE}{kind}{f' {alike.index(key) + 1}/{len(alike)}' if ':' in key and key in alike else ''}", flush=True)
        print(f"{PROGRESS}{self.share():.3f}", flush=True)


class Running(RuntimeError):
    """The job asked for still runs."""


def folder(outputs: Path) -> Path:
    return outputs / FOLDER


def record_of(outputs: Path, job_id: str) -> Path:
    """The record of the job `job_id`; ValueError for an id that is no file name of FOLDER."""
    if not JOB_ID.fullmatch(job_id) or job_id.strip(".") == "":
        raise ValueError(job_id)
    return folder(outputs) / f"{job_id}.json"


def is_running(outputs: Path, job_id: str) -> bool:
    record = record_of(outputs, job_id)
    return record.exists() and running(json.loads(record.read_text()))


def start(outputs: Path, job_id: str, kind: str, steps: list[tuple[str, list[str]]], **extra) -> dict:
    """Starts the `steps` (name, command arguments after `python -m`) one after the other; Running when the job
    `job_id` still runs."""
    record = record_of(outputs, job_id)
    record.parent.mkdir(parents=True, exist_ok=True)
    jobs = record.parent
    if is_running(outputs, job_id):
        raise Running(job_id)
    job = {"id": job_id, "kind": kind, "steps": [{"name": n, "args": a} for n, a in steps], "started": time.time(), **extra}
    files.write_text(record, json.dumps(job, indent=1))
    log = open(jobs / f"{job_id}.log", "w")
    process = subprocess.Popen(
        [sys.executable, "-m", "volleyball_stats.jobs", str(record)],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    log.close()
    job.update(pid=process.pid, pidStarted=started_at(process.pid), pidKey=process_key(process.pid))
    update(record, pid=job["pid"], pidStarted=job["pidStarted"], pidKey=job["pidKey"])
    return job


def update(record: Path, **fields) -> None:
    job = json.loads(record.read_text())
    job.update(fields)
    files.write_text(record, json.dumps(job, indent=1))


# `ps` tells a process's start from the clock at boot plus its age: a clock set again (WSL2 after a sleep or a resync,
# 9 s on 13 Nov) moves it. Starts this close are one process; a number reused after a restart starts much later.
START_SLACK_S = 300
LSTART = "%a %b %d %H:%M:%S %Y"


def started_at(pid: int) -> str | None:
    """When the process `pid` started, as `ps` tells it: another process given the same number later starts later."""
    try:
        found = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return found or None


def process_key(pid: int) -> str | None:
    """Where the system tells it (Linux, WSL2), the process `pid` exactly: the boot's id and its start in ticks since
    the boot, which no clock change moves; None elsewhere (macOS: `started_at` only)."""
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        ticks = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None
    return f"{boot}:{ticks}"


def same_start(now: str | None, since: str) -> bool:
    """Whether two of `ps`'s start times are one process's, the clock set again in between (START_SLACK_S)."""
    if now is None:
        return False
    try:
        return abs((datetime.strptime(" ".join(now.split()), LSTART) - datetime.strptime(" ".join(since.split()), LSTART)).total_seconds()) <= START_SLACK_S
    except ValueError:
        return now == since


def alive(pid: int | None, since: str | None = None, key: str | None = None) -> bool:
    """Whether the process `pid` runs, and is the one started at `since` (`ps`'s time) or known as `key`
    (`process_key`) when given: a restart reuses numbers."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A child of this process that ended stays a zombie until waited for.
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            return False
    except ChildProcessError:
        pass
    found = process_key(pid) if key else None
    if found:
        return found == key
    return since is None or same_start(started_at(pid), since)


def running(job: dict) -> bool:
    return "ended" not in job and alive(job.get("pid"), job.get("pidStarted"), job.get("pidKey"))


def tail(path: Path) -> str:
    """The end of a log, each line as it last showed (ffmpeg rewrites its own with \\r)."""
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        f.seek(max(0, path.stat().st_size - TAIL_BYTES))
        text = f.read().decode(errors="replace")
    return "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))


def progress(text: str, total_s: float | None = None) -> tuple[float | None, str | None]:
    """The last progress (0-1) and stage a log tells; ffmpeg's time over `total_s` for a copy."""
    found, stage = None, None
    for line in text.split("\n"):
        if line.startswith(PROGRESS):
            found = float(line.removeprefix(PROGRESS))
        elif line.startswith(STAGE):
            stage, found = line.removeprefix(STAGE).strip(), None
    if total_s:
        times = FFMPEG_TIME.findall(text.replace("\r", "\n"))
        if times:
            h, m, s = times[-1]
            found = min(1.0, (int(h) * 3600 + int(m) * 60 + float(s)) / total_s)
    return found, stage


def error_of(text: str) -> str | None:
    """The line saying why a command failed: its last one."""
    lines = [line.strip() for line in text.split("\n") if line.strip() and not line.startswith(("::", "frame=", "size="))]
    return lines[-1] if lines else None


def state(outputs: Path) -> list[dict]:
    """Every job as the app shows it: running, done or failed (with its step and error), its progress and stage."""
    found = []
    for record in sorted(folder(outputs).glob("*.json")):
        try:
            job = json.loads(record.read_text())
        except (OSError, ValueError):
            continue
        text = tail(record.with_suffix(".log"))
        job["running"] = running(job)
        if not job["running"] and "ended" not in job:
            job.update(ended=job.get("started"), failed=job.get("step"), error="interrupted")
        if job["running"]:
            job["progress"], job["stage"] = progress(text, job.get("total") if job.get("step") == job["steps"][0]["name"] else None)
        elif job.get("failed") and not job.get("error"):
            job["error"] = error_of(text)
        job.pop("steps")
        found.append(job)
    return found


def stop(outputs: Path, job_id: str) -> None:
    """Stops a running job and the commands it started."""
    record = record_of(outputs, job_id)
    job = json.loads(record.read_text())
    if running(job):
        try:
            os.killpg(job["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        update(record, ended=time.time(), failed=job.get("step"), error="stopped")


def forget(outputs: Path, job_id: str) -> None:
    record = record_of(outputs, job_id)
    for path in (record, record.with_suffix(".log")):
        path.unlink(missing_ok=True)


def run(record: Path) -> None:
    """The runner: each step in turn, stopping at the first that fails."""
    job = json.loads(record.read_text())
    for step in job["steps"]:
        update(record, step=step["name"], stepStarted=time.time())
        code = subprocess.run([sys.executable, "-m", *step["args"]], stdin=subprocess.DEVNULL).returncode
        if code:
            update(record, ended=time.time(), failed=step["name"], code=code)
            return
    update(record, ended=time.time(), step=None)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
