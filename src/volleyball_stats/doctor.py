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

from volleyball_stats import git_check

# A 2-hour match: about 8 GB of RAM at its peak (docs/setup.md), its 4K video about 60 GB, twice that while it is imported.
RAM_GB, WARN_RAM_GB = 12, 16
DISK_GB, WARN_DISK_GB = 60, 150
MODELS = Path("models")


def system() -> str:
    """"mac", "wsl" or "linux"."""
    if platform.system() == "Darwin":
        return "mac"
    try:
        return "wsl" if "microsoft" in Path("/proc/version").read_text().lower() else "linux"
    except OSError:
        return "linux"


def install_command(packages: list[str]) -> str:
    return f"brew install {' '.join(packages)}" if system() == "mac" else f"sudo apt install -y {' '.join(packages)}"


def tools() -> dict:
    missing = [t for t in ("ffmpeg", "ffprobe", "git") if not shutil.which(t)]
    packages = sorted({"git" if t == "git" else "ffmpeg" for t in missing})
    return {"id": "tools", "status": "error" if missing else "ok", "missing": missing, "command": install_command(packages) if missing else None}


def gpu() -> dict:
    """The device the models run on; on Linux, an NVIDIA card torch cannot use names its driver."""
    try:
        import torch
    except ImportError as error:
        return {"id": "gpu", "status": "error", "kind": "torch", "detail": str(error)}
    if torch.cuda.is_available():
        return {"id": "gpu", "status": "ok", "kind": "cuda", "name": torch.cuda.get_device_name()}
    if torch.backends.mps.is_available():
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        return {"id": "gpu", "status": "ok", "kind": "mps", "name": chip or "Apple"}
    smi = shutil.which("nvidia-smi") or ("/usr/lib/wsl/lib/nvidia-smi" if Path("/usr/lib/wsl/lib/nvidia-smi").exists() else None)
    if smi:
        return {"id": "gpu", "status": "error", "kind": "driver", "name": None}
    return {"id": "gpu", "status": "warn", "kind": "cpu", "name": None}


def memory() -> dict:
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        return {"id": "memory", "status": "ok", "gb": None}
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
    from volleyball_stats import actions, ball, film, identity, players, web

    return [ball.WEIGHTS_PATH, players.MODEL, actions.POSE_MODEL, identity.REID, film.SEG_S, film.SEG_M, web.UPSCALER]


def models() -> dict:
    missing = [p.name for p in model_files() if not p.exists()]
    return {"id": "models", "status": "warn" if missing else "ok", "missing": len(missing), "total": len(model_files())}


def code() -> dict:
    late = git_check.behind(git_check.ROOT) if (git_check.ROOT / ".git").exists() and shutil.which("git") else None
    return {"id": "code", "status": "warn" if late else "ok", "behind": late["behind"] if late else 0}


def busy() -> dict:
    from volleyball_stats import match

    reasons = match.slow_run_reasons(os.nice(0), os.getloadavg()[0], os.cpu_count() or 1)
    return {"id": "busy", "status": "warn" if reasons else "ok", "load": round(os.getloadavg()[0], 1), "cores": os.cpu_count(), "nice": os.nice(0)}


def checks(data: Path = Path("data")) -> list[dict]:
    found = []
    for check in (tools, gpu, memory, lambda: disk(data), models, code, busy):
        try:
            found.append(check())
        except Exception as error:  # noqa: BLE001
            found.append({"id": getattr(check, "__name__", "check"), "status": "error", "detail": str(error) or type(error).__name__})
    return found


def fetch_models() -> None:
    """Each model missing, downloaded where the pipeline looks for it."""
    from volleyball_stats import ball, identity, web

    for path in model_files():
        if path.exists():
            continue
        print(f"Downloading {path.name}", flush=True)
        if path == ball.WEIGHTS_PATH:
            ball.load_model("cpu")
        elif path == identity.REID:
            identity.load_reid("cpu")
        elif path == web.UPSCALER:
            if web.upscaler() is None:
                raise SystemExit(f"Could not download {path.name}")
        else:
            from ultralytics.utils.downloads import attempt_download_asset

            path.parent.mkdir(parents=True, exist_ok=True)
            attempt_download_asset(path)
        if not path.exists():
            raise SystemExit(f"Could not download {path.name}")


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
