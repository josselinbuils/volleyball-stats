# Running and checking

## A match

- A new match starts with `import_match` (README): `data/MATCH/MATCH.mp4` and `outputs/MATCH/`, named like its hosted page, everything of a match in those two folders.
- `match` refuses to track at a low priority or on a busy machine (`slow_run_reasons`, `--anyway`): tell the owner what it lists, stopping their work
  (Docker, Kili sandboxes) is their call. To correct a running job: `sudo renice 0 -p PID...` in their own terminal (`renice -n 0` changes nothing on
  macOS). A run can't survive a restart: tracking writes nothing until it ends. Idle, the M4 tracks 4K at 2.87 MB/s (6 h for 84 min); progress is the
  `ffmpeg` read offset (`lsof -o`) over the file's size.

- `match` ends by making the review's page and pictures, for its first open to be quick; a failure there only warns. The review's reruns pass `--no-page`.

## Checking the page on the short clips

The page holds no video by default; `--footage full --club 1 --pictures` (saved in
`outputs/VIDEO/page.json`) brings back the video and the club's pictures for features that need them.

Then open `outputs/side_setend/site/index.html` (two sets) or `outputs/side_holdout/site/` (one
set). In browser checks mute the videos and check a phone width (no horizontal page scroll). The
"Analyse" columns stay empty on these short clips: lower `MIN_TRIES` in
`web/src/components/Stats/helpers/insights.ts` temporarily to see them, and restore it before the
build you commit. `benchmarks/scale.py` measures memory on a 2-hour match, `benchmarks/speed.py`
the trackers' speed (`outputs/speed/side_holdout_4k.mp4` is a 4K test copy).
