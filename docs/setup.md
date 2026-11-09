# Setup

- [Requirements](#requirements)
- [Install](#install)
- [Performance](#performance)

## Requirements

- **A GPU.** Processing picks an NVIDIA GPU (CUDA) first, then Apple Silicon (MPS), then the CPU.
  Set up for an RTX 5080 in WSL2 with Ubuntu (its speed not measured yet), and run on an Apple M4 Pro
  (slower).
- **NVIDIA under WSL2:** the Windows NVIDIA driver covers WSL2: do not install a Linux driver. The
  locked PyTorch is the CUDA 13 build. It supports the RTX 50 series and needs a recent driver (R580
  or later).
- **Tools:** [`uv`](https://docs.astral.sh/uv/) (it installs Python 3.12+), `ffmpeg` and `git`.
  Node.js 22 only to change the page: its build is committed.
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code Remote-SSH).
- **Two machines** (the Mac and the PC): the matches' results go through the hosting server (`sync`, the review opening
  each match on its newest copy) and the videos straight between them (`data_sync`): [hosting.md](hosting.md).
  The code goes through git: pull before working. The committed build and `attribution_ranker.json` conflict when both
  machines change them: take either side, then rebuild or retrain.
- Older repositories pinning older PyTorch or TensorFlow versions are ported to this environment
  rather than run as-is.

## Install

`install.sh` does it all and starts the app (`curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh`,
or `./install.sh` in a copy): Homebrew on a Mac, git, ffmpeg and uv when missing, the code in `~/volleyball-stats`
(`VOLLEYBALL_STATS_DIR` for another place), `~/.local/bin/volleyball-stats` (carrying the PATH the tools were found
on: a Mac's shortcut opens without Homebrew's) and a desktop shortcut (a Mac's `.command`, Windows' `.bat` from WSL2;
none on Linux: the same line starts it again). The app's "Installation" (`doctor.py`) checks the tools, the graphics card
and its driver, the memory, the disk, the models (downloaded there) and the code's version. By hand:

On a Windows PC with an NVIDIA GPU:

```bash
wsl --install -d Ubuntu-24.04                     # in PowerShell, then reboot
# in Ubuntu:
sudo apt update && sudo apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/josselinbuils/volleyball-stats.git && cd volleyball-stats
uv sync
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name())"
uv run python benchmarks/speed.py VIDEO          # projected processing time of a match
```

On a Mac:

```bash
brew install ffmpeg git uv
git clone https://github.com/josselinbuils/volleyball-stats.git && cd volleyball-stats
uv sync
```

The models (ball, players, re-identification) download on their first use, or ahead from the app's warning
(`uv run python -m volleyball_stats.doctor --models`).

## Performance

- **Keep the videos in the Ubuntu file system** (`~/`), not under `/mnt/c`: reading Windows files
  from WSL2 is several times slower.
- **One reading of the video:** `ffmpeg` decodes it once for both the ball and the players, on the
  graphics card (NVDEC) when it can, shrinking the frames to 1280 px before the models.
  `sudo apt install ffmpeg` in WSL2 is enough for NVDEC.
- **Numbers read on the graphics card:** the jerseys and the score board (RapidOCR) run on it through
  `onnxruntime-gpu`, which `uv sync` installs on Linux in place of `onnxruntime`, with torch's CUDA libraries.
- **Processing time:** `speed.py` compares that reading with the old two readings and projects both
  over a 2-hour match. On the M4 Pro the models set the pace (7.8 h instead of 8.4 h for 2 hours of
  4K 50 fps). The RTX 5080 should run them several times faster, so the saved reading matters more
  there.
- **Memory:** a 2-hour match at 50 fps needs about 8 GB of RAM at its peak, the identity step
  holding the players' rows (`benchmarks/scale.py` measures each step on a synthetic long match).
- **WSL2 memory:** WSL2 gets half of the PC's RAM by default. With 16 GB, raise it in
  `%UserProfile%\.wslconfig` (`[wsl2]`, then `memory=12GB`) and restart WSL (`wsl --shutdown`).
