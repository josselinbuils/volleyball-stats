"""Copies of what cannot be made again (the review's answers, names and comments, the match's results, and beside the
matches the courts and their clicks, the roster, the lens, the club the app edits, the viewers' reports) on the hosting
server, outside its website: ROOT/COPY/MATCH/ and ROOT/COPY/<what sits beside>, a copy per hour something changed
(`copy_id`). A copy starts as the one before hard-linked on the server (`snapshot`), so each holds every match while only
what changed is uploaded and takes room. A match's files replace the copy's (`--delete`); what sits beside the matches is
shared by the machines, each file the newest of both and none removed (`--update`). The last KEEP copies are kept (or
as many as the server's settings.json says), and each match's newest however old. Each machine keeps how its last copy
went in outputs/backup_state.json (`state`). The video is too big for that server.

    uv run python -m volleyball_stats.backup outputs/matches/2026-10-29-aspom-1-vs-aspom-2

goes through `sync.push`, as the app does. The app's "Serveur" tab restores a match or what sits beside the matches from
any copy (`server.restore`).
"""

import argparse
import fnmatch
import json
import os
import re
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path

from volleyball_stats import files, matches

ROOT = "/root/backups/volleyball-stats"
# Old copies of the results, the pages built from them (the review's links the video), half-written files, the review's
# marker of a page waiting for its pictures (review.STALE_PHOTOS), made and removed as it builds. The films go (a few MB each):
# a machine that pulls the match gets them, and its upload keeps them online.
# Per machine (`sync`): the server's version of the match this machine's copy started from.
STATE = ".sync.json"
SKIP = ("backup-*", "review", "site", "photo_moments", ".*.tmp", "photos_stale", STATE)
# What sits beside the matches in the outputs folder, copied with each match and on its own (`backup_shared`).
SHARED = ("courts", "court", "roster.json", "lens.json", "club", "feedback")
REMOTE = Path(__file__).with_name("backup_remote.py")
# How this machine's last copies went.
STATE_FILE = "backup_state.json"
KEEP = 30
# Under this, no copy: the server also runs the owner's websites.
MIN_FREE_GB = 5
TIMEOUT_S = 3600
# rsync: a file vanished while it read the folder (the review writing); the next copy takes it. The Mac's openrsync says it
# as a file it could not open.
VANISHED = 24
# A copy's name: its day, and its hour since copies are hourly (the daily ones before have none).
COPY = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2})?")


def vanished(stderr: str) -> bool:
    lines = [line for line in stderr.splitlines() if line.strip()]
    return bool(lines) and all("No such file or directory" in line for line in lines)


def copy_id(now: float | None = None) -> str:
    """The copy a backup made now goes into: one per hour, the later backups of that hour updating it."""
    return time.strftime("%Y-%m-%dT%H", time.localtime(now))


def shared(outputs: Path) -> list[Path]:
    return [outputs / name for name in SHARED if (outputs / name).exists()]


def sources(match: Path) -> list[Path]:
    """What is copied, each landing under its name: the match's folder and what sits beside it."""
    return [match, *shared(files.root(match))]


def signature(paths: list[Path]) -> tuple[int, float]:
    """The number of files copied from `paths` and the latest time one changed: any change moves it."""
    count, latest = 0, 0.0
    skipped = lambda name: any(fnmatch.fnmatch(name, p) for p in SKIP)  # noqa: E731
    for path in paths:
        for folder, dirs, names in os.walk(path) if path.is_dir() else [(str(path.parent), [], [path.name])]:
            dirs[:] = [d for d in dirs if not skipped(d)]
            for name in names:
                if not skipped(name) and not os.path.islink(os.path.join(folder, name)):
                    count += 1
                    latest = max(latest, os.path.getmtime(os.path.join(folder, name)))
    return count, latest


def newest(held: dict[str, set[str]]) -> dict[str, str]:
    """Each match's newest copy, by name: the one a pull brings."""
    return {name: day for day in sorted(held) for name in held[day]}


