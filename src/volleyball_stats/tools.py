"""ffmpeg where the system has none, on Windows and macOS: one version on every machine the app installs it on (VERSION),
its builds' files checked by their sha256, kept in DIR and put first on the PATH at the package's import. Linux has its
system's (apt).

    python -m volleyball_stats.tools    # fetches it (Diagnostics' download does, with the models)
"""

import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

VERSION = "9.1"
DIR = Path.home() / ".local/share/volleyball-stats/ffmpeg"
BIN = DIR / "bin"
# Windows: Gyan's full build (its .7z through Windows' tar, its .zip where that tar cannot: Windows 10); macOS:
# Martin Riedl's, ffmpeg and ffprobe apart. Both GPL (x264), with libx264 and libsvtav1, NVENC on Windows, VideoToolbox
# on Apple chips.
GYAN = "https://github.com/GyanD/codexffmpeg/releases/download/9.1/ffmpeg-9.1-full_build"
RIEDL = "https://ffmpeg.martin-riedl.de/download/macos"
BUILDS = {
    ("windows", "amd64"): [
        [(f"{GYAN}.7z", "1a86f2c8b51b4990ae9a0b0f8bd4f345f5c79389d293ac3fda128a58ec507b16")],
        [(f"{GYAN}.zip", "f9a83be8f97b8989a223a15e4af234accd0842bacf7c126af5a3aae759785e48")],
    ],
    ("mac", "arm64"): [
        [
            (f"{RIEDL}/arm64/1795207104_9.1/ffmpeg.zip", "1f66e9a690a7f1c9e60b012379f8869c11818d1797f45b21dbb2f2564ba61ae1"),
            (f"{RIEDL}/arm64/1795207104_9.1/ffprobe.zip", "6ef2df5f575042923a28537ab37adf936f28bf3e7b85de23a1447ed447ec1dbd"),
        ]
    ],
    ("mac", "x86_64"): [
        [
            (f"{RIEDL}/amd64/1795212433_9.1/ffmpeg.zip", "35b3d82cccc2c1d644d49d15f5e57eb913a08ef68f798042c90eecec62c51f1e"),
            (f"{RIEDL}/amd64/1795212433_9.1/ffprobe.zip", "41ca7b7cba7992e33f1da3f1bf54db8ec103a4d387b1bfac3162062e8b1074ad"),
        ]
    ],
}
PROGRAMS = ("ffmpeg", "ffprobe")


def add_to_path() -> None:
    """DIR's programs before the system's."""
    if BIN.is_dir() and str(BIN) not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}"


def build() -> list[list[tuple[str, str]]] | None:
    """This machine's build, as ways to get it (each its files), None where the app installs none."""
    from volleyball_stats import doctor

    return BUILDS.get((doctor.system(), platform.machine().lower() if os.name == "nt" else platform.machine()))


def fetchable() -> bool:
    return build() is not None


def version() -> str | None:
    """The ffmpeg on the PATH's version ("9.1", "6.1.1": a build's label after it dropped), None without one."""
    program = shutil.which("ffmpeg")
    if not program:
        return None
    try:
        out = subprocess.run([program, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.match(r"ffmpeg version n?(\d+(?:\.\d+)*)?(\S*)", out)
    return (found.group(1) or found.group(2)) if found else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def unpack(archive: Path, into: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    else:
        subprocess.run(["tar", "-xf", str(archive), "-C", str(into)], check=True, capture_output=True, stdin=subprocess.DEVNULL)


def fetch(told=None) -> None:
    """This machine's build in BIN, `told(share)` by its bytes; RuntimeError when none fits or it cannot be got."""
    from volleyball_stats import files, updates

    ways = build()
    if not ways:
        raise RuntimeError(f"no ffmpeg build for this system ({platform.system()} {platform.machine()})")
    DIR.mkdir(parents=True, exist_ok=True)
    error = None
    for way in ways:
        with tempfile.TemporaryDirectory(dir=DIR, prefix=".fetch-") as work:
            work = Path(work)
            try:
                for n, (url, digest) in enumerate(way):
                    archive = work / url.rsplit("/", 1)[1]
                    updates.download(url, archive, told and (lambda done, total, n=n, of=len(way): told((n + done / total) / of) if total else None))
                    if sha256(archive) != digest:
                        raise RuntimeError(f"{archive.name}: not the expected file")
                    unpack(archive, work / "out")
            except (OSError, RuntimeError, subprocess.CalledProcessError) as failed:
                error = failed
                continue
            BIN.mkdir(exist_ok=True)
            suffix = ".exe" if os.name == "nt" else ""
            for program in PROGRAMS:
                found = next((work / "out").rglob(program + suffix), None)
                if found is None:
                    raise RuntimeError(f"{program} missing from the build")
                found.chmod(0o755)
                files.replace(found, BIN / (program + suffix))
            add_to_path()
            return
    raise RuntimeError(f"ffmpeg could not be downloaded: {error}")


if __name__ == "__main__":
    fetch(lambda share: print(f"{share:.0%}", flush=True))
    print(f"ffmpeg {version()} in {BIN}", flush=True)
