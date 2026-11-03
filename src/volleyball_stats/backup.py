"""A dated copy of what cannot be made again (the review's answers, names and comments, the match's
results, the courts, the viewers' reports, the sponsors) on the hosting server, outside its website.
Files unchanged since the copy before take no room. The video is too big for that server.

    uv run python -m volleyball_stats.backup outputs/2026-10-29-aspom-1-vs-aspom-2

Restore: rsync -rt -e "ssh -i KEY" root@HOST:/root/backups/volleyball-stats/DAY/2026-10-29-aspom-1-vs-aspom-2/ outputs/2026-10-29-aspom-1-vs-aspom-2/
"""

import argparse
import fnmatch
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from volleyball_stats import matches

ROOT = "/root/backups/volleyball-stats"
# Old copies of the results, the pages built from them (the review's links the video), half-written files.
SKIP = ("backup-*", "review", "site", "films", "photo_moments", ".*.tmp")
SPONSORS = Path("branding/aspom/sponsors")
KEEP = 30
# Under this, no copy: the server also runs the owner's websites.
MIN_FREE_GB = 5
TIMEOUT_S = 3600
# rsync: a file vanished while it read the folder (the review writing); the next copy takes it.
VANISHED = 24
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def sources(match: Path) -> list[Path]:
    """What is copied, each landing under its name: the match's folder and what sits beside it."""
    outputs = match.parent
    found = [match, outputs / "courts", outputs / "roster.json", outputs / "lens.json", SPONSORS, *sorted(outputs.glob("feedback*.log"))]
    return [p for p in found if p.exists()]


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


def stale(days: list[str], keep: int = KEEP) -> list[str]:
    """The copies of `days` to remove: all but the last `keep`."""
    return sorted(days)[: -keep or None] if len(days) > keep else []


def rsync_command(paths: list[Path], host: str, ssh: list[str], root: str, day: str, previous: str | None) -> list[str]:
    """Today's copy from `paths`, linking to the `previous` one's files that did not change."""
    return [
        "rsync", "-rt", "--delete", *[f"--exclude={p}" for p in SKIP], "-e", " ".join(ssh),
        *([f"--link-dest={root}/{previous}"] if previous else []),
        *map(str, paths), f"{host}:{root}/{day}/",
    ]  # fmt: skip


def backup(match: Path, day: str | None = None, root: str = ROOT) -> None:
    """Copies `match` to the server of its publish.json; raises what went wrong."""
    config = json.loads((match / matches.PUBLISH).read_text())
    host, ssh = config["upload"].split(":")[0], ["ssh", "-i", str(Path(config["key"]).expanduser()), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    day = day or time.strftime("%Y-%m-%d")

    def remote(command: str) -> str:
        return subprocess.run([*ssh, host, command], check=True, capture_output=True, text=True, timeout=60).stdout

    # Only root reads the folder: it holds real names and pictures.
    found = remote(f"mkdir -p {root} && chmod 700 {root} && df -Pk {root} | tail -1 && ls -1 {root}").splitlines()
    free_gb = int(found[0].split()[3]) / 1024**2
    if free_gb < MIN_FREE_GB:
        raise RuntimeError(f"only {free_gb:.1f} GB free on the server")
    days = sorted(d for d in found[1:] if DAY.fullmatch(d))
    previous = next((d for d in reversed(days) if d != day), None)
    run = subprocess.run(rsync_command(sources(match), host, ssh, root, day, previous), capture_output=True, text=True, timeout=TIMEOUT_S)
    if run.returncode not in (0, VANISHED):
        raise RuntimeError(run.stderr.strip() or f"rsync: {run.returncode}")
    old = stale(sorted({*days, day}))
    if old:
        remote("rm -rf " + " ".join(f"{root}/{d}" for d in old))


def rename_copies(match: Path, old: str, root: str = ROOT) -> None:
    """The copies of the match `old`, now `match`, under its new name, for the next copy to link to their files; none without a
    publish.json, which backups need."""
    path = match / matches.PUBLISH
    if not path.exists():
        return
    config = json.loads(path.read_text())
    ssh = ["ssh", "-i", str(Path(config["key"]).expanduser()), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", config["upload"].split(":")[0]]
    subprocess.run([*ssh, rename_command(root, old, match.name)], check=True, capture_output=True, text=True, timeout=120)


def rename_command(root: str, old: str, new: str) -> str:
    """The shell command moving each dated copy's folder `old` to `new`."""
    return f"for d in {shlex.quote(root)}/*/; do if [ -d \"$d\"{shlex.quote(old)} ] && [ ! -e \"$d\"{shlex.quote(new)} ]; then mv \"$d\"{shlex.quote(old)} \"$d\"{shlex.quote(new)}; fi; done"


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy what cannot be made again to the hosting server.")
    parser.add_argument("match", type=Path)
    backup(parser.parse_args().match)
    print("backed up", flush=True)


if __name__ == "__main__":
    main()