def stale(held: dict[str, set[str]], keep: int = KEEP) -> list[str]:
    """The copies of `held` (each copy's matches) to remove: those neither among the last `keep` nor holding a match's
    newest copy, a match nobody copies for a while keeping its last one."""
    days = sorted(held)
    kept = set(days[-keep:]) | set(newest(held).values())
    return [d for d in days if d not in kept]


def listing(root: str) -> str:
    """The server's command telling its free room, the settings the machines share, then its copies and their matches
    (`listed`); only root reads them: they hold real names and pictures."""
    return (
        f"mkdir -p {root} && chmod 700 {root} && df -Pk {root} | tail -1 && (cat {root}/settings.json 2>/dev/null || echo '{{}}') | tr -d '\\n'"
        f" && echo && cd {root} && ls -1d */ */*/source.json 2>/dev/null; true"
    )


def listed(text: str) -> tuple[float, dict, dict[str, set[str]]]:
    """The free GB, the shared settings and each copy's matches, from `listing`'s output."""
    lines = text.splitlines()
    return int(lines[0].split()[3]) / 1024**2, json.loads(lines[1] or "{}"), held("\n".join(lines[2:]))


def kept(settings: dict) -> int:
    """How many copies the server keeps, besides each match's newest: its settings' `keep`, else KEEP."""
    keep = settings.get("keep")
    return keep if isinstance(keep, int) and keep >= 1 else KEEP


def held(listing: str) -> dict[str, set[str]]:
    """Each copy's matches, from the server's `ls -1d COPY/ COPY/MATCH/source.json` lines."""
    found: dict[str, set[str]] = {}
    for line in listing.splitlines():
        parts = line.strip().strip("/").split("/")
        if parts and COPY.fullmatch(parts[0]):
            found.setdefault(parts[0], set())
            if len(parts) == 3 and parts[2] == "source.json":
                found[parts[0]].add(parts[1])
    return found


def snapshot(host: str, ssh: list[str], root: str, day: str, previous: str) -> None:
    """The copy `day` started on the server as the `previous` one, hard-linked (backup_remote.py): nothing uploaded, no
    room taken."""
    command = "python3 - " + " ".join(shlex.quote(a) for a in (root, day, previous))
    subprocess.run([*ssh, host, command], input=REMOTE.read_text(), check=True, capture_output=True, text=True, timeout=600)


def rsync_command(paths: list[Path], host: str, ssh: list[str], root: str, day: str, merge: bool = False) -> list[str]:
    """The copy `day` from `paths`, only the files changed since the copy it started as going up, put in place together
    at the end (`--delay-updates`: a copy cut off keeps its files as they were). A match's files replace the copy's;
    with `merge` (what sits beside the matches, shared by the machines) each file goes up only if newer, none removed."""
    return [
        "rsync", "-rt", "--delay-updates", *(["--update"] if merge else ["--delete"]), *[f"--exclude={p}" for p in SKIP],
        "-e", " ".join(ssh), *map(str, paths), f"{host}:{root}/{day}/",
    ]  # fmt: skip


def state(outputs: Path) -> dict:
    """How this machine's last copies went: `at` the last made, `error` why the last one failed (None when it went),
    `shared` the signature of what sits beside the matches as last sent or brought, `verified` the last check of the
    copies and `problems` what it found."""
    path = outputs / STATE_FILE
    return {"at": None, "error": None, "shared": None, "verified": None, "problems": [], **(json.loads(path.read_text()) if path.exists() else {})}


def shared_changed(outputs: Path) -> bool:
    """Whether what sits beside the matches changed here since it was last sent or brought."""
    return list(signature(shared(outputs))) != state(outputs)["shared"]


def note(outputs: Path, **changes) -> None:
    files.write_text(outputs / STATE_FILE, json.dumps({**state(outputs), **changes}) + "\n")


def backup(match: Path, root: str | None = None) -> None:
    """Copies `match` and what sits beside it to the server of its publish.json; raises what went wrong. `sync.push`
    calls it, under the match's claim."""
    root = root or ROOT
    copy(files.root(match), [match], sources(match)[1:], json.loads((match / matches.PUBLISH).read_text()), match.name, root)


