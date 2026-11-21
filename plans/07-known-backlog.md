# Known backlog — what the code and the docs already say is left

Nothing here is a new finding: it gathers the deliberate shortcuts (`ponytail:` comments, 57 on 21 Nov) and the open
items scattered in `docs/state.md`, `docs/history.md` "Left, by value" and `docs/corrections_log.md` "Next", so that
they are weighed with the rest. "Pull forward" marks the ones another plan makes worth doing now.

Refresh the first list with:
`grep -rn "ponytail:" src web/src web/*.ts tests benchmarks install.sh pyproject.toml`

## Shortcuts in the code worth pulling forward

| Where | The shortcut | Why now | Plan |
|---|---|---|---|
| `src/volleyball_stats/files.py:4` | no `fsync` in the atomic write: a power cut may lose the last write | the answers log (`identity_answers.json`) is the owner's hours of review; SRV plan on writes | `os.fsync` the temp file before `os.replace` for the files that hold the owner's input only (answers, names, roster, club, publish): a `durable=True` argument, off for caches |
| `src/volleyball_stats/sync.py:255` | a machine pulling while another sends may get a half-written copy | two machines are in daily use; see LIVE-02/03 and the HOST plan | `pull` refuses (or waits, 60 s) while the server's record says `pushing`; `sync_remote` already holds the lock for `list` |
| `src/volleyball_stats/matches.py:795` | a match whose video is gone stops the update of all | today's state: two of four matches have "Vidéo absente" on the Mac | skip it, keep its hosted page, list it in the job's end ("N matchs sans vidéo : laissés") |
| `src/volleyball_stats/analysis.py:56` | one fingerprint for every step: a change to one step reruns them all | every "Réanalyser" after a code change costs the whole pipeline | a fingerprint per stage (its own module files + its inputs' stamps); see PIPE-22 |
| `src/volleyball_stats/jumps.py:56,109` | caches keyed by attack alone: delete by hand after changing constants | a silent stale cache hides a change from its benchmark (PIPE-15) | key the cache with `files.cache_stamp(video, [jumps.py], constants)` as `review.py:397` does for jerseys |
| `src/volleyball_stats/players.py:50`, `benchmarks/scale.py:25` | the offline pass holds every row in memory (~0.8 KB each, 2.9 GB of the 6.3 GB peak) | the memory peak decides which machines can run a match; also what makes a stop lose everything (PIPE-05) | rows appended to numpy chunks flushed to disk every N frames: halves the peak and gives a resume point |
| `src/volleyball_stats/players.py:108` | a hand-made fallback because ultralytics' trackers need `lap` | `uv tree` shows whether `lap` is now a dependency of the installed ultralytics | if it is, delete the fallback |
| `src/volleyball_stats/tables.py:57` | a read-only or full disk silently loses the cache | "why is it slow" has no answer in the app | `applog` a one-line warning once per run |
| `src/volleyball_stats/app.py:1085`, `pyproject.toml:23` | the flags and the script name of before 9 Nov kept "for the habits of then" | two weeks on, the launchers were rewritten | drop both once the owner's two machines start through `stats` (check `shortcut.py` rewrote them) |
| `src/volleyball_stats/video_copies.py:17` | a reading thread would save the pipe's share of the 28 min per hour of match | the encode is the longest wait of "Mettre en ligne" | measure first: `ffmpeg` time vs wall time on one 5-minute cut; only then the thread |
| `src/volleyball_stats/learn.py:222` | the learned order's training tells no progress | the rule "a progress bar moves only with counted work": its bar holds for minutes | print `::progress` per held-out set from `benchmarks/attribution/ranker.py`, read by `jobs.follow` |
| `src/volleyball_stats/web.py:986` | a match whose court is misplaced loses 3D, speeds, heights "without a word" | the owner's rule is UX first: a silent loss looks like a bug | a line in the review's header ("Terrain à replacer") opening the court dialog; no caveat on the public page |
| `web/src/lib/player.tsx:43` | one video per page: its time lives in a module-level store | blocks any second player (a compare view, picture-in-picture film) | leave until a second player is wanted |

## Shortcuts that are fine as they are

Accuracy limits with their upgrade path already written beside them, each waiting for data rather than code:
`contacts.py:22` (attack and block merged), `court.py:59,443`, `points.py:34,61,109`, `teams.py:154,184,227,334,417,452`,
`actions.py:48,85,102,114,128,179,184,356`, `rallies.py:61,188`, `jumps.py:277`, `identity.py:1044`, `match.py:460,636`,
`web.py:394`, `gesture_training.py:37,113`, `attribution.py:141` (O(tracks × contacts)), `defense.py:96` (20,160
pairings), `scoreboard.py:83` (O(n²) on a few dozen), `applog.py:49`, `matches.py:258,811`, the benchmarks' own
(`benchmarks/teams/bench.py:176`, `ball/candidates.py:186`, `corrections/doubts.py:6`), `Timeline.tsx:23`.

## Open items in the docs

From `docs/state.md` "Open":

- 3: the 3D ball's and TV mode's limits (`history.md` "The page").
- 4: rally ends with the ball out of sight or another court's whistle (F1 ±1 s 0.58 -> 0.67 with the play model on
  50:00-60:00), then how rallies end (in, out, fault): "the least reliable measure".
- 7: the pose's cost per touch on the 5080 (`history.md` "Left" 8).
- 9: the owner's plan, on hold: a job queue the two machines pull from, then logins and the review on the VPS.
- 14: the Match tab's four ways of saving -> every edit saved at once (designed in REV-04).
- 18: not looked at on a phone: 3D and TV mode on a real phone, the review, dark mode, "Mon match" with a player picked
  (this audit looked at dark mode and the review at 390 px in a headless Chrome: no horizontal scroll, no console error).
- 19: "Vidéo augmentée" not looked at: 50 fps on the 4K original, full screen with the court beside, dark mode, an
  iPhone, the review's own clips.
- 20: the 3D view in a VR headset (WebXR), needs a headset.
- 21: likeness ideas left: shoes' colour, leggings, long sleeves, glasses.
- 24: the Mac's encoding time untimed; the cuts through black and the ×2 breaks not watched on a full match.
- 31: after the gesture model, the players are the largest share of corrections (440).

From `docs/history.md` "Left, by value" (not settled): 3 (contacts the ball track misses), 5 (empty windows), 6 (same
player twice at identity level), 7 (ties to the bigger box), 8 (pose cost), 9 (the 8 automatic results corrected to
"play"), 10 (fewer close-call questions), 13 (the review's answers as benchmarks for types and rally verdicts).

From `docs/corrections_log.md` "Next": 2 (the ball unseen around a touch: 266 touches to add with no contact on the
four matches, the largest single source), 6 (the play model on someone else's footage).

## What to do with this file

Once the plans are worked through, fold what stays true into `docs/state.md` and delete this file: two lists of the
same open items drift apart.
