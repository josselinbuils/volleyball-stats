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
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from volleyball_stats import awake, files

FOLDER = "jobs"
# A line of a command's output telling its progress (0-1) or its stage (match.STAGE).
PROGRESS, STAGE = "::progress ", "::stage "
# ffmpeg's -stats line: how far it went in the output.
FFMPEG_TIME = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
TAIL_BYTES = 64 << 10
# A job's id, a file name in FOLDER.
JOB_ID = re.compile(r"[\w.-]+")


# How often a job's Stages tell the share done.
TELL_EVERY_S = 1.0


class Stages:
    """A command's stages told as it goes, for the app's job: `::stage KIND K/N` ("match 2/5": the second of five
    "match:NAME" stages of the `plan`, `::stage KIND` for one alone), then every TELL_EVERY_S the share done of the
    whole, of the stage (`part`) and the seconds left (`told`). Only counted work moves the share (the owner's rule): the
    stage running tells its own share (`share_of_stage`, `counter`), else it holds; the stages are weighted by their last
    duration on this machine kept in `path`, else their kind's in `took`, both per unit of `scale` (the video's seconds
    for the pipeline). `plan` may change as it goes. Not `told`, it only keeps the durations; not `keep`, it keeps none (a
    run reusing what an earlier one computed, its quick stages no measure of the next full run's)."""

    def __init__(self, path: Path | None, plan: list[str], took: dict[str, float], told: bool = True, scale: float = 1.0, keep: bool = True):
        self.path, self.plan, self.told, self.scale, self.keep = path, plan, told, max(scale, 1e-9), keep
        try:
            self.took = {**took, **json.loads(path.read_text())} if path else dict(took)
        except (OSError, ValueError):
            self.took = dict(took)
        self.kept = dict(self.took)
        self.key, self.done, self.since, self.own, self.base = None, 0.0, time.time(), None, 0.0
        self.stopped = threading.Event()
        if told:
            threading.Thread(target=self.tell, daemon=True).start()

    def expected(self, key: str) -> float:
        return self.scale * self.took.get(key, self.took.get(key.split(":")[0], 0.0))

    def part(self) -> float:
        """The share done of the stage running, as it counts it; 0 until it does: the bar holds."""
        return self.own or 0.0

    def share(self) -> float:
        return min(1.0, (self.done + self.part() * self.expected(self.key or "")) / max(sum(self.expected(k) for k in self.plan), 1.0))

    def left(self) -> float:
        """Seconds left: the stage running's, from its own share's pace when it tells one, then the later stages'."""
        spent, expected = time.time() - self.since, self.expected(self.key or "")
        # The pace of the share counted since the stage started (`resumed`: not what an earlier run did).
        counted = (self.own or 0.0) - self.base
        here = spent * (1 - self.own) / counted if self.own is not None and counted > 0.01 else max(0.0, expected * (1 - self.base) - spent) if self.own is None else expected * (1 - self.base)
        later = self.plan[self.plan.index(self.key) + 1 :] if self.key in self.plan else []
        return here + sum(self.expected(k) for k in later)

    def line(self) -> str:
        part = "" if self.own is None else f"{self.own:.3f}"
        return f"{PROGRESS}{self.share():.4f} part={part} left={self.left():.0f}"

    def tell(self) -> None:
        while not self.stopped.wait(TELL_EVERY_S):
            if self.key:
                print(self.line(), flush=True)

    def share_of_stage(self, share: float) -> None:
        """The stage running tells its own share done (0-1)."""
        self.own = min(1.0, max(0.0, share))

    def resumed(self, share: float) -> None:
        """The stage running starts again from a share an earlier run did (`resume`): its bar from there, its time left
        and the duration kept from this run's own pace."""
        self.base = min(0.99, max(0.0, share))
        self.share_of_stage(self.base)

    def counter(self, total: float) -> Callable[[float], None]:
        """A tick for the stage running to count its work with: each call adds that much done of `total`."""
        done = [0.0]

        def tick(n: float = 1.0) -> None:
            done[0] += n
            self.share_of_stage(done[0] / total if total > 0 else 1.0)

        return tick

    def start(self, key: str | None) -> None:
        """The stage `key` of the plan starts, the last one's duration kept; None: the command ends."""
        now = time.time()
        if self.key:
            # The share counts it as expected, never going back; the next run expects what it took (the weights of
            # this one stay as they were, else the share would jump).
            self.done += self.expected(self.key)
            self.kept[self.key] = (now - self.since) / self.scale / (1 - self.base)
            if self.path and self.keep:
                files.write_text(self.path, json.dumps(self.kept, indent=1) + "\n")
        self.key, self.since, self.own, self.base = key, now, None, 0.0
        if key is None:
            self.stopped.set()
        if key is None or not self.told:
            return
        kind = key.split(":")[0]
        alike = [k for k in self.plan if k.split(":")[0] == kind]
        print(f"{STAGE}{kind}{f' {alike.index(key) + 1}/{len(alike)}' if ':' in key and key in alike else ''}", flush=True)
        print(self.line(), flush=True)


