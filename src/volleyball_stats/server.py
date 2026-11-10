"""The hosting server, set in the app's "Serveur" tab: its address, the site's folder there, the ssh key and the public
address, in outputs/server.json (sync.SERVER), which every match's publish.json follows. The matches go online there,
and the backups go there too (backup.py).
"""

import json
import re
import shlex
import subprocess
from pathlib import Path

from volleyball_stats import backup, files, matches, sync

# Where this machine builds the hosted site before uploading it.
SITE = "outputs/hosted"
ADDRESS = re.compile(r"[\w.-]+@[\w.-]+")
URL = re.compile(r"https?://\S+")


def read(outputs: Path) -> dict | None:
    """The server as the tab shows it."""
    found = sync.server(outputs)
    if not found:
        return None
    address, _, folder = found["upload"].partition(":")
    return {"address": address, "folder": folder, "key": found["key"], "url": found.get("url", "")}


def save(outputs: Path, body: dict) -> None:
    """The server the tab sent, in server.json and every match's publish.json; ValueError for one it cannot reach."""
    address, folder, key, url = (str(body.get(k) or "").strip() for k in ("address", "folder", "key", "url"))
    if not ADDRESS.fullmatch(address) or not folder.startswith("/") or not key or (url and not URL.fullmatch(url)):
        raise ValueError("server")
    hosting = {"upload": f"{address}:{folder.rstrip('/')}/", "key": key, "url": url and url.rstrip("/") + "/", "site": SITE}
    files.write_text(outputs / sync.SERVER, json.dumps(hosting, indent=2) + "\n")
    for path in sorted((outputs / "matches").glob(f"*/{matches.PUBLISH}")):
        given = json.loads(path.read_text())
        matches.update_publish(path.parent, **{k: v for k, v in hosting.items() if v and (k != "site" or not given.get("site"))})


def ssh(found: dict, command: str, timeout: float = 30) -> str:
    """`command` run on the server; RuntimeError with its reason."""
    host, connect = backup.connection(found)
    try:
        run = subprocess.run([*connect, host, command], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("timeout") from error
    if run.returncode:
        raise RuntimeError((run.stderr.strip().splitlines() or [f"ssh: {run.returncode}"])[-1])
    return run.stdout


def test(outputs: Path) -> None:
    """Whether the server answers and holds the site's folder; RuntimeError with the reason."""
    found = connected(outputs)
    folder = found["upload"].partition(":")[2]
    if ssh(found, f"test -d {shlex.quote(folder)} || echo missing").strip() == "missing":
        raise RuntimeError(f"missing:{folder}")


# Each day's own bytes, those no other copy shares (what removing it frees), then the whole backups' kB.
SIZES = "; echo ::sizes; for d in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/; do [ -d \"$d\" ] && printf '%s ' \"${d%/}\" && find \"$d\" -type f -links 1 -printf '%s\\n' | awk '{s+=$1} END {print s+0}'; done; du -sk . | cut -f1"


def connected(outputs: Path) -> dict:
    found = sync.server(outputs)
    if not found:
        raise LookupError("server")
    return found


def copies(outputs: Path, root: str = backup.ROOT) -> dict:
    """The backups on the server: its free and used room, how many copies it keeps, then each day's copy
    newest first with its matches, its own size and the matches it holds the newest copy of (it cannot be removed)."""
    text = ssh(connected(outputs), backup.listing(root) + SIZES)
    listed, _, sized = text.partition("::sizes\n")
    free_gb, settings, days = backup.listed(listed)
    *rows, used_kb = sized.strip().split("\n")
    sizes = {day: int(size) for day, size in (row.split() for row in rows)}
    last = backup.newest(days)
    return {
        "free": round(free_gb, 1),
        "used": int(used_kb) * 1024,
        "keep": backup.kept(settings),
        "days": [{"day": d, "matches": sorted(days[d]), "size": sizes.get(d, 0), "newest": sorted(m for m, n in last.items() if n == d)} for d in sorted(days, reverse=True)],
    }


def delete(outputs: Path, day: str, root: str = backup.ROOT) -> None:
    """The day's copy removed from the server; PermissionError when it holds a match's newest copy, the one a pull brings."""
    if not backup.DAY.fullmatch(day):
        raise ValueError(day)
    found = connected(outputs)
    _, _, days = backup.listed(ssh(found, backup.listing(root)))
    if day not in days:
        raise LookupError(day)
    if day in backup.newest(days).values():
        raise PermissionError(day)
    ssh(found, f"rm -rf {shlex.quote(f'{root}/{day}')}")


def keep(outputs: Path, count: int, apply: bool, root: str = backup.ROOT) -> list[str]:
    """The days keeping `count` copies (and each match's newest) removes; with `apply`, the count shared and those days
    removed."""
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 365:
        raise ValueError("keep")
    found = connected(outputs)
    _, _, days = backup.listed(ssh(found, backup.listing(root)))
    removed = backup.stale(days, count)
    if apply:
        sync.share_settings(found, {"keep": count})
        if removed:
            ssh(found, "rm -rf " + " ".join(shlex.quote(f"{root}/{d}") for d in removed))
    return removed
