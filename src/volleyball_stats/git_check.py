"""Warn at the start of a command when the branch lacks commits of its remote."""

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Set once checked: the commands a command starts inherit it and skip the check.
CHECKED_ENV = "VOLLEYBALL_STATS_GIT_CHECKED"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # A new session has no terminal: ssh cannot stop to ask a passphrase.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, start_new_session=True, env=env)


def behind_warning(root: Path) -> str | None:
    """Fetch, then the warning when the current branch is behind its upstream."""
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "@{u}")
        if upstream.returncode != 0:
            return None
        try:
            _git(root, "fetch", "--quiet")
        except subprocess.TimeoutExpired:
            pass
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    if counts.returncode != 0:
        return None
    ahead, behind = (int(n) for n in counts.stdout.split())
    if not behind:
        return None
    diverged = f" and {ahead} ahead" if ahead else ""
    return f"Warning: {branch} is {behind} commit{'s' if behind > 1 else ''} behind {upstream.stdout.strip()}{diverged}: run git pull --rebase."


def _warn() -> None:
    message = behind_warning(ROOT)
    if message:
        if sys.stderr.isatty():
            message = f"\033[33m{message}\033[0m"
        print(message, file=sys.stderr, flush=True)


def check() -> None:
    """Check in the background once per `python -m volleyball_stats.X` command."""
    if sys.argv[:1] != ["-m"] or os.environ.get(CHECKED_ENV) or not (ROOT / ".git").exists():
        return
    os.environ[CHECKED_ENV] = "1"
    threading.Thread(target=_warn, name="git-check").start()