def backup_shared(outputs: Path, config: dict, root: str | None = None) -> None:
    """Copies what sits beside the matches to the server of `config` (`upload`, `key`): no match needs to be open."""
    root = root or ROOT
    copy(outputs, [], shared(outputs), config, None, root)


def copy(outputs: Path, own: list[Path], beside: list[Path], config: dict, name: str | None, root: str) -> None:
    """`own` (a match's folder, its files replacing the copy's) and `beside` (merged) copied into this hour's copy, started
    as the one before; then the copies past the kept count removed. How it went noted in outputs/backup_state.json."""
    sent = list(signature(shared(outputs)))
    try:
        upload(own, beside, config, name, root)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        note(outputs, error=str(error) or type(error).__name__)
        raise
    note(outputs, at=datetime.now().isoformat(timespec="seconds"), error=None, shared=sent)


def upload(own: list[Path], beside: list[Path], config: dict, name: str | None, root: str) -> None:
    host, ssh = connection(config)
    day = copy_id()

    def remote(command: str) -> str:
        run = subprocess.run([*ssh, host, command], capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
        return run.stdout

    free_gb, settings, days = listed(remote(listing(root)))
    if free_gb < MIN_FREE_GB:
        raise RuntimeError(f"only {free_gb:.1f} GB free on the server")
    before = [d for d in sorted(days) if d < day]
    if before and day not in days:
        snapshot(host, ssh, root, day, before[-1])
        days[day] = set(days[before[-1]])
    for paths, merge in ((own, False), (beside, True)):
        if not paths:
            continue
        run = subprocess.run(rsync_command(paths, host, ssh, root, day, merge), capture_output=True, text=True, timeout=TIMEOUT_S)
        if run.returncode not in (0, VANISHED) and not vanished(run.stderr):
            raise RuntimeError(run.stderr.strip() or f"rsync: {run.returncode}")
    days.setdefault(day, set()).update([name] if name else [])
    old = stale(days, kept(settings))
    if old:
        remote("rm -rf " + " ".join(shlex.quote(f"{root}/{d}") for d in old))


def connection(config: dict) -> tuple[str, list[str]]:
    """The server's host and the ssh command reaching it, from a publish.json's `upload` and `key`."""
    return config["upload"].split(":")[0], ["ssh", "-i", str(Path(config["key"]).expanduser()), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def rename_copies(match: Path, old: str, root: str | None = None) -> None:
    """The copies of the match `old`, now `match`, under its new name, for the next copy to link to their files; none without a
    publish.json, which backups need."""
    root = root or ROOT
    path = match / matches.PUBLISH
    if not path.exists():
        return
    host, ssh = connection(json.loads(path.read_text()))
    subprocess.run([*ssh, host, rename_command(root, old, match.name)], check=True, capture_output=True, text=True, timeout=120)


def rename_command(root: str, old: str, new: str) -> str:
    """The shell command moving each copy's folder `old` to `new`, and its claim (`sync`)."""
    claims = shlex.quote(f"{root}/claims/")
    return (
        f"for d in {shlex.quote(root)}/*/; do if [ -d \"$d\"{shlex.quote(old)} ] && [ ! -e \"$d\"{shlex.quote(new)} ]; then mv \"$d\"{shlex.quote(old)} \"$d\"{shlex.quote(new)}; fi; done"
        f"; if [ -e {claims}{shlex.quote(old + '.json')} ] && [ ! -e {claims}{shlex.quote(new + '.json')} ]; then mv {claims}{shlex.quote(old + '.json')} {claims}{shlex.quote(new + '.json')}; fi"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy a match and what sits beside it to the hosting server, as the app does.")
    parser.add_argument("match", type=Path)
    from volleyball_stats import sync

    try:
        sync.push(parser.parse_args().match)
    except sync.Conflict as error:
        parser.exit(1, f"{error}: open it in the review to keep one\n")
    print("backed up", flush=True)


if __name__ == "__main__":
    main()
