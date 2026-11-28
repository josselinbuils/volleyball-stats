"""The code's version and its update. A git checkout: git's. An install without git (the installers'): GitHub's archive of
the branch, its commit and its files kept in INSTALLED, the commits since read from the branch's feed (no API: its
limit is per address, a club's network shares it).

The standard library only, nothing of the package imported at the top: the installers run this file alone before the
code is there.

    python updates.py install DIR    # the code in DIR, or brought up to date
"""

import functools
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO, BRANCH = "josselinbuils/volleyball-stats", "main"
ARCHIVE = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
FEED = f"https://github.com/{REPO}/commits/{BRANCH}.atom"
INSTALLED = ".install.json"
# The feed's commits seen within this long are not asked again.
FEED_TTL = 600
AGENT = {"User-Agent": "volleyball-stats"}
_feed: tuple[float, list[str]] | None = None


def git(root: Path) -> bool:
    return (root / ".git").exists()


def installed(root: Path) -> dict | None:
    """INSTALLED's commit and files, None in a git checkout or a copy the installers did not make."""
    try:
        found = json.loads((root / INSTALLED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("commit") else None


def commit(root: Path) -> str | None:
    """The code's commit: git's HEAD, else INSTALLED's; None when neither says."""
    if git(root):
        try:
            run = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return None
        return run.stdout.strip() or None if run.returncode == 0 else None
    found = installed(root)
    return found["commit"] if found else None


@functools.cache
def tls() -> ssl.SSLContext:
    """The system's root certificates and Mozilla's (certifi, when installed): a Windows holds only the roots it fetched
    for its own connections, so Python alone can miss GitHub's."""
    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return context
    context.load_verify_locations(certifi.where())
    return context


def get(url: str, timeout: float = 30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout, context=tls())


def feed() -> list[str]:
    """The branch's last commits (20), newest first; kept FEED_TTL."""
    global _feed
    if _feed and time.time() - _feed[0] < FEED_TTL:
        return _feed[1]
    with get(FEED, 15) as answer:
        found = re.findall(r"Commit/([0-9a-f]{40})", answer.read().decode("utf-8", "replace"))
    _feed = (time.time(), found)
    return found


def behind(root: Path) -> dict | None:
    """How far an install without git is behind the branch, as `git_check.behind` says it: None when it is not or
    cannot tell (offline). Past the feed's commits, the feed's count."""
    found = installed(root)
    if not found:
        return None
    try:
        commits = feed()
    except OSError:
        return None
    late = commits.index(found["commit"]) if found["commit"] in commits else len(commits)
    return {"branch": BRANCH, "upstream": "github", "behind": late, "ahead": 0} if late else None


def newer(sent: str, here: str) -> bool:
    """Whether commit `sent` is newer than `here`, for an install without git: by their places in the feed; one past it
    is older than those in it, two past it cannot tell (False)."""
    try:
        commits = feed()
    except OSError:
        return True
    place = {c: i for i, c in enumerate(commits)}
    if sent in place and here in place:
        return place[sent] < place[here]
    return sent in place


def download(url: str, to: Path, told=None) -> None:
    """`url` into `to`, `told(done, total)` as it comes (total None when the server does not say)."""
    with get(url, 60) as answer, open(to, "wb") as out:
        total = int(answer.headers.get("Content-Length") or 0) or None
        done = 0
        while chunk := answer.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if told:
                told(done, total)


def install(root: Path, archive: Path | None = None) -> str:
    """The branch's code in `root` from its archive (downloaded unless `archive`): its files written, those an older
    install brought and this one has not removed, INSTALLED written last. Its commit. Refused in a git checkout."""
    root = root.resolve()
    if git(root):
        raise RuntimeError(f"{root} is a git checkout: git pull updates it")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix=".update-") as work:
        if archive is None:
            archive = Path(work) / "code.zip"
            download(ARCHIVE, archive)
        with zipfile.ZipFile(archive) as z:
            sha = z.comment.decode("ascii", "replace").strip()
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise RuntimeError("the archive names no commit")
            entries = [i for i in z.infolist() if not i.is_dir()]
            prefix = os.path.commonprefix([i.filename for i in entries]).rpartition("/")[0] + "/"
            files = []
            for info in entries:
                name = info.filename[len(prefix) :]
                path = (root / name).resolve()
                if root not in path.parents or name == INSTALLED:
                    raise RuntimeError(f"the archive holds a file out of place: {info.filename}")
                files.append(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = Path(work) / "file"
                with z.open(info) as source, open(temporary, "wb") as out:
                    shutil.copyfileobj(source, out)
                mode = info.external_attr >> 16
                if os.name != "nt" and mode & 0o111:
                    temporary.chmod(0o755)
                replace(temporary, path)
    before = installed(root)
    for name in sorted(set((before or {}).get("files", [])) - set(files)):
        gone = root / name
        gone.unlink(missing_ok=True)
        for folder in gone.parents:
            if folder == root or any(folder.iterdir()):
                break
            folder.rmdir()
    (root / f"{INSTALLED}.new").write_text(json.dumps({"commit": sha, "files": sorted(files)}) + "\n", encoding="utf-8")
    replace(root / f"{INSTALLED}.new", root / INSTALLED)
    return sha


def replace(source: Path, target: Path) -> None:
    """`os.replace`, retried a moment while another process holds `target` (Windows)."""
    for attempt in range(20):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 19:
                raise
            time.sleep(0.25)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "install":
        sys.exit(__doc__.split("\n\n")[-1])
    print(f"Code {install(Path(sys.argv[2]))[:7]} in {sys.argv[2]}", flush=True)
