"""What this machine needs to process a match, checked for the app: tools, graphics card, memory, disk, models and the
code's version. Each check gives an `id`, a `status` (ok, warn, error) and the values its text shows.

    python -m volleyball_stats.doctor            # the checks, in the terminal
    python -m volleyball_stats.doctor --models   # downloads the models missing
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from volleyball_stats import git_check, procs

# A 2-hour match: about 8 GB of RAM at its peak (docs/setup.md), its 4K video about 60 GB, twice that while it is imported.
RAM_GB, WARN_RAM_GB = 12, 16
DISK_GB, WARN_DISK_GB = 60, 150
MODELS = Path("models")


def system() -> str:
    """"mac", "windows", "wsl" or "linux"."""
    if platform.system() == "Darwin":
        return "mac"
    if platform.system() == "Windows":
        return "windows"
    try:
        return "wsl" if "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower() else "linux"
    except OSError:
        return "linux"


# winget's names of the tools.
WINGET = {"ffmpeg": "Gyan.FFmpeg", "git": "Git.Git"}


def install_command(packages: list[str]) -> str:
    kind = system()
    if kind == "windows":
        return "; ".join(f"winget install --scope user {WINGET[p]}" for p in packages)
    return f"brew install {' '.join(packages)}" if kind == "mac" else f"sudo apt install -y {' '.join(packages)}"


def tools() -> dict:
    """ffmpeg, and git in a git checkout (an install without it updates from GitHub's archive). An ffmpeg the app
    installs (Windows, macOS) comes with the models' download, no command."""
    from volleyball_stats import tools as fetched

    # Fetched since this process started (the models' download).
    fetched.add_to_path()
    needed = ("ffmpeg", "ffprobe", "git") if (git_check.ROOT / ".git").exists() else ("ffmpeg", "ffprobe")
    missing = [t for t in needed if not shutil.which(t)]
    fetch = any(t != "git" for t in missing) and fetched.fetchable()
    packages = sorted({"git" if t == "git" else "ffmpeg" for t in missing if t == "git" or not fetch})
    return {
        "id": "tools",
        "status": "error" if missing else "ok",
        "missing": missing,
        "fetch": fetch,
        "version": None if "ffmpeg" in missing else fetched.version(),
        "command": install_command(packages) if packages else None,
    }


def gpu() -> dict:
    """The device the models run on; on Linux, an NVIDIA card torch cannot use names its driver."""
    try:
        import torch
    except ImportError as error:
        return {"id": "gpu", "status": "error", "kind": "torch", "detail": str(error)}
    if torch.cuda.is_available():
        return {"id": "gpu", "status": "ok", "kind": "cuda", "name": torch.cuda.get_device_name()}
    if torch.backends.mps.is_available():
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        return {"id": "gpu", "status": "ok", "kind": "mps", "name": chip or "Apple"}
    smi = shutil.which("nvidia-smi") or ("/usr/lib/wsl/lib/nvidia-smi" if Path("/usr/lib/wsl/lib/nvidia-smi").exists() else None)
    if smi:
        return {"id": "gpu", "status": "error", "kind": "driver", "name": None}
    return {"id": "gpu", "status": "warn", "kind": "cpu", "name": None}


def memory() -> dict:
    found = procs.total_memory()
    if found is None:
        return {"id": "memory", "status": "ok", "gb": None}
    total = found / 1e9
    status = "error" if total < RAM_GB else "warn" if total < WARN_RAM_GB else "ok"
    return {"id": "memory", "status": status, "gb": round(total), "wsl": system() == "wsl"}


def disk(data: Path) -> dict:
    data.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(data).free / 1e9
    status = "error" if free < DISK_GB else "warn" if free < WARN_DISK_GB else "ok"
    # Windows' disks read from WSL2 are several times slower.
    slow = system() == "wsl" and str(data.resolve()).startswith("/mnt/")
    return {"id": "disk", "status": "warn" if slow and status == "ok" else status, "gb": round(free), "slow": slow}


def model_files() -> list[Path]:
    from volleyball_stats import actions, ball, film, identity, pictures, players

    return [ball.WEIGHTS_PATH, players.MODEL, actions.POSE_MODEL, identity.REID, film.SEG_S, film.SEG_M, pictures.UPSCALER]


def models() -> dict:
    missing = [p.name for p in model_files() if not p.exists()]
    return {"id": "models", "status": "warn" if missing else "ok", "missing": len(missing), "total": len(model_files())}


def code() -> dict:
    from volleyball_stats import updates

    known = updates.installed(git_check.ROOT) or ((git_check.ROOT / ".git").exists() and shutil.which("git"))
    late = git_check.behind(git_check.ROOT) if known else None
    return {"id": "code", "status": "warn" if late else "ok", "behind": late["behind"] if late else 0}


def busy() -> dict:
    from volleyball_stats import match

    nice, load = procs.priority(), procs.load()
    reasons = match.slow_run_reasons(nice, load, os.cpu_count() or 1)
    return {"id": "busy", "status": "warn" if reasons else "ok", "load": round(load, 1), "cores": os.cpu_count(), "nice": nice}


def speed(outputs: Path = Path("outputs")) -> dict:
    """An hour of match's analysis here (`estimate`), unknown before the first import; too slow past estimate.SLOW."""
    from volleyball_stats import estimate

    found = estimate.stages(outputs)
    hour = None if found is None else 3600 * sum(found[k] for k in estimate.REFERENCE)
    return {"id": "speed", "status": "warn" if hour and hour > 3600 * estimate.SLOW else "ok", "hour": hour}


def checks(data: Path = Path("data")) -> list[dict]:
    found = []
    for check in (tools, gpu, memory, lambda: disk(data), models, speed, code, busy):
        try:
            found.append(check())
        except Exception as error:  # noqa: BLE001
            found.append({"id": getattr(check, "__name__", "check"), "status": "error", "detail": str(error) or type(error).__name__})
    return found


def fetch_models() -> None:
    """ffmpeg where the app installs it and it is missing (`tools`), then each model missing, downloaded where the
    pipeline looks for it. The share told as it goes is the items done of those missing, ffmpeg's by its bytes (the
    libraries downloading the models show none)."""
    from volleyball_stats import ball, identity, jobs, pictures, tools as fetched

    missing = [p for p in model_files() if not p.exists()]
    ffmpeg = fetched.fetchable() and not (shutil.which("ffmpeg") and shutil.which("ffprobe"))
    items = len(missing) + ffmpeg
    if ffmpeg:
        print(f"Downloading ffmpeg {fetched.VERSION}", flush=True)
        fetched.fetch(lambda share: jobs.tell(share / items))
    for done, path in enumerate(missing, start=ffmpeg):
        jobs.tell(done / items)
        print(f"Downloading {path.name}", flush=True)
        if path == ball.WEIGHTS_PATH:
            ball.load_model("cpu")
        elif path == identity.REID:
            identity.load_reid("cpu")
        elif path == pictures.UPSCALER:
            if pictures.upscaler() is None:
                raise SystemExit(f"Could not download {path.name}")
        else:
            from ultralytics.utils.downloads import attempt_download_asset

            path.parent.mkdir(parents=True, exist_ok=True)
            attempt_download_asset(path)
        if not path.exists():
            raise SystemExit(f"Could not download {path.name}")
    jobs.tell(1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check what this machine needs to process a match.")
    parser.add_argument("--models", action="store_true", help="Download the models missing")
    args = parser.parse_args()
    if args.models:
        fetch_models()
        print("Done", flush=True)
        return
    print(json.dumps(checks(), indent=1))


if __name__ == "__main__":
    main()
