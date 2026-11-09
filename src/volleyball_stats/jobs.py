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
import time
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
    job.update(pid=process.pid, pidStarted=started_at(process.pid))
    update(record, pid=job["pid"], pidStarted=job["pidStarted"])
    return job


def update(record: Path, **fields) -> None:
    job = json.loads(record.read_text())
    job.update(fields)
    files.write_text(record, json.dumps(job, indent=1))


def started_at(pid: int) -> str | None:
    """When the process `pid` started, as `ps` tells it: another process given the same number later starts later."""
    try:
        found = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return found or None


def alive(pid: int | None, since: str | None = None) -> bool:
    """Whether the process `pid` runs, and is the one started at `since` when given (a restart reuses numbers)."""
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
    return since is None or started_at(pid) == since


def running(job: dict) -> bool:
    return "ended" not in job and alive(job.get("pid"), job.get("pidStarted"))


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