Share = Callable[[float], None]


def quiet(_: float) -> None:
    """A share told to nobody."""


def parts(tell: Share, weights: dict[str, float]) -> Callable[[str], Share]:
    """A step cut in parts of fixed `weights` (their share of its work, measured once), each counting its own share
    (0-1): `part(name)(share)` tells the step's share, the parts before it counted as done."""
    names, total = list(weights), sum(weights.values()) or 1.0

    def part(name: str) -> Share:
        before = sum(weights[n] for n in names[: names.index(name)])
        return lambda share: tell((before + weights[name] * min(1.0, max(0.0, share))) / total)

    return part


def every(count: int, tell: Share, step: int = 0) -> Callable[[int], None]:
    """For a loop over `count` items: `seen(k)` after the item k (0-based) tells k+1 / count, every `step` items (about
    a hundred times in all by default), and at the last one."""
    step = step or max(1, count // 100)

    def seen(k: int) -> None:
        if (k + 1) % step == 0 or k + 1 == count:
            tell((k + 1) / count)

    return seen


def tell(share: float) -> None:
    """A share told on stdout, for the process that started this one (`follow`)."""
    print(f"{PROGRESS}{share:.4f}", flush=True)


def follow(command: list[str], share: Share, **options) -> None:
    """Runs `command` (`options` as Popen's), its shares told (`tell`) passed to `share`, its other lines through;
    CalledProcessError when it fails, as `subprocess.run(check=True)`."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1, **options)
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith(PROGRESS):
            share(float(line.removeprefix(PROGRESS).split()[0]))
        else:
            sys.stdout.write(line)
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, command)


def ffmpeg(command: list[str], seconds: float, share: Share) -> subprocess.CompletedProcess:
    """Runs ffmpeg's `command` (starting "ffmpeg"), its share done told from the time it wrote over the `seconds` of
    video it writes; returns how it ended, its errors kept, as `subprocess.run(capture_output=True, text=True)`."""
    process = subprocess.Popen([command[0], "-progress", "pipe:1", "-nostats", *command[1:]], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    errors: list[str] = []
    # Read apart, else a full pipe of errors would stop ffmpeg.
    reader = threading.Thread(target=lambda: errors.extend(process.stderr), daemon=True)
    reader.start()
    assert process.stdout is not None
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and seconds > 0:
            share(min(1.0, int(value) / 1e6 / seconds))
    process.wait()
    reader.join()
    # Its last report comes before its end.
    if process.returncode == 0:
        share(1.0)
    return subprocess.CompletedProcess(command, process.returncode, "", "".join(errors))


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


# The runner's threads write its record in turn (the battery's watch beside the steps).
WRITING = threading.Lock()


def update(record: Path, **fields) -> None:
    with WRITING:
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


def told(text: str, total_s: float | None = None) -> dict:
    """What a log last tells: the share done (`progress`, 0-1), the stage, the stage's own share (`part`) and the
    seconds left (`toldLeft`) when it tells them (`Stages`); ffmpeg's time over `total_s` for a copy that tells none."""
    found: dict = {"progress": None, "stage": None}
    for line in text.split("\n"):
        if line.startswith(PROGRESS):
            share, *extra = line.removeprefix(PROGRESS).split()
            found = {"stage": found["stage"], "progress": float(share)}
            for item in extra:
                key, _, value = item.partition("=")
                if key in ("part", "left") and value:
                    found["part" if key == "part" else "toldLeft"] = float(value)
        elif line.startswith(STAGE):
            found = {"stage": line.removeprefix(STAGE).strip(), "progress": None}
    if total_s and found["progress"] is None:
        times = FFMPEG_TIME.findall(text.replace("\r", "\n"))
        if times:
            h, m, s = times[-1]
            found["progress"] = min(1.0, (int(h) * 3600 + int(m) * 60 + float(s)) / total_s)
    return found


def progress(text: str, total_s: float | None = None) -> tuple[float | None, str | None]:
    """The last progress (0-1) and stage a log tells (`told`)."""
    found = told(text, total_s)
    return found["progress"], found["stage"]


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
            job.update(told(text, job.get("total") if job.get("step") == job["steps"][0]["name"] else None))
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
    """The runner: each step in turn, stopping at the first that fails, the machine kept awake (`battery` told)."""
    job = json.loads(record.read_text())
    with awake.held(lambda on: update(record, battery=on)):
        for step in job["steps"]:
            update(record, step=step["name"], stepStarted=time.time())
            code = subprocess.run([sys.executable, "-m", *step["args"]], stdin=subprocess.DEVNULL).returncode
            if code:
                update(record, ended=time.time(), failed=step["name"], code=code)
                return
    update(record, ended=time.time(), step=None)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
