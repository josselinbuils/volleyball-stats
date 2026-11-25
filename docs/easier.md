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

- [ ] Done

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

- "Tester le cadrage": a photo or a few seconds filmed from the planned spot, imported like a match; the automatic
  court detection (`court auto`) answers in a picture: both end lines and corners seen, or what to change ("reculez",
  "montez la caméra", "alignez-la sur le filet"), with the court's outline drawn on the picture.
- The same check runs at each import on the first minutes, said at once, before the long analysis.
- Ask the owner then: is a check at the gym, from a phone, worth it (the review server on the local network,
  `network.py`, or a page in the hosted site that runs nothing but the detection)? Decide before building more than the
  in-app check.
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
- Signing: unsigned, Windows shows "Windows a protégé votre ordinateur" (SmartScreen) and macOS blocks the app
  (Privacy settings > "Ouvrir quand même"), both hard for non-tech people. Apple's Developer Program is $99/year
  (signing + notarization); a Windows code-signing certificate costs a few hundred euros a year. **Waits on the owner:
  buy them or not.** Unsigned, the download page shows how to get past the warning, in pictures.
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

- 25 Nov: plan written with the owner (costs of a cloud GPU rejected: ~€8 a match). Next: step 1.
