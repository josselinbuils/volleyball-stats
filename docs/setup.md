# Setup

- [Requirements](#requirements)
- [Install](#install)
- [Performance](#performance)

## Requirements

- **A GPU.** Processing picks an NVIDIA GPU (CUDA) first, then Apple Silicon (MPS), then the CPU.
  Run on an RTX 5080 in WSL2 with Ubuntu, on the same PC natively on Windows (the same speed) and on an Apple M4 Pro
  (about twice as slow).
- **NVIDIA on Windows:** the Windows NVIDIA driver covers WSL2 too: do not install a Linux driver. The
  locked PyTorch is the CUDA 13 build. It supports the RTX 50 series and needs a recent driver (R580
  or later).
- **Tools:** [`uv`](https://docs.astral.sh/uv/) (it installs Python 3.12+) and `ffmpeg`, which the installers bring;
  `git` only to develop, Node.js 22 only to change the page (its build is committed).
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code Remote-SSH).
- **Two machines** (the Mac and the PC): the matches' results go through the hosting server (`sync`, the review opening
  each match on its newest copy), the videos copied by hand: [hosting.md](hosting.md).
  The code goes through git: pull before working. The committed build and `attribution_ranker.json` conflict when both
  machines change them: take either side, then rebuild or retrain.
- Older repositories pinning older PyTorch or TensorFlow versions are ported to this environment
  rather than run as-is.

## Install

For users: on Windows `volleyball-stats-setup.exe`, on a Mac `volleyball-stats.dmg`, both from
[the download page](https://github.com/josselinbuils/volleyball-stats/releases/latest) (the README says how); on Linux
the line below. The same without the installers, from a terminal:

```bash
curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh   # Mac, Linux, WSL2
```

```powershell
irm https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.ps1 | iex       # Windows, PowerShell
```

To develop: `git clone https://github.com/josselinbuils/volleyball-stats && cd volleyball-stats && ./install.sh`.

`install.sh` does it all and starts the app (the `.dmg`'s app runs it too, or `./install.sh` in a developer's git
checkout, which it keeps): uv (its own installer), the code from GitHub's archive
(no git: the app then updates it by itself), the libraries, the models, and ffmpeg 9.1 on a Mac (no Homebrew, no
password); on Linux and WSL2 ffmpeg and curl through apt. The code in `~/volleyball-stats` (`VOLLEYBALL_STATS_DIR` for another place),
`~/.local/bin/volleyball-stats` (`uv run stats`, carrying the PATH the tools were found on: a Mac's shortcut opens
without Homebrew's). The app's start and the club's changes make the shortcut on that launcher again when
`shortcut.VERSION` or the icon's colours change (`shortcut.py`), replacing the older `.bat` or `.command`: under WSL2 a
Windows `.lnk` on the desktop and in the Start menu (`conhost.exe --headless wsl.exe …`, natively `cmd.exe` on
`volleyball-stats.cmd`: no window, the icon in
`%LOCALAPPDATA%`), on a Mac `Volleyball Stats.app`, the .dmg's in Applications or else one in `~/Applications`,
on Linux an applications menu entry. The icon (`icon.py`) is a volleyball in the club logo's two main colours (else its
main colour, else blue and yellow), drawn with Pillow for the shortcut and as SVG for the pages' favicon (`icon.favicon`,
named after its colours: Windows caches icons by path). On a Mac that app is a native one (`packaging/macos/app.swift`, built by
`app.sh` and committed, for Apple chips and Intel): the page in its own window (WebKit), its Dock icon; it starts the
server (`stats server --with-app`) with a pipe on its stdin and the server stops once that pipe ends, when the app
quits (⌘Q, the Dock), no timer. Closing its window only hides it, the Dock icon shows it again. `stats` opens that app
when it is there (`shortcut.mac_app`). Elsewhere the page opens in a window of its own (`--app`) of Chrome or Edge
(Brave or Chromium too on Linux), else in the browser (`app.app_window`), its title ending in "– Volleyball Stats" there. Closing
it stops the server (`presence.py`), once no job runs (Windows may stop WSL with it). The app's "Diagnostics" (`doctor.py`) checks the tools, the graphics card
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

Or natively on Windows, no WSL: the installer or `install.ps1` above (in PowerShell, not as administrator).

`install.ps1` installs uv, the code in `~\volleyball-stats` (GitHub's archive: no git), the libraries, ffmpeg 9.1 and
the models, the launcher `~\.local\bin\volleyball-stats.cmd`, then opens the app, which makes its shortcuts. No admin
rights; run again, it only opens the app. `setup.exe` (`packaging/windows/setup.iss`, Inno Setup 7) runs it in a window
of its own; its uninstaller, in Windows' installed apps, removes the app and, if asked, the matches. A Mac's
`volleyball-stats.dmg` (`packaging/macos/build.sh`, on a Mac) holds the Mac app to drag to Applications: its first open
runs `install.sh` in Terminal, which opens it again once done, and its first start makes it the shortcut. Both are built by the "Installers" workflow (`.github/workflows/installers.yml`, started by hand); given a
release's tag, it gives both its version (`v1.2`: 1.2, "dev" without a tag: no version written by hand) and puts them on that GitHub release with its text (`packaging/release/release.md`, the screenshots of
SmartScreen and Gatekeeper beside it): the download page, whose links stay the same
(`releases/latest/download/volleyball-stats-setup.exe`, `…/volleyball-stats.dmg`). The installers change rarely: they
take the code from GitHub at install.

Without git, the code's version is the archive's commit (`.install.json`: its files too), the commits behind come from
the branch's feed and "Mettre à jour" writes the new archive over it, removing the files gone (`updates.py`). Such an
install also updates itself (`app.auto_update`): at the server's start and every hour, when no job, apply nor match's
review runs, then the server starts again on it; meanwhile nothing else starts and the pages say "Mise à jour de
l'application…", reloading once it ended. A git checkout keeps the button: its owner pulls.

Natively, torch comes from PyTorch's CUDA 13 index (`[tool.uv.sources]`) and the OCR from `onnxruntime-gpu` on torch's
CUDA. What POSIX has and Windows lacks has a stand-in in the code: processes (`procs.py`: `OpenProcess` and its creation
time, priority classes, the CPU's busy share, jobs apart from the console's Ctrl+C), rsync (`transfer.py`), the frames'
pipes (`decode.popen`, 1 MB), files replaced while another process reads them (`files.replace` retries). Symlinks need
Developer Mode, which nothing needs. Its ffmpeg gives pixels slightly unlike Ubuntu's 6.1: the same match can come
out a rally apart ([easier.md](easier.md), step 7).

ffmpeg where the system has none, on Windows and a Mac (`tools.py`): 9.1, Gyan's full build on Windows and Martin
Riedl's on a Mac, each file checked by its sha256, in `~/.local/share/volleyball-stats/ffmpeg` and first on the PATH.
Both GPL (x264). Diagnostics offers it with the models (`uv run python -m volleyball_stats.tools` by hand); Linux has
apt's.

On a Mac, by hand with Homebrew:

```bash
brew install ffmpeg git uv
git clone https://github.com/josselinbuils/volleyball-stats.git && cd volleyball-stats
uv sync
```

The models (ball, players, re-identification) download on their first use (the 3D figures' hair and skin one, from
Hugging Face, at the first pictures; offline the figures keep made-up looks), or ahead from the app's warning
(`uv run python -m volleyball_stats.doctor --models`). One model is not downloaded but learned from the matches reviewed here and
shared between a person's machines by the backup: the play / no-play model (`outputs/learned/play/`, [hosting.md](hosting.md))
and the touch types' from the gesture (`outputs/learned/gesture/`, from two fully checked matches); without them the
pipeline runs on its rules alone.

## Performance

- **Keep the videos in the Ubuntu file system** (`~/`), not under `/mnt/c`: reading Windows files
  from WSL2 is several times slower.
- **One reading of the video:** `ffmpeg` decodes it once for both the ball and the players, on the
  graphics card (NVDEC) when it can, shrinking the frames to 1280 px before the models.
  `sudo apt install ffmpeg` in WSL2 is enough for NVDEC.
- **Numbers read on the graphics card:** the jerseys and the score board (RapidOCR) run on it through
  `onnxruntime-gpu`, which `uv sync` installs on Linux and Windows in place of `onnxruntime`, with torch's CUDA
  libraries.
- **Processing time:** the RTX 5080 ran a 91-minute 4K match end to end in 4 h 15. Tracking, the longest step,
  runs the ball's and the players' models in two threads on an NVIDIA card (37 frames a second); on the M4 Pro in turn,
  7.8 h for 2 hours of 4K 50 fps (Metal aborts on two threads). `speed.py` projects a video's tracking time.
- **Memory:** a 2-hour match at 50 fps needs about 6.3 GB of RAM at its peak, the identity step
  holding the players' rows (`benchmarks/scale.py` measures each step on a synthetic long match).
- **WSL2 memory:** WSL2 gets half of the PC's RAM by default. With 16 GB, raise it in
  `%UserProfile%\.wslconfig` (`[wsl2]`, then `memory=12GB`) and restart WSL (`wsl --shutdown`).
