"""Warn at the start of a command when the branch lacks commits of its remote; the commits that changed a file since a version."""

import functools
import hashlib
import os
import re
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
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, start_new_session=True, env=env, encoding="utf-8", errors="replace")


def behind(root: Path) -> dict | None:
    """Fetch, then how far the current branch is behind its upstream: None when it is not. An install without git: by
    GitHub's feed (`updates.behind`)."""
    if not (root / ".git").exists():
        from volleyball_stats import updates

        return updates.behind(root)
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
    ahead, late = (int(n) for n in counts.stdout.split())
    return {"branch": branch, "upstream": upstream.stdout.strip(), "behind": late, "ahead": ahead} if late else None


def behind_warning(root: Path) -> str | None:
    """`behind`'s warning for the terminal."""
    state = behind(root)
    if not state:
        return None
    n = state["behind"]
    diverged = f" and {state['ahead']} ahead" if state["ahead"] else ""
    return f"Warning: {state['branch']} is {n} commit{'s' if n > 1 else ''} behind {state['upstream']}{diverged}: run git pull --rebase."


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


# A commit's subject as the late page's tip shows it: without its type ("feat: ") nor its details (after "; ", " (" or ": ",
# not a French " : " which a quoted text of the page may hold).
SUBJECT_TYPE, SUBJECT_DETAILS = re.compile(r"^\w+(\([^)]*\))?!?: "), re.compile(r"; | \(|(?<! ): ")


def short_subject(subject: str) -> str:
    """`subject` without its type nor its details (SUBJECT_TYPE, SUBJECT_DETAILS)."""
    return SUBJECT_DETAILS.split(SUBJECT_TYPE.sub("", subject.strip()), maxsplit=1)[0]


@functools.cache
def commits_since(path: Path, since: str, now: str) -> list[tuple[int, str]] | None:
    """The commits that changed `path` after its version whose content's sha256 starts with `since`, newest first, by time and
    short subject; `now` its stamp today, for the cache. None when git cannot tell (no history, that version not in it)."""
    try:
        log = _git(path.parent, "log", "--format=%x00%ct %s", "--raw", "--no-abbrev", "--", path.name)
        entries = []
        for chunk in log.stdout.split("\0")[1:] if log.returncode == 0 else []:
            head, *raw = chunk.strip().split("\n")
            when, _, subject = head.partition(" ")
            entries.append((int(when), subject, next((line.split()[3] for line in raw if line.startswith(":")), None)))
        blobs = [blob for *_, blob in entries if blob and blob.strip("0")]
        out = subprocess.run(["git", "-C", str(path.parent), "cat-file", "--batch"], input="\n".join(blobs).encode() + b"\n", capture_output=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None
    stamps, at = {}, 0
    while (end := out.find(b"\n", at)) != -1:
        oid, _, size = out[at:end].decode().partition(" blob ")
        if not size:
            break
        content = out[end + 1 : end + 1 + int(size)]
        # A checkout may turn the line ends into Windows' ones.
        stamps[oid] = {hashlib.sha256(text).hexdigest()[:16] for text in (content, content.replace(b"\n", b"\r\n"))}
        at = end + 1 + int(size) + 1
    found = []
    for when, subject, blob in entries:
        if since in stamps.get(blob, ()):
            return found
        found.append((when, short_subject(subject)))
    return None
