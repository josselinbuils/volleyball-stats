# Pipeline — improvements

One entry per finding, most valuable first. IDs are `PIPE-NN`.

Baseline: `uv run pytest -q` gives 1101 passed, 1 skipped (21 Nov). Experiments ran in the scratch folder on synthetic
videos and read-only on `outputs/matches/` (counts only).

## PIPE-01 A failed or stopped rerun orphans the answers keyed by rally

- **Type**: data-loss
- **Impact**: high — after one failed "Mettre à jour" / set change rerun, the next one leaves checked rallies, winners, ends and joins on keys no rally bears: the page silently drops them.
- **Effort**: M
- **Confidence**: confirmed for `rekey` (simulated below); read for the rest (`learn.rerun`, `match.py`'s write order).
- **Where**: `src/volleyball_stats/learn.py:268-300`, `src/volleyball_stats/match.py:605` (rallies.csv written before jerseys, scoreboard, identity, jumps), `src/volleyball_stats/rekey.py:75-79`, `src/volleyball_stats/web.py:203`
- **Problem**: `learn.rerun` copies the current `rallies.csv` to `before-rerun/` then runs `match.py`, which rewrites `rallies.csv` at its "actions" stage, long before it ends; `if run.returncode: raise` comes before the rekey. After a stop (`jobs.stop` kills the group), a crash or an out-of-memory, `rallies.csv` is new and `identity_answers.json` still names the old starts. The next rerun overwrites `before-rerun/rallies.csv` with the already-new file, so `rekey.moved(log, old, new)` gets `old` == the crashed run's windows and `key()` returns every unknown start unchanged ("one overlapping none keeps its key (the page then leaves its answers out)"). Only `learn.py` and `matches.MADE_SKIP` name `before-rerun`: nothing restores it.
  ```
  normal rerun  : [{'checked': [1040, 2980], 'winner': [{'start': 1040, ...}]}]
  after a crash : [{'checked': [1000, 3000], 'winner': [{'start': 1000, ...}]}]   # 1000, 3000 start no window
  ```
  Meanwhile the folder mixes the new `rallies.csv` with the old `actions.csv` (written last): `web.contacts` does `next(i for ... if start - lead <= frame <= end)` with no default, so a touch outside every new window raises while the page is built.
- **Plan**:
  1. `learn.rerun`: write `before-rerun/pending` before the subprocess, remove it after `review.save`. When it is there at the start, keep the saved `rallies.csv` and `review-data.js` (they still match the answers) instead of copying over them.
  2. Save with them the small files `match.py` rewrites before it ends (`rallies.csv`, `net.csv`, `tracks.csv`, `timeouts.csv`, `points.csv`) and copy them back when the run returns non-zero: the folder stays one run's.
  3. `tests/test_learn.py`: a fake `Popen` that rewrites `rallies.csv` and returns 1, then a second rerun that succeeds: the checked keys follow the windows.
- **Check**: the new test; by hand, stop an update mid-run in the app, start it again: the checked rallies stay checked.

## PIPE-02 The app's update breaks the tracked ranker weights it retrained

- **Type**: bug
- **Impact**: high — on any machine that retrained ("Mettre à jour") then updates the code after the weights changed upstream, `attribution_ranker.json` holds conflict markers and every match run crashes at `ranker.load()`.
- **Effort**: M
- **Confidence**: confirmed (git's behaviour reproduced in a scratch repo); read for the callers.
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): the facts hold: the file is tracked, the app's update retrained and the owner committed it by hand twice (b3907d5, 8b317f3), `app.update` runs `git pull --ff-only --autostash` and only checks the exit code (`app.py:741-743`).
- **Where**: `src/volleyball_stats/ranker.py:15,72`, `src/volleyball_stats/learn.py:223`, `benchmarks/attribution/ranker.py:152-153`, `src/volleyball_stats/app.py:741`, `src/volleyball_stats/analysis.py:60`
- **Problem**: `ranker.WEIGHTS = Path(__file__).with_name("attribution_ranker.json")` is tracked (`git ls-files`), one JSON line, and `learn.train` rewrites it (`ranker.py --write --if-better`). The app updates with `git pull --ff-only --autostash`. Same case in a scratch repo (local edit, upstream edit of the same line):
  ```
  Applying autostash resulted in conflicts.        exit 0
  <<<<<<< Updated upstream
  {"w":[2]}
  =======
  {"w":[3]}
  >>>>>>> Stashed changes
  ```
  Exit 0, so `app.update` reports success; `json.loads` then fails at `match.py:547`, and `analysis.fingerprint` hashes the markers. The owner's two machines hit it as soon as both retrain (the log shows the weights committed by hand after each update). The play and gesture weights avoid this: `outputs/learned/`, shared by the backup. The write is also not atomic (`WEIGHTS.write_text`).
- **Plan**:
  1. Retrained weights go to `outputs/learned/attribution/ranker.json` (`backup.SHARED` already carries `learned`), written with `files.write_text`; `ranker.load()` reads it when there, else the tracked file (the seed for a new install). `analysis.fingerprint` takes the one loaded.
  2. An override like `gesture.OVERRIDE` for the benchmarks (see PIPE-12).
  3. `tests/test_ranker.py`: the learned file wins; without it the seed loads.
- **Check**: retrain in the app, `git status` stays clean; `benchmarks/corrections score` unchanged with the same weights in the new place.

## PIPE-03 The near-touch identity is dropped by every apply and never reaches the page

- **Type**: bug
- **Impact**: high — the kept change "players-near" (288 -> 283 and 400 -> 389 corrections) exists only between a pipeline run and the first apply, and only in `actions.csv`: the page and the Match tab never show it, while the benchmark counts it.
- **Effort**: S
- **Confidence**: confirmed on the four real matches (counts below).
- **Where**: `src/volleyball_stats/match.py:628`, `src/volleyball_stats/identity.py:1072-1081,1181-1184`, `src/volleyball_stats/web.py:466-473`, `benchmarks/corrections/bench.py:161`, `src/volleyball_stats/learn.py:86,164`, `src/volleyball_stats/review.py:625`, `benchmarks/attribution/ranker.py:86`
- **Problem**: `match.py` fills `actions.csv`'s `identity` with `identity.touch_identity` (its only caller). `identity.rerun` (every review apply) rewrites the column with `finder(table)`, no fallback; `web.people.who` uses `finder` too. `benchmarks/corrections` scores `x["identity"]` right after `match.py`, so it measures a state the owner never sees. On the real folders (all applied since):

  | match | touches with a track | column differs from plain `lookup` | touches `touch_identity` would name |
  |---|---|---|---|
  | 29 Oct | 810 | 0 | 5 |
  | 2 Nov | 1002 | 0 | 12 |
  | 12 Nov | 1120 | 0 | 8 |
  | 16 Nov | 1190 | 0 | 4 |
- **Plan**:
  1. One finder for touches (`identity.touch_finder(table, fps)`: `finder`, then the nearest identified piece of the track within `NEAR_TOUCH_S`), used by `match.py`, `identity.rerun` and `web.people` for the contacts' `who` (the other lookups stay as they are).
  2. `benchmarks/attribution/ranker.py:86` labels with it too: today a right candidate on such a piece is no label.
  3. Tests: `tests/test_identity.py` (the column after `rerun` keeps the near identity), `tests/test_web.py` (the contact's person).
  4. `benchmarks/corrections score real` before and after an apply: the players' count must match the `players-near` run.
- **Check**: after an apply, the `identity` column equals `touch_identity` on every touch with a track (29 more touches named over the four matches) and the page shows the same players.

## PIPE-04 A failed ffmpeg leaves a short or empty `play.npz` stamped as done

- **Type**: bug
- **Impact**: high — the match then runs for good without the play model (or with half of it), silently: `wanted()` sees the weights' stamp and never runs the stage again.
- **Effort**: S
- **Confidence**: confirmed for the stream (below); read for `predict` and `wanted`.
- **Where**: `src/volleyball_stats/playing.py:162-174` (`frames`), `:177-185` (`predict`), `:140-147` (`wanted`); `src/volleyball_stats/play_training.py` reads the same stream into a cache kept by the video's size and time.
- **Problem**: `frames` never reads ffmpeg's exit code and has no processor fallback, unlike `decode.piped` ("one busy with other work may refuse another decoder"); on CUDA it uses `scale_cuda` without `decode.scale_cuda()`'s probe. In scratch: a 20 s clip gives 160 frames; the same file cut in half 73, no exception; a file ffmpeg cannot open 0, no exception. `predict` writes whatever came with `weights=stamp(folder)`.
- **Plan**:
  1. `frames`: after the loop, `if process.wait(): raise RuntimeError` with ffmpeg's last line; when nothing was sent and the GPU flags were used, start again on the processor (as `decode.piped`); choose `scale_cuda` only when `decode.scale_cuda()`.
  2. `predict`: with `seconds`, refuse to write under 98% of `seconds * FPS` frames.
  3. `tests/test_playing.py`: a truncated lavfi video raises; nothing is written.
- **Check**: the new test; `benchmarks/rallies/play_run.py` gives the same `play.npz` as before on a whole video.

## PIPE-05 Hours of tracking are lost on any stop: tracks live in memory until the last frame

- **Type**: feature
- **Impact**: high — 3.9 h (RTX 5080) to 7.8 h (M4) start over after a crash, a full disk, a reboot or a stopped job; the peak memory (rows of the whole match) is paid for the same reason.
- **Effort**: L
- **Confidence**: read.
- **Where**: `src/volleyball_stats/match.py:145-160` (`track`), `src/volleyball_stats/players.py` (`finish`, `stitch`), `src/volleyball_stats/decode.py:137` (`piped(first=)`)
- **Problem**: `positions` and `rows` grow for the whole video; `ball.csv` and `players.csv` are written after the loop only. Nothing on disk says where a run stopped.
- **Plan**:
  1. Every few minutes of video, append to `ball.csv.part` and a `players.part/NNNN.npz` chunk, with the last frame done and the video's stamp (size, time).
  2. At the start, with parts of the same video: decode from that frame (`piped(first=)`, two frames earlier for the ball's 3-frame window), a new player tracker with track ids past the last one; `players.stitch` (`MAX_GAP_S`, `MAX_SPEED`) joins the pieces cut there.
  3. Benchmarks: `benchmarks/ball` and `benchmarks/players` on a clip tracked whole and in two halves (same ball rows expected: to confirm `ball.track_frames` keeps no state past its window; identity switches for the players), `benchmarks/scale.py` for the memory.
- **Check**: kill `stats match` mid-tracking, start again: the PROGRESS line resumes where it was; the benchmark numbers above.

## PIPE-06 Nothing keeps the machine awake during a job

- **Type**: feature
- **Impact**: medium — an overnight run on a laptop stops at the idle sleep and is found unfinished in the morning (with PIPE-05, at zero).
- **Effort**: S
- **Confidence**: suspected — no `caffeinate`, `systemd-inhibit` or power call anywhere in `src/` (grep), docs silent; left to check: that the owner's Mac does sleep mid-run with its settings.
- **Where**: `src/volleyball_stats/jobs.py:383-392` (`run`)
- **Problem**: `jobs.run` starts each step with `subprocess.run([sys.executable, "-m", ...])` and nothing else.
- **Plan**:
  1. In `jobs.run`: on macOS prefix the step with `caffeinate -i` (in every macOS), on Linux with `systemd-inhibit --what=sleep` when `shutil.which` finds it. WSL2 sleeps with Windows: one line in `docs/running.md`.
  2. `tests/test_jobs.py`: the prefix per platform, none when the tool is missing.
- **Check**: `pmset -g assertions` shows the assertion while a job runs.

## PIPE-07 Without `outputs/lens.json` three kept changes are switched off silently

- **Type**: bug
- **Impact**: medium — a new user (no lens file: its calibration is a terminal command) gets no `by_flight` (height rule, `SET_OVER_S`), no ball width and no 3D places for the gesture model, with no word of it.
- **Effort**: M
- **Confidence**: read; the numbers on a court without lens are not measured.
- **Where**: `src/volleyball_stats/match.py:531,553,571`, `src/volleyball_stats/app.py:625-626`, `src/volleyball_stats/ball3d.py:57-82`, `docs/recording.md:101`
- **Problem**: `if calibration is not None and calibration.lens:` gates `actions.by_flight`, although `ball3d.flight_places` only needs `projection(calibration)`, which has its own branch without lens; line 550 already calls it ungated for the learned order. The app passes `--lens` only `if (OUTPUTS / LENS).exists()`, and the lens is made by `uv run python -m volleyball_stats.lens calibrate VIDEO` (against "every action is done in the app"). `Calibration.with_lens()` (pinhole) serves `film.py` only.
- **Plan**:
  1. Gate the three on `ball3d.projection(calibration) is not None` (width: keep the real lens if the measure needs it), after measuring: `benchmarks/corrections run` on copies whose court is refitted without lens (`bench.py run` needs a `--court` option), with and without the gates.
  2. In the import screen, a camera choice that copies `docs/lens_osmo_action3_standard_4k.json` to `outputs/lens.json` for that camera; the checkerboard calibration as an app step later.
- **Check**: the benchmark's corrections on the no-lens copies, before and after; a match made on a fresh `outputs/` shows `by_flight`'s retypes.

## PIPE-08 Seeking returns the frame before the one asked at 100 fps and more

- **Type**: bug
- **Impact**: medium — on 100/120 fps footage (the Osmo Action 3 records 4K at both) every pose, jersey crop, embedding, clip and picture cut after a seek is one frame early.
- **Effort**: S
- **Confidence**: confirmed.
- **Where**: `src/volleyball_stats/decode.py:141-142`
- **Problem**: `# Half a frame early` / `seek = ("-ss", f"{timestamps(video)[first] - 0.01:.6f}")`: 0.01 s is half a frame at 50 fps only. On lavfi videos, processor decode:
  ```
  50 fps:  (asked, got) [(7, 7), (40, 40), (91, 91)]              frames_at(91) -> 91
  100 fps: (asked, got) [(7, 6), (40, 39), (91, 90), (133, 132)]  frames_at(91) -> 90
  120 fps: (asked, got) [(7, 6), (40, 39), (91, 90), (133, 132)]  frames_at(91) -> 90
  ```
- **Plan**:
  1. `ts = timestamps(video)`; seek at `ts[first] - min(0.01, (ts[first] - ts[first - 1]) / 2)`: the same value at 50 fps.
  2. `tests/test_decode.py`: `frames_at` on a 120 fps lavfi video gives OpenCV's pixels at the frames asked.
- **Check**: the test; the scratch script above prints equal pairs.

## PIPE-09 A video without sound crashes the run after the tracking

- **Type**: bug
- **Impact**: medium — a recording with the microphone off, or re-encoded without audio, fails at "rallies" after hours of tracking, at every retry.
- **Effort**: S
- **Confidence**: confirmed for ffmpeg (exit 234, "Output file does not contain any stream"); read for the caller.
- **Where**: `src/volleyball_stats/rallies.py:138-154` (`read_audio`), `src/volleyball_stats/match.py:506`, `src/volleyball_stats/play_training.py:142`
- **Problem**: `if process.wait(): raise subprocess.CalledProcessError(...)`, uncaught in `match.py`. Whistles are one cue among others (`served`, the play model); `whistles()` already returns nothing for an audio under `FFT_SIZE`.
- **Plan**:
  1. `read_audio`: ask ffprobe for an audio stream first; without one return `np.zeros(0, np.float32)` and print one line.
  2. `tests/test_rallies.py`: a lavfi video made with `-an` gives no whistle and no error.
- **Check**: the test; `stats match` on a muted copy of a short clip goes through.

## PIPE-10 Constants counted in frames and a hard-coded 50 fps on the learning path

- **Type**: bug
- **Impact**: medium — on 25, 30 or 60 fps 4K footage the gesture clips span another duration than the model learned, and the app's retraining computes its features at the wrong rate.
- **Effort**: M
- **Confidence**: read. (`MIN_SPEED` / `MAX_SPEED` per second was tried and dropped, `benchmarks/rallies/README.md:296`: not proposed again.)
- **Where**: `src/volleyball_stats/gesture.py:34,56-59`, `benchmarks/attribution/ranker.py:61,87`, `src/volleyball_stats/identity.py:81`, `src/volleyball_stats/gesture_training.py:91,98`
- **Problem**: `OFFSETS = tuple(-21 + 3 * k for k in range(16))` are frames (-0.42 to +0.48 s at 50 fps), and `gesture.wanted` checks the height only. `ranker.py`'s `from_match` has `fps = 50.0` (gap, track age, `flight_places`) and `s0 - 50 <= t[0]`; it is what "Mettre à jour" runs (`learn.train`). `identity.BATCH = 90` frames. `gesture_training` calls `truth(folder, 50.0)`.
- **Plan**:
  1. `OFFSETS` from seconds (`round((-0.42 + 0.06 * k) * fps)`), `BATCH_S = 1.8`, `ranker.py` reads the fps of the video it is given, `gesture_training` passes the match's: identical integers at 50 fps (assert it in `tests/test_gesture.py`, `tests/test_identity.py`).
  2. Until footage at another rate is labelled, `gesture.wanted` and the learned order also ask for 50 fps within 10%, as they ask for the height: the rules run instead.
- **Check**: `benchmarks/corrections run` then `score --compare`: no change on the four matches.

## PIPE-11 `benchmarks/rallies/checked.py` no longer scores what `match.py` writes

- **Type**: tests
- **Impact**: medium — its numbers leave out the play model's five uses and the relances, so a rally change can look neutral or good there and differ in the pipeline.
- **Effort**: S
- **Confidence**: read.
- **Where**: `benchmarks/rallies/checked.py:1,49-54`, `src/volleyball_stats/match.py:506-563`
- **Problem**: its docstring says "Rally windows, as match.py writes them", but it calls `rally_windows`, `typed_windows`, `mark_dead` and `no_play` alone: no `playing.moved` / `added`, no set start or match end filter, no `alive` in `typed_windows` and `mark_dead`, no `mark_relances` / `by_flight`, no `kept` (`playing.confirmed`) in `no_play`.
- **Plan**:
  1. Make it score a folder's `rallies.csv` and `actions.csv` (the real one or a `benchmarks/corrections` run): about ten lines, nothing to keep in step.
  2. Say so in `benchmarks/rallies/README.md`.
- **Check**: on a `corrections` run folder its "touches" equals that run's "checked: touches found".

## PIPE-12 The learned order is held out by set, and the benchmark cannot swap its weights

- **Type**: tests
- **Impact**: medium — the `--if-better` gate judges weights on sets of matches they were fitted on, and a held-out `corrections` run means overwriting the tracked file by hand (`m3-heldout` in the log).
- **Effort**: M
- **Confidence**: read; whether the per-match gate decides differently is not measured.
- **Where**: `benchmarks/attribution/ranker.py:87,136-150`, `benchmarks/corrections/bench.py:67-91,250-252`, `src/volleyball_stats/ranker.py:72`
- **Problem**: `group = f"{match.name} set N"`: the other sets of the same match (same camera place, court, players, tracks) train the model that scores a set. The play and gesture models are judged on a match they did not see. `bench.py run` has `--play` and `--gesture` for held-out weights, nothing for the order.
- **Plan**:
  1. With three matches or more, the gate's groups are the matches (the sets' lines stay printed).
  2. `ranker.py --held MATCH --out DIR` writes weights fitted without it; `bench.py run --ranker PATH` sets the override of PIPE-02.
- **Check**: `ranker.py` on the four matches prints both hold-outs; `bench.py run x MATCH --ranker ...` leaves `git status` clean.

## PIPE-13 A stop while the gesture clips are cut loses all of them

- **Type**: performance
- **Impact**: medium — the stage's longest part (minutes on the 5080, far more on a Mac) starts over, since the index is written once at the end.
- **Effort**: S
- **Confidence**: read.
- **Where**: `src/volleyball_stats/gesture.py:162-208` (`clips`)
- **Problem**: the docstring says "a clip written in full before the index names it", but `keys[k] = len(keys)` only changes memory and `files.write_text(index, ...)` comes after the loop; the next call does `f.truncate(len(keys) * nbytes)` with the old keys and cuts everything again.
- **Plan**:
  1. In `write`, flush and write the index every 200 clips (the data file only grows, so the index stays true).
  2. `tests/test_gesture.py`: a decoder stub that raises after N frames, then a second call cuts only the missing clips.
- **Check**: the test.

## PIPE-14 No batch is retried smaller when the graphics card runs out of memory

- **Type**: bug
- **Impact**: medium — another program taking video memory mid-run (a film being made, a game, a browser) ends a multi-hour stage.
- **Effort**: M
- **Confidence**: read; no out-of-memory was reproduced.
- **Where**: `src/volleyball_stats/ball.py:30,109` (`BATCH = 16`), `src/volleyball_stats/playing.py:203-208` (batch 32), `src/volleyball_stats/gesture.py` (`scores`, batch 4), `src/volleyball_stats/identity.py` (`describe`, `CHUNK`)
- **Problem**: no `OutOfMemoryError` handling in `src/` (grep).
- **Plan**:
  1. One helper (`decode` or `ball`): run the batch, on `torch.OutOfMemoryError` empty the cache and run its two halves; used by the four flushes.
  2. `benchmarks/ball` and `benchmarks/rallies/play_run.py` at batch 16 and 8: the same outputs (to confirm under bf16 autocast).
- **Check**: a test with a model stub raising once: the same results, two calls.

## PIPE-15 Caches keyed by frame alone hide a change from its own benchmark

- **Type**: tests
- **Impact**: medium — changing a pose crop, the ball width's measure or a relance threshold reuses the old values, in the match folder and in every `benchmarks/corrections run` (the copy keeps them), which then reports "no change".
- **Effort**: M
- **Confidence**: read.
- **Where**: `src/volleyball_stats/attribution.py:221` (`wrists.json`, "frame:x:y"), `src/volleyball_stats/ballsize.py:82` (`ball_widths.json`), `src/volleyball_stats/actions.py:362` (`relances.json`, by frame), `src/volleyball_stats/jumps.py:56,109` ("delete the cache after changing ..."), `benchmarks/corrections/bench.py:69-70`
- **Problem**: none carries what made it; `jerseys.pictures_read` shows the pattern (`{"stamp": ..., "read": {...}}`). `files.cache_stamp` hashes whole sources and would throw 25 minutes of poses away at every edit.
- **Plan**:
  1. Each cache gets `"made"`: a hash of a tuple of the constants and the model name it depends on, declared beside them (`POSE_CROP`, `POSE_MODEL.name`, `BEFORE_S`, ...); another value empties it.
  2. A test per cache: a changed constant recomputes, an unchanged one does not.
- **Check**: change `POSE_CROP` in a scratch run: `wrists.json` is rebuilt and the benchmark moves.

## PIPE-16 The first run and every later apply use different embeddings

- **Type**: bug
- **Impact**: low — identities of a fresh run and of the first apply with no answer can differ at the thresholds, and a benchmark run differs from its own rerun.
- **Effort**: S
- **Confidence**: read.
- **Where**: `src/volleyball_stats/identity.py:256,292,295`
- **Problem**: fresh vectors enter `stored` as float64 (`sums[k] / counts[k]`), are saved as `np.float16` and read back as float16 values: only the first run sees full precision.
- **Plan**:
  1. `stored[keys[k]] = (np.float16(mean).astype(np.float32), ...)` when computed.
  2. `tests/test_identity.py`: `embed` twice (computed, then cached) returns equal arrays.
- **Check**: the test; `benchmarks/identity` unchanged.

## PIPE-17 Files of a match still written in place

- **Type**: bug
- **Impact**: low — a stop during the write leaves a truncated `teams.json` (then reported as "Not set starts"), `points.csv` or court file, which the review server may read meanwhile.
- **Effort**: S
- **Confidence**: read.
- **Where**: `src/volleyball_stats/teams.py:638`, `src/volleyball_stats/points.py:196`, `src/volleyball_stats/court.py:193`, `src/volleyball_stats/match.py:644`, `benchmarks/attribution/ranker.py:153,160`
- **Problem**: `path.write_text(...)` / `open(path, "w")` where the rest of the pipeline uses `files.write_text` and `files.replacing`.
- **Plan**:
  1. Use the two helpers at these six places.
- **Check**: `uv run pytest -q`; grep finds no `write_text(` on a match file outside `files.py`.

## PIPE-18 `relances_by_touch` reads the next rally's serve as "its own side plays on"

- **Type**: bug
- **Impact**: low — a second-touch relance that ends the rally becomes a "set" when the same side serves next.
- **Effort**: S
- **Confidence**: confirmed for the mechanism; the effect measured is small.
- **Where**: `src/volleyball_stats/actions.py:432-449`, `src/volleyball_stats/match.py:534`
- **Problem**: `before` and `after` cross the rallies (the function gets no rally index, floors skipped). `serve R, pass L, relance L, floor R | serve L, pass R` gives `['serve', 'pass', 'set', 'floor', 'serve', 'pass']`; the first rally alone keeps "relance". On the two matches whose reviewed page is on this machine, 20 rally-ending sets are followed by the same side's first touch: the owner left 14 as sets, made 3 attacks and 1 a relance.
- **Plan**:
  1. Pass each touch's rally (`rally_of`, as for `mark_dead`) and reset `before`, `count`, `after` at a rally's edge; `tests/test_actions.py` with the case above.
  2. `benchmarks/corrections run` then `score --compare`: keep only if the types do not lose.
- **Check**: the test and the benchmark's "type" count.

## PIPE-19 The frame rate is read from the video at every use and never checked

- **Type**: maintainability
- **Impact**: low — an unreadable or missing video gives fps 0: a `ZeroDivisionError` in `match.py`, zero-length windows elsewhere.
- **Effort**: M
- **Confidence**: read for `match.py:500,506` (`frame_count / fps`, while line 478 guards it); suspected for the review of a match whose video is not on the machine.
- **Where**: `src/volleyball_stats/match.py:452,500,506`, `src/volleyball_stats/identity.py:1180`, `src/volleyball_stats/learn.py:194,290`, `src/volleyball_stats/jerseys.py:80`, `src/volleyball_stats/scoreboard.py:106`, `src/volleyball_stats/play_training.py:138`, `src/volleyball_stats/gesture_training.py:63`
- **Problem**: `cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)` in a dozen places, 0.0 when the file cannot be opened.
- **Plan**:
  1. `match.py` stores `fps` and the frame count in `source.json`; `files.fps(match, video)` reads it, else the video, and raises a `ValueError` naming the video at 0.
  2. `match.py:452`: `parser.error` on a video with no frame rate.
- **Check**: a test of `files.fps` with a missing video; `stats match` on a text file renamed `.mp4` says what is wrong.

## PIPE-20 A model file cut short gives a raw loader error, and the checks call it present

- **Type**: bug
- **Impact**: low — a download cut by the network or Drive's quota page saved as weights stops the first match with a pickle or key error.
- **Effort**: S
- **Confidence**: suspected — left to check: whether `gdown` leaves a partial file under the final name.
- **Where**: `src/volleyball_stats/ball.py:74-83`, `src/volleyball_stats/identity.py:204-217`, `src/volleyball_stats/doctor.py:85-87`
- **Problem**: `if not path.exists(): gdown.download(...)` then `torch.load(path, ...)`; `doctor.models` counts `p.exists()` only.
- **Plan**:
  1. Each model with its size in bytes beside its path; `doctor.models` reports a wrong size as missing, and the loaders delete and download once more before failing with the file's name.
- **Check**: truncate a copy of a model in a scratch `models/`: the check lists it, the loader fetches it again.

## PIPE-21 Nothing notices a camera moved during the match

- **Type**: feature
- **Impact**: medium — a tripod hit by a ball or a player shifts the court for the rest of the match: places, sides, 3D and "in or out" go wrong with no sign.
- **Effort**: M
- **Confidence**: suspected — one calibration serves the whole video (`match.py:454`); left to check: whether any of the four matches drifts.
- **Where**: `src/volleyball_stats/court.py:426` (`match`: the stored court found on a new video), `src/volleyball_stats/match.py:454`
- **Problem**: no step compares the court's lines with the picture after the first frame.
- **Plan**:
  1. At "rallies", refine the court's landmarks on one frame per set start and at the end (the refine `court` already has for a stored court); a shift over a few pixels at 4K is told in the app, with the court to click again from there.
  2. `benchmarks/court`: a clip shifted by 10, 30 and 80 px halfway; the check must tell the three and stay quiet on the four matches.
- **Check**: the benchmark; no warning on the reviewed matches.

## PIPE-22 `analysis.fingerprint` does not see the base models nor the libraries

- **Type**: maintainability
- **Impact**: low — a new YOLO, WASB or OSNet file, or an upgraded torch / ultralytics, changes the results without "Nouvelles règles" on the matches.
- **Effort**: S
- **Confidence**: read.
- **Where**: `src/volleyball_stats/analysis.py:54-70`
- **Problem**: `parts = [*modules(), ranker.WEIGHTS]` plus the play and gesture stamps; the files of `doctor.model_files()` and `uv.lock` are not in it (`files.cache_stamp` does take `uv.lock`).
- **Plan**:
  1. Add the pipeline's model files by size and time (not their bytes: hundreds of MB). `uv.lock` only if the owner wants a rerun offered after each dependency bump.
- **Check**: `tests/test_analysis.py`: touching a model file changes the fingerprint.

## PIPE-23 `docs/pipeline.md`'s status is two matches old

- **Type**: docs
- **Impact**: low — a reader takes the third match for not reviewed and the numbers for current.
- **Effort**: S
- **Confidence**: read.
- **Where**: `docs/pipeline.md:33-44`
- **Problem**: "Two real matches ... processed and reviewed" and "A third match (12 Nov) is processed, not reviewed yet", while `docs/state.md:143-147` has four matches reviewed and the fourth held out (433 corrections).
- **Plan**:
  1. Replace the paragraph by a pointer to `docs/state.md` and the table of `docs/corrections_log.md`.
- **Check**: read both.

## Looked at, fine

- `contacts.detect`, `attribution.ranked` and `unreached` on a real match (253,499 frames, 2.5 M player rows): 2.9 s, 1.7 s, 1.5 s; the duplicate calls in `match.py` (`rallies.served` twice, `ranked` twice) cost seconds: not worth a change.
- Frame times: on a real match video the packets' timestamps stay within 0.023 s of `frame / fps` over 67 minutes (three chapter joins of about 10 ms): the pages' `t = frame / fps` holds.
- `decode.piped` at 50 fps, the processor fallback when the card refuses, `frames_at`'s runs and seeks (and their 17 tests).
- `teams.lefts` against the set starts the review writes (the middle of the break): no edge case at the bounds; `teams.settle` keeps `end` and `net`.
- `rekey.moved`, `found`, `added_rallies` on a run that succeeds; `rekey`'s 15 tests.
- `ball3d`: `projection`, depth, the lift term and the robust rounds; `flight_places` drops places outside the hall.
- `identity`: `covers`, `split`, `cannot_links`, `whiten`, `sharpen`, `follow`, `group`, `hold`, `fill_in`, `number`, `doubts`, `kept_cards`, `jersey_links`: no bug found.
- `scoreboard`: `parse`, `gaps`, `grid`, `steady`; the frames already read are kept. `jerseys`: `agreed`, `RARE`, the pictures' stamp.
- `timeouts`: answers in frames, kept through a rerun; `found`'s bounds.
- `jumps`: `flight`, `lift`, `hip_rise`, `run_up` (NaN and edge guards in place); `defense`: `layout`, `assign`.
- `playing.moved` / `added` / `confirmed` / `goes_on` on empty or one-clip inputs (guarded where the pipeline calls them); `play_training`'s held-out check.
- `tables`, `files.replacing`, `analysis.code` (comments and docstrings out of the fingerprint).
- `import_match` refuses an existing target: no stale tracks under a re-imported name.
- `benchmarks/corrections`: read-only on the real folders, `renames` with a warning for a player renamed since the freeze, `in_rally` for the bounces after a rally's end.
- `doctor.system()` knows mac, wsl and linux only, so `os.nice` / `os.getloadavg` / `ps` in `match.py` are within the supported systems.
- `MIN_SPEED` / `MAX_SPEED` per second: tried and dropped (`benchmarks/rallies/README.md:296`).
- Not reviewed in depth: `likeness.py`, `lens.py`'s calibration, `benchmarks/ball/finetune*.py`, `benchmarks/pose`, `speed.py`, `scale.py`, and the README of most benchmark steps.
