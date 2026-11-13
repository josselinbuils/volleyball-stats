# Running and checking

## A match

- `uv run stats` (`app.py`) is the review server on the list of the matches, its `/app/` routes doing what
  used to need a command: `doctor.py`'s checks, the import, the court (`court auto --background`, else clicks and
  `court fit --out`), the pipeline (`match --players --anyway`, after the app's own busy check), the videos with the
  other machine (`data_sync`) and the update (`git pull --ff-only --autostash`, `uv sync --inexact`, a restart; refused
  while a job or an apply runs). It opens the page in a window of its own, `stats browser` in a browser tab, `stats server` nowhere (a restart); it refuses to start at a lowered priority (`app.lowered`: zsh's `bg_nice` on a background job, which its jobs would inherit and nothing without root undoes); `stats` alone stops once its last window closes (`--with-window`, `presence.py`: each page says it is open every 30 s and that it goes as it unloads; 5 s for a reload or another match's review to come back; a page silent for 30 min is gone; never while a job or an apply runs), the restarts keeping it; else Ctrl+C or `uv run stats stop` stops it (`/app/quit`, refused while an apply runs); jobs go on. The long ones are jobs (`jobs.py`): a process of their own in a new session, their
  record and log in `outputs/jobs/`, so they outlive the server's restarts; `match` prints `::progress` while tracking.
  A match being prepared shows above the list until its `report.md` exists; one whose pipeline a command ran and no
  process runs any more is offered to run again. A job is the runner's process number and start time (`ps lstart`):
  after a restart, a reused number is no job. Under WSL2 the import lists Windows' drives, a card plugged in after WSL
  started mounted when picked (`wsl.exe -u root mount -t drvfs`, no password), and the Windows downloads. "Parcourir…" opens the
  system's own file window to pick the video (`app.pick_video`: Finder, Windows' under WSL2, zenity or kdialog on a Linux
  desktop; no button without one). A second start
  only opens the page.
  "Club" (on the list and in the review's "..." menu, `club_settings.py`, `outputs/club/club.json`) edits the one club
  every page shows (name, site, logo, colours, sponsors) and its teams; saved from a review, that match's pages are rebuilt at once, the others at their next build.
- Every `python -m volleyball_stats.X` command fetches in the background and warns when the branch is behind its remote
  (`git_check.py`; once per command, not in the ones it starts). The review and its list say it too, with "Mettre à
  jour" (`/app/update`).
- The videos from the other machine, both on the same network: `uv run python -m volleyball_stats.data_sync` on the Mac (it
  waits and shows a command with a code), that command on the PC. Each gets what only the other has; a cut copy resumes. The
  results come through the review's list ("À télécharger") or `sync pull` ([hosting.md](hosting.md)).
- A new match starts with `import_match` ([processing.md](processing.md)): `data/matches/MATCH/MATCH.mp4` and `outputs/matches/MATCH/`, named like its hosted page, everything of a match in those two folders.
- `match` refuses to track at a low priority or on a busy machine (`slow_run_reasons`, `--anyway`): tell the owner what it lists, stopping their work
  (Docker, Kili sandboxes) is their call. To correct a running job: `sudo renice 0 -p PID...` in their own terminal (`renice -n 0` changes nothing on
  macOS). A run can't survive a restart: tracking writes nothing until it ends. Idle, the M4 tracks 4K at 2.87 MB/s (6 h for 84 min); progress is the
  `ffmpeg` read offset (`lsof -o`) over the file's size.

- `match` ends by making the review's page and pictures, for its first open to be quick; a failure there only warns. The review's reruns pass `--no-page`.

## Checking the page on the short clips

The page holds no video by default; `--footage full --club 1 --pictures` (saved in
`outputs/benchmarks/VIDEO/page.json`) brings back the video and the club's pictures for features that need them.

Then open `outputs/benchmarks/side_setend/site/index.html` (two sets) or `outputs/benchmarks/side_holdout/site/` (one
set). In browser checks mute the videos and check a phone width (no horizontal page scroll). The
"Analyse" columns stay empty on these short clips: lower `MIN_TRIES` in
`web/src/components/Stats/helpers/insights.ts` temporarily to see them, and restore it before the
build you commit. `benchmarks/scale.py` measures memory on a 2-hour match, `benchmarks/speed.py`
the trackers' speed (`outputs/benchmarks/speed/side_holdout_4k.mp4` is a 4K test copy).
