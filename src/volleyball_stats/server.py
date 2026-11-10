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
    found = sync.server(outputs)
    if not found:
        raise LookupError("server")
    folder = found["upload"].partition(":")[2]
    if ssh(found, f"test -d {shlex.quote(folder)} || echo missing").strip() == "missing":
        raise RuntimeError(f"missing:{folder}")


def copies(outputs: Path, root: str = backup.ROOT) -> dict:
    """The backups on the server: its free room, then each day's copy newest first with its matches."""
    found = sync.server(outputs)
    if not found:
        raise LookupError("server")
    free_gb, days = backup.listed(ssh(found, backup.listing(root)))
    return {"free": round(free_gb, 1), "days": [{"day": d, "matches": sorted(days[d])} for d in sorted(days, reverse=True)]}
