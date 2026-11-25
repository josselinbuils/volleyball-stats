# Easier for anyone

The plan to make the app usable by people with no computing knowledge, on their own machine: no cloud GPU (too
expensive, the owner's call, 25 Nov). Agreed with the owner on 25 Nov: every item below gets done, in the order chosen
here. **To resume in a new session:** read this file, pick the first step not ticked, read its "Touches", go. Tick a
step only once its "Done when" holds, and add a line to the [log](#log).

Not this plan (dropped 22 Nov, still dropped): a club sending its video for the owner to process, a job queue across
machines, logins and the review on the VPS. Here everyone runs the app on their own computer.

The project's rules apply to every step (CLAUDE.md): UX first, light interface text, fr first then en, every action in
the app, Windows and macOS alike, benchmarks before and after a pipeline change, `benchmarks/online.py` before/after any
Python or page change, commit + push + restart the review once a step is done.

## Where a newcomer stops today (25 Nov)

| Stage | Today | Blocker for a non-tech person |
|---|---|---|
| Install | `curl … \| sh` in a terminal; Windows needs WSL2 first (`wsl --install`, reboot, Ubuntu) | terminal, WSL, Homebrew's password prompt |
| Processing | ~2.5 s of GPU work per second of video on an RTX 5080 (a match ≈ 3.6 h), about twice that on an M4 Pro | nothing keeps the machine awake; a sleep, restart or update loses everything (tracking writes nothing until it ends); no time shown before starting |
| Recording | `recording.md`: placement, settings, fan; lens calibration is a command (`lens calibrate`) | know-how in a doc, a command outside the app |
| Framing | discovered at import, after the match | a bad framing costs a whole match |
| Sharing | your own Linux server (root SSH, nginx), or the zip export | a server, or a host to find for the zip |
| First run | the list, empty | nothing says what to do first |

## Order

1. [Keep the computer awake during a job](#1-keep-the-computer-awake)
2. [Say the time it will take before starting](#2-say-the-time-before-starting)
3. [Resume a stopped analysis](#3-resume-a-stopped-analysis)
4. [Lens calibration in the app, profiles picked by camera](#4-the-lens-without-a-command)
5. [A framing check](#5-a-framing-check)
6. [The recording guide in the app](#6-the-recording-guide-in-the-app)
7. [Native Windows (no WSL)](#7-native-windows)
8. [Installers: Windows and macOS](#8-installers)
9. [Share a match without a server](#9-share-without-a-server)
10. [A guided first run](#10-a-guided-first-run)
11. [A newcomer's test, then the fixes it shows](#11-a-newcomers-test)

Why this order: 1-3 are cheap and protect the hours a slow machine spends (a laptop runs a match overnight); 4-6 stop
a bad recording before it happens; 7-8 are the biggest change (most people are on Windows) and need 1-3 working on
native Windows too; 9 needs nothing before it; 10 comes last because it walks through every screen the steps before
change. Step 0 can happen any time and helps every step: **the owner watches one non-tech friend install and process a
short clip, without helping, and notes where they stop** (waits on the owner; its notes go in the log).

## 1. Keep the computer awake

- [x] Done (26 Nov), but its sleep test: the owner's PC already holds itself awake
  (`CallNtPowerInformation` shows a request with no job, `powercfg /requests` needs admin), the Mac not tried.

A job (`jobs.start`) holds the machine awake while it runs, the screen free to sleep; nothing to set.

- macOS: `caffeinate -i -w PID` beside the job. Linux: `systemd-inhibit --what=idle:sleep` when present, else nothing.
  Windows (native, step 7): `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` through `ctypes` in the job's
  process. Under WSL2 the sleep to stop is Windows': a hidden `powershell.exe` calling `SetThreadExecutionState` in a
  loop for as long as the job's process lives (check it does not need admin; `powercfg /requestsoverride` does).
- A laptop on battery: say it in the job's screen ("Branchez l'ordinateur"), the lid closing still sleeps it on most
  laptops (say so where the time is shown, step 2).
- Touches: `jobs.py` (`start`, `run`), a small `awake.py`, `doctor.py` if a check fits; tests in `tests/`.
- Done when: a job on the Mac and on the PC (WSL2) runs past the system's sleep delay set to 1 min, the machine awake;
  ended, the machine sleeps again (`pmset -g assertions`, `powercfg /requests`).

## 2. Say the time before starting

- [ ] Done

Before the analysis starts, the import says how long it will take on this machine, in plain words ("environ 7 h :
laissez l'ordinateur allumé et branché"), and the projected end time.

- A machine with `outputs/pipeline_timings.json` uses it (×video length, as `match.plan` does). A new machine has
  none: measure, as `benchmarks/speed.py` does, a few seconds of the video on this machine's models at import (counted
  work, its own bar), then scale by the 5080's stage shares.
- `doctor.py` (Diagnostics) shows the same figure for an hour of match.
- A machine too slow (no GPU, CPU only: tens of hours) is told so before it starts, and what would make it faster.
- Touches: `benchmarks/speed.py` (move what is shared into the package), `match.py` (`plan`, `TIMINGS`), `app.py`
  import routes, the import screen in `web/src/` (the app's screens, `LOCAL` in `web/online.ts`), locales.
- Done when: on the PC and the Mac, a first import with `pipeline_timings.json` removed (kept aside) announces a time
  within 20% of the real run's.

## 3. Resume a stopped analysis

- [ ] Done

A stopped analysis (sleep, restart, crash, update, the window closed) starts again where it was, not from zero.

- Tracking is the long stage (~1.26 of the 2.5 s per second of video) and writes nothing until it ends: write it in
  chunks (every few minutes of video, the chunk's file in place at once) and on a new run start after the last whole
  chunk. The other stages already keep their results between runs (a run on the same tracks takes seconds).
- The list offers "Reprendre" on a match whose analysis stopped (it already offers to run again: same place).
- Must be bit-identical: tracks carry state across frames (ids, the tracker's memory). A chunk restarts the tracker
  from a saved state, or re-reads an overlap before the chunk and keeps only what follows; pick what gives the same
  outputs as an uninterrupted run.
- Touches: the tracking stage (`players.py`, `ball.py`, `match.py`), `jobs.py`, the list's card; tests.
- Done when: on one match, a run killed twice at random points then resumed gives the same `outputs/matches/MATCH/`
  files as an uninterrupted run (byte for byte, or the differences explained and accepted by the owner); the pipeline's
  benchmarks unchanged.

## 4. The lens without a command

- [ ] Done

- Lens calibration in the app (the rule: every action in the app): the club's or Diagnostics' "Calibrer la caméra",
  the board to print or show full screen, the filmed clip picked like an import, `lens calibrate` as a job with its
  bar, the result checked (coverage, error) in plain words.
- Profiles by camera: the camera's own files carry its model (DJI's tags, Apple's, GoPro's: read before the import
  remuxes them, the imported `MATCH.mp4` says only `Lavf`). A known model and mode picks its profile
  (`lens_osmo_action3_standard_4k.json` today) with no calibration; an unknown one runs without, and the app says the
  court's positions are less precise and offers the calibration.
- Touches: `lens.py`, `import_match.py`, `app.py` (`LENS`, the court's `--lens`), the club or Diagnostics screen.
- Done when: the court benchmark (`benchmarks/court/`) unchanged with the profile picked automatically; a calibration
  done from the app alone on the Mac and the PC.

## 5. A framing check

- [ ] Done

A bad framing costs a match: check it before.

- `court auto` only finds a court already stored (a gym calibrated once from clicks); a new gym, every away match's
  among them, needs the clicks. So: "Tester le cadrage" takes a photo or a few seconds filmed from the planned spot,
  imported like a match. A stored court answers on its own; a new gym asks the rough clicks (the existing flow),
  and a corner or end line out of the picture is what it reports. The answer is a picture: the court's outline drawn,
  OK or what to change ("reculez", "montez la caméra", "alignez-la sur le filet"). The court is stored, so the match
  itself is found automatically.
- The same check runs at each import on the first minutes, said at once, before the long analysis.
- At the gym (open, the owner's call): the computer only sees the camera's picture once the card is imported, usually
  after the match. A check there could be (a) the recording guide (step 6) readable on a phone with "what the
  camera's screen must show", judged by eye: hours on top of step 6, but a page online (ask the owner); (b) the
  automatic check in the phone's browser on a screenshot of the camera's live view (DJI Mimo or the like): court.py's
  line snapping ported to JS (opencv.js, ~10 MB), the picture never leaving the phone: several days; (c) the app on a
  laptop at the gym through "Réseau local" (`network.py`): nothing to build, a laptop and one network needed. Sending
  the picture to a server is out (footage of people). Decide after step 11 shows whether framing goes wrong.
- Touches: `court.py`, `app.py`, the import screen.
- Done when: on the four matches' first frames the check says OK; on frames cropped to hide an end line, it says
  which one and what to do.

## 6. The recording guide in the app

- [ ] Done

`recording.md` for anyone: one screen (the list's menu, and linked from the framing check and the first run) with the
placement as a drawing (SVG, no real footage), the settings for the known cameras, what to bring (the checklist), the
fan and the battery. The fewest words: the drawing says most.

- Touches: a new screen in the app's code (`LOCAL`), locales fr then en; `recording.md` stays the long version.
- Done when: the screen reads at phone width without horizontal scroll, light and dark.

## 7. Native Windows

- [ ] Done

The app and the pipeline on Windows itself, no WSL. CUDA PyTorch runs there; the rest assumes a POSIX system.
Keep WSL2 working until native has passed everything below.

- Audit, then fix each: the 7 modules naming WSL (`app.py`, `doctor.py`, `jobs.py`, `network.py`, `shortcut.py`,
  `jerseys.py`, `likeness.py`); `jobs.py`'s process handling (`start_new_session`, `ps lstart`, `process_key`'s boot
  ticks, signals); `sync.py`'s locks (`flock`) and `ssh`/`rsync` for the server and backups (rsync is not on Windows:
  find what replaces it, no new Python dependency without asking); the file picker (`app.pick`: the Windows dialog
  directly); paths and drives (the SD card is a plain drive letter); the shortcut (`shortcut.py`: a native `.lnk`);
  ffmpeg's encoders (NVENC on Windows); `uv run stats` and its launcher.
- Test on the owner's PC itself (Windows side), CPU and GPU.
- Touches: the modules above; `install.sh` stays for macOS/Linux.
- Done when: on native Windows, `uv run pytest -q` passes, a match imports, runs (same outputs as under WSL2, or the
  differences explained), reviews, exports, uploads and backs up; the pipeline's speed within 10% of WSL2's.

### The audit (25 Nov)

A copy in `D:\vbs-native` (no `server.json`, no `publish.json`: it cannot sync or upload), uv and ffmpeg installed per
user (`irm https://astral.sh/uv/install.ps1 | iex`, `winget install Gyan.FFmpeg --scope user`: no admin; its ffmpeg has
`av1_nvenc`, `h264_nvenc`, `libsvtav1`), uv's cache on D: (C: has 25 GB free). Git is not on Windows: the copy was
cloned from WSL. The trial's files: `D:\vbs-trial\` (a 3-minute cut of the 16 Nov match, its court, the logs).

Fixed at once (committed):
- No Python pinned: a fresh machine got CPython 3.15, which torch has no wheel for (a fresh Mac too, through
  `install.sh`). `.python-version` pins 3.12, the version WSL runs.
- PyPI's torch is CPU-only on Windows: `torch` and `torchvision` come from PyTorch's CUDA 13 index there
  (`[tool.uv.sources]`, marker `win32`); Linux's and macOS's packages unchanged (`uv sync --dry-run`). The 5080 is seen.

Left to fix, by how much they block:
1. **The app does not start**: `os.nice` does not exist on Windows (`app.lowered`, `match.py`'s busy check, with
   `os.getloadavg`). Busy and priority checks need a Windows way (the process's priority class; the CPU's load).
2. **Ctrl+C to itself**: `os.kill(pid, 0)` (`jobs.alive`, 2 calls) tests a process on POSIX, but on Windows signal 0 is
   `CTRL_C_EVENT`, sent to the whole console: it stopped pytest itself, it would stop the app. A Windows test of a
   process (`OpenProcess` through `ctypes`, or `tasklist`).
3. **Text encoding**: 148 `read_text()`/`write_text()`/`open()` without `encoding=`: Windows' default is cp1252, the
   pages come out garbled ("·" as "Â·", test_matches). `encoding="utf-8"` everywhere, or `PYTHONUTF8=1` set by the
   launcher (the quick way; Python 3.15 makes UTF-8 the default).
4. **Replacing a file still open** (`files.py`'s atomic write, a numpy temp file): `PermissionError` (WinError 5) where
   POSIX replaces it. Close before replacing, retry a moment.
5. **Symlinks** (2 places: a match's video link): need admin or Developer Mode on Windows (WinError 1314). A copy,
   a hard link or the path itself.
6. **Remote paths built as local ones**: the server's paths and the ssh key come out with backslashes
   (`root@host:\…\feedback.log`, `ssh -i '\Users\A B\key'`): `PurePosixPath` for what goes to the server.
7. **Jobs outliving the server**: `start_new_session` means nothing on Windows: `CREATE_NEW_PROCESS_GROUP` and
   `DETACHED_PROCESS`; `ps` (3 calls: `started_at`, the busiest processes) and `/proc` (`process_key`) absent.
8. **Tools**: `rsync` (5 calls: uploads, backups) is not on Windows; ssh is (Windows' OpenSSH). `fcntl.flock`
   (`sync.py`) absent. Git absent: the installer brings it, or updates come from GitHub's archive (step 8).
9. **The platform's own screens**: the file picker (`app.pick`: Windows' dialog directly, not through `wsl.exe`), the
   shortcut (`shortcut.py`: a `.lnk` starting `uv run stats`, not `wsl.exe`), drives (a plain `E:\`, no mount).
10. A script started as a program (WinError 193, the backup flow's tests: their fake `ssh` is a shell script) and
    `time.tzset` (test_sync): the tests' own POSIX habits, to make portable with the code.

Tests natively: 1,065 pass, 43 fail in 18 of the 60 files run, and `test_jobs.py` (17 tests) stops the run (point 2);
the reasons above; the full list in `D:\pytest-files.txt` and `D:\pytest-files2.txt`. Diagnostics runs, its busy check fails
(point 1); 5 of the 7 models missing on a new machine, as expected (downloaded by Diagnostics).

The pipeline natively (`D:\vbs-trial\run_native.py`: `os.nice` and `os.getloadavg` stood in for, the code unchanged), on
the 3-minute clip, against WSL2 on the same file:
- It runs to the end: 826 s against 495 s (+67%). Tracking takes the same time (3.9 min against 4.0); what decodes
  4K frames and the OCR are slower: identity 5.0 min against 1.5, jerseys 2.3 against 1.1, wrists, teams, jumps.
11. **Windows' pipe is the bottleneck**: ffmpeg alone decodes 263 4K frames a second there (200 under WSL2), but read
    through `Popen`'s pipe Python gets 22 (108 under WSL2), whatever Popen's buffer. A pipe made with a 1 MB buffer
    (`_winapi.CreatePipe`, given to ffmpeg as its stdout) gives 146, more than WSL2: `decode.piped`'s pipe on Windows.
12. **The OCR on the CPU**: `onnxruntime-gpu` is installed on Linux only (pyproject's marker), Windows gets the CPU
    one. `onnxruntime-gpu` has Windows wheels: extend the marker to `win32`, check it shares torch's CUDA there.
13. **ffmpeg's version changes the pixels**: Windows' (winget, 9.1) and WSL2's (Ubuntu, 6.1) give the same frame with
    12% of its pixels off by up to 9 levels (their scaler changed), CPU and GPU decoding identical on each. The boxes
    move by about 0.2 px, which was enough to split one rally in two (6 rallies against 5, the set 3-3 against 2-3).
    Not Windows' doing: a Mac on Homebrew's ffmpeg differs from the PC already. The installers bring one ffmpeg
    version everywhere (step 8), the same under WSL2, and Diagnostics names a different one.

## 8. Installers

- [ ] Done

A file to download and double-click, nothing typed.

- Windows: a `setup.exe` (Inno Setup, free) that installs uv, ffmpeg and git where missing (`winget` on Windows 10/11
  when present, else their own installers; no admin rights if possible), the code, the shortcut, then opens the app.
  An `install.ps1` first (the same steps, testable alone), the `.exe` wrapping it.
- macOS: a `.dmg` with `Volleyball Stats.app` that installs on first open without Homebrew if possible (uv's own
  installer, a static ffmpeg build: check its licence; git through the system or none: see below), so no password.
- Git: the app updates with `git pull`. Without git on the machine, update from GitHub's release archive instead;
  decide when there (the sync's `code.json` names a commit: keep that working).
- No code signing (the owner's call, 25 Nov: no Apple Developer Program, no Windows certificate). So the warning
  comes once, at the first install only, and is made easy to pass:
  - The installers stay small and rarely change: they fetch the code, and the app updates itself (`git pull`, or the
    archive) without any warning. On Windows, SmartScreen's reputation is per file: an unchanged `setup.exe` builds it.
  - Windows: SmartScreen's "Windows a protégé votre ordinateur": "Informations complémentaires" then "Exécuter quand
    même". macOS (Sequoia and later, right-click > Open no longer works): open it once, then Réglages Système >
    Confidentialité et sécurité > "Ouvrir quand même". The download page shows each, in screenshots of the real
    dialogs, fr then en.
  - Also on the page, for those at ease with it: one line to paste (`irm … | iex` in PowerShell, `curl … | sh` in
    Terminal): files fetched so carry no "downloaded from the internet" mark, so no warning at all.
  - The `.app` is ad-hoc signed (`codesign -s -`, free: Apple Silicon refuses to run unsigned code at all).
- Where to download: a page with the two buttons (the hosted list's site or GitHub's releases). **Ask the owner before
  putting anything online.**
- Touches: `install.sh`, new `install.ps1`, `packaging/` (Inno Setup script, the `.app`'s bundle), GitHub releases.
- Done when: on a fresh Windows 11 account and a fresh macOS user (no tools installed), the download, the
  double-click and nothing else end on the app's list with Diagnostics all green.

## 9. Share without a server

- [ ] Done

The Site tab offers a server-less way: "Publier" puts the matches' pages on a free static host, no server to set up.

- A match's page without the video is small (~14 MB, ~650 files: `outputs/hosted/MATCH/` without `video/`), within
  every free host's limits. The video stays off (a free host has no password: CLAUDE.md's rule on footage), pictures
  only with the players' consent (the same rule as the owner's site).
- The host: Netlify (an OAuth "Se connecter à Netlify" button, the app deploying through its API: no token to paste)
  before Cloudflare Pages (API tokens only). Check its free plan's terms and limits for this use when starting.
  The owner's own server stays as it is, for those who have one.
- Then: the page's link to copy, and a QR code to show at the club.
- Touches: `server.py`, `matches.py` (build into a folder, as the export does), the Site tab (`SiteTab.tsx`), a
  `netlify.py`; the export's code reused.
- Done when: from a new Netlify account, two matches go online from the app alone, update when a match changes
  ("En retard" then "À jour" as with the server), and open on a phone.

## 10. A guided first run

- [ ] Done

The first opening walks through it: the club and its teams, the recording guide (step 6), the framing check (step 5),
the import, the analysis (its time, step 2), the review, sharing (step 9). Each screen says only what is next; a
step done is ticked; it stays reachable from the list's menu until every step is done once, then goes.

- The review's first open explains its questions once, in a few words, with one example.
- Touches: the list (`appPanel.tsx` and its screens), the review's first open, locales.
- Done when: a person who has never seen the app goes from the first opening to a shared match without asking
  anything (checked in step 11).

## 11. A newcomer's test

- [ ] Done

The owner gives the download link to one or two non-tech people (a teammate, a parent), watches without helping, notes
where they stop. Each stop becomes a step here, before the order's end.

Their own gym is the other risk: everything is tuned on ASPOM's gym and camera, and the play model is already worse on
the one other match ([state.md](state.md), open item 4). Run their first match's numbers (corrections asked, rallies
found) against ours and say what differs.

## Log

One line per session: date, what was done, what is next.

- 25 Nov: plan written with the owner (costs of a cloud GPU rejected: ~€8 a match). No code signing (owner). Next: step 1.
- 25 Nov: step 7's audit on the owner's PC natively (its findings under step 7): Python pinned to 3.12 and CUDA torch
  on Windows committed; the pipeline runs natively but 67% slower (the pipe, the OCR on the CPU), its outputs differ
  by ffmpeg's version. Next: step 1, step 7's fixes when it comes.
- 26 Nov: step 1 done (`awake.py`): jobs and the review's apply hold the machine awake, the job's screen says when
  it runs on battery. Checked under WSL2 (the holder gone on a normal end, a kill, a lost process) and natively on
  Windows (the thread's state set and released); a real sleep test waits for the Mac and a PC not held awake by
  something else. Next: step 2.
