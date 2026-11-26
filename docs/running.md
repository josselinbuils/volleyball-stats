# Running and checking

## A match

- `uv run stats` (`app.py`) is the review server on the list of the matches, its `/app/` routes doing what
  used to need a command: `doctor.py`'s checks, the import, the court (`court auto --background`, else clicks and
  `court fit --out`), the pipeline (`match --players --anyway`, after the app's own busy check) and the update (`git pull --ff-only --autostash`, `uv sync --inexact`, a restart; refused
  while a job or an apply runs). It opens the page in a window of its own, `stats browser` in a browser tab, `stats server` nowhere (a restart); it refuses to start at a lowered priority (`app.lowered`: zsh's `bg_nice` on a background job, which its jobs would inherit and nothing without root undoes); `stats` alone stops once its last window closes (`--with-window`, `presence.py`: each page says it is open every 30 s and that it goes as it unloads; the first page given 2 min once the server listens (a review loads for 20-35 s, and from Windows a page polling a port not listening yet waits some 20 s per try: 60 s from the start stopped it, 18 Nov); 30 s for a reload or another match's review to come back, an apply's reload coming while the server still works; a page silent for 30 min is gone; never while a job, an apply or the pictures it leaves for later run), the restarts keeping it; else Ctrl+C or `uv run stats stop` stops it (`/app/quit`, refused while an apply runs); jobs go on. The long ones are jobs (`jobs.py`): a process of their own in a new session, their
  record and log in `outputs/jobs/`, so they outlive the server's restarts; a job, and the review's apply, keep the
  machine from sleeping on its own while they run, the screen free to (`awake.py`: `caffeinate -i` on macOS,
  `systemd-inhibit` on Linux, `SetThreadExecutionState` on Windows, under WSL2 through a hidden `powershell.exe` fed a
  byte every 30 s, gone 75 s after the last), and the job's screen says "Sur batterie : branchez l'ordinateur"
  on battery (a closing lid still sleeps most laptops); `match` and `import_match` tell their
  stages, the share done of the whole and of the stage, and the time left (`jobs.Stages`: `::progress SHARE part=P left=S`).
  Only counted work moves a bar (the owner's rule, 15 Nov): a stage tells its share (`share_of_stage`, `counter`;
  `jobs.parts`, `every`, `follow` for a child's `::progress` lines, `ffmpeg` for its time), else it holds; the stages weigh
  their last duration by second of video (`outputs/pipeline_timings.json`, `import_timings.json`), kept as the run started,
  and only by a run tracking the players anew (a run on the same tracks reads the last one's wrists, jerseys, embeddings
  in seconds: kept, its durations made the next import's time left hours short, 17 Nov).
  Before the analysis, the import's card says its time and end (`estimate.py`, `/app/state`'s `seconds`): those
  durations, else, on a new machine, the RTX 5080's scaled by this one's tracking pass timed at its first import
  (500 frames after 50 to warm up, 30 s at most, its own counted bar, kept in `outputs/speed.json`); "Laissez
  l'ordinateur branché et ouvert" on a laptop (`awake.laptop`), and past 24 s per second of video, that it is too
  slow and what would help. Diagnostics says the same for an hour of match.
  "Filmer un match" on the list (`GuideDialog`, also from the framing check) is recording.md for anyone: the camera's
  place drawn from above and from an end line (SVG, no footage), the settings by camera (the Osmo Action 3's by its
  menus, others' in general with "Calibrer la caméra"), what to bring as boxes to tick, what to do once.
  The framing (`placement.py`): "Tester le cadrage" on the list takes a few seconds filmed from the camera's planned
  spot, picked like an import, as a job (`placement test`: the picture without the players, its counted bar, then
  `court.find` among the stored courts); a new gym asks the clicks (`placement fit`, the court then stored for its
  matches). The answer is the court drawn (`court.check_image`: a line out of the picture goes on in red on a grey border)
  and what is out (an end line, a sideline, the far players' heads at 2.4 m) with what to change: back, turn, tilt, on the
  net's line, higher (the camera's place and heads only with its lens known: a guessed one puts it metres off). An
  import's card says the same before the analysis when its court could be framed better (`/app/state`'s `framing`).
  A stopped analysis (the Stop button, a sleep, a crash, the app closed) carries on where it was: the tracking pass
  keeps a part every 9600 frames (`resume.py`, `tracking_parts/`: the ball positions, the player rows, BoT-SORT's
  state and its next id, pickled; this machine's own, left out of backups and the hosted pages), started again it reads
  the parts kept under the same key (video, court, models, the tracking's code) and decodes from the next frame, the
  ball's 16 frames before it read again so its windows batch as before: its tracks byte for byte those of a run never
  stopped. The card says "Arrêté", its time for the rest and "Reprendre"; "Réessayer" only for a failure with nothing
  kept. A user's stop leaves the tasks' pill (no failure to tell).
  The bars show both shares, and slide when a job tells none. Every page of the app (the list, the review, the page at
  `/page`) shows the tasks running elsewhere in a pill in its corner (`Tasks.tsx`, `/app/tasks`: the review's apply and
  the jobs running or ended within 2 min), its panel each one's bar and a link to its screen, the share leading the
  window's title; a match's card in the list carries its own bar, and a task whose bar the page shows leaves the pill. A job is known by its process's boot and start ticks (`jobs.process_key`), else by `ps`'s start
  time (`ps lstart`, macOS) within 5 min: WSL2 resetting its clock once made a running analysis show as failed (13 Nov);
  after a restart, a reused process number is no job.
  A match being prepared shows above the list until its `report.md` exists; one whose pipeline a command ran and no
  process runs any more is offered to run again. Under WSL2 the import lists Windows' drives, a card plugged in after WSL
  started mounted when picked (`wsl.exe -u root mount -t drvfs`, no password), and the Windows downloads. "Vidéos…" and "Dossier…" open
  the system's own file window in front of the page to pick several videos or a folder (`app.pick`: Finder, Windows' under WSL2
  owned by a window kept on top, zenity or kdialog on a Linux desktop; no button without one); Windows' drives show by their
  name ("SD_Card (E:)"). The import plays the recording (the camera's own files, `/app/video` by byte ranges, chapter after
  chapter; HEVC needs a browser that decodes it, else the pictures of a slider), zoomed and full screen, above the two teams
  side by side as on the picture. The pictures to check before the analysis zoom too (`Zoomable`). A second start
  only opens the page.
  "Club" (on the list and in the review's "..." menu, `club_settings.py`, `outputs/club/club.json`) edits the one club
  every page shows (name, site, logo, colours, sponsors) and its teams; saved from a review, that match's pages are rebuilt at once, the others at their next build.
- Every `python -m volleyball_stats.X` command fetches in the background and warns when the branch is behind its remote
  (`git_check.py`; once per command, not in the ones it starts). The review and its list say it too, with "Mettre à
  jour" (`/app/update`).
- A match's results come from the other machine through the review's list ("À télécharger"), the Site tab's "Tout
  récupérer" or `sync pull`
  ([hosting.md](hosting.md)); its video is copied by hand (the app's video exchange was removed, 18 Nov).
- A new match starts with `import_match` ([processing.md](processing.md)): `data/matches/MATCH/MATCH.mp4` and `outputs/matches/MATCH/`, named like its hosted page, everything of a match in those two folders.
- `match` refuses to track at a low priority or on a busy machine (`slow_run_reasons`, `--anyway`): tell the owner what it lists, stopping their work
  (Docker, Kili sandboxes) is their call. To correct a running job: `sudo renice 0 -p PID...` in their own terminal (`renice -n 0` changes nothing on
  macOS). A run can't survive the machine's restart: tracking writes nothing until it ends.

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
`benchmarks/online.py` whether a change moved the online state of the matches (CLAUDE.md, "Check a change").
