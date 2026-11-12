# Fewer corrections in the review: work log

Started 11 Nov 2026. Goal (the owner's): less work correcting the automatic labels of a match.
This file is the hand-over: what was measured, tried, kept and dropped, and what to do next.
Read `state.md` and `next_steps.md` first for what was tried before 11 Nov.

## How the work is run

- 11 Nov: Claude Fable 5.2 planned and reviewed, Sonnet agents executed, each pipeline one in its own git worktree. 12 Nov: one
  session did the rest itself, no agents; the reruns one at a time (`flock /tmp/vb-rerun.lock`), two heavy jobs at most (WSL has 15 GB).
- The two reviewed matches in `outputs/matches/` are never written to: every rerun happens on a scratch copy.
- A change is kept only if the corrections it saves show on both matches (see "Harness").

## Where the corrections are (7 Nov, `learn.json`, before this work)

| Corrections left to the owner | First match (129 rallies) | Second match (150 rallies) |
| --- | --- | --- |
| Touches to add | 65 | 126 |
| Touches to remove | 45 | 71 |
| Types to fix | 91 | 117 |
| Players to fix (named ones) | 91 | 100 |
| Winners to fix | 11 | 18 |

## Harness (`benchmarks/corrections/`, 11 Nov)

    uv run python benchmarks/corrections/bench.py freeze            # once: the checked rallies' truth, frozen
    uv run python benchmarks/corrections/bench.py run NAME          # scratch copy + `learn.rerun` with today's code (3 min a match)
    uv run python benchmarks/corrections/bench.py score NAME --compare baseline
    uv run python benchmarks/corrections/breakdown.py NAME          # the errors by cause, `outputs/benchmarks/corrections/breakdown.md`

Everything lands in `outputs/benchmarks/corrections/MATCH/` (`truth.json`, `runs/NAME/`); the real match folders are only read.
A pipeline run writes nothing outside its `--out` (checked by a file snapshot before and after).
`score real` gives the real folders as they are: it matches `learn.json`'s 7 Nov numbers on the second match; on the first, 10 touches
left the reviewed page since and the names moved (880/945 found, 686/770 players).

## Baseline: today's code, run `baseline` (11 Nov, commit ed91e85)

| | First match | Second match |
| --- | --- | --- |
| Touches found | 880/945 | 1102/1199 |
| Pipeline touches kept | 871/917 | 1094/1167 |
| Types | 789/880 | 972/1102 |
| Named players | 686/770 | 850/953 |
| Winners | 120/128 | 138/145 |
| To add | 65 | 97 |
| To remove | 46 | 73 |
| Types to fix | 91 | 130 |
| Players to fix | 84 | 103 |
| Winners to fix | 8 | 7 |
| **Corrections** | **294** (2.28 a rally) | **410** (2.73 a rally) |
| Rallies needing none | 34 of 129 | 38 of 150 |

The second match's real folder (429 corrections) predates the 5 Nov rally fixes: a rerun alone brings 410.

### Where they come from (first / second match)

- To add (65 / 97): outside every rally window 26 / 53; ball seen under half of ±0.4 s 19 / 25; ball seen, no contact 15 / 12;
  contact found, no player at the ball 5 / 6. By type: attacks 19 / 29, sets 13 / 18, digs 7 / 18, serves 7 / 11.
  The second match: one rally whose window holds its last 1.3 s of 31 s (18 to add), two checked rallies with no window.
- To remove (46 / 73): relance 11 / 13, attack 10 / 11, dig 5 / 17, block 3 / 12, serve 8 / 3. 23 / 34 are 0.2-0.5 s from a real
  touch (seen twice, or a timing slip that also costs a touch to add: 18 / 6 of those to add are under 0.5 s from a pipeline touch).
- Types (91 / 130), truth -> pipeline: attack -> set 10 / 15, attack -> relance 10 / 8, relance -> attack 8 / 15, block -> attack 8 / 8,
  relance -> set 8 / 6; second match dig -> floor 14, dig -> relance 11; first match pass -> floor 7.
- Players (84 / 103): another named player 73 / 83, unknown 11 / 17; same team 68 / 92; the type wrong too on 25 / 20.
- Winners (8 / 7): last touch right, result wrong 6 / 4; another last touch 2 / 0; no window 0 / 3.
- 10 worst rallies: 85 of 294 and 149 of 410 corrections (one 79 s rally of the second match: 33).

## Steps

1. Done: the harness, the baseline and the breakdown above (a Sonnet agent, 14 min).
2. Done (11 Nov), four Sonnet agents, the pipeline ones each in its own git worktree (`outputs`, `data`, `models` linked, main's `.venv`
   with `PYTHONPATH=src`), reruns one at a time (`flock`, 15 GB of RAM):
   - windows: done, nothing kept ("Tried and dropped");
   - false touches: done, nothing kept ("Tried and dropped");
   - types: done, one rule kept ("Kept"), the rest in "Tried and dropped";
   - ball: a training set to fine-tune the ball model on the two matches (the ball is about 4 px wide at the model's 512x288;
     the same model size, so no slower on either machine), labels from the reviewed touches' flights: dropped end to end.
3. Done (12 Nov): the models the owner asked about on 11 Nov ("do we use the best models?"): re-identification dropped, the
   play / no-play model kept, a learned touch type not wired in, the pose comparison (see "State").

## Kept

| Change | First match | Second match |
| --- | --- | --- |
| A set crossing the net within 1.3 s of its touch is an attack, or a relance by its flight (`actions.SET_OVER_S`, `by_flight`; runs `types-setover`) | 294 -> 288 (types 91 -> 85) | 410 -> 400 (types 130 -> 119, players 103 -> 104) |
| A touch on a piece of track with no identity takes its track's nearest identified piece within 5 s (`identity.touch_identity`; runs `players-near`) | 288 -> 283 (players 84 -> 79) | 400 -> 389 (players 104 -> 93) |
| A play / no-play clip model, where its weights are: ends carried on, starts pulled back, the windows with play all along kept, a rally going on after a bounce played on (`playing.py`; runs `play-eskb`, the model held out) | 283 -> 281 (to add 65 -> 62, types 85 -> 82, players 79 -> 81) | 389 -> 351 (to add 97 -> 62, types 119 -> 105, players 93 -> 103) |

The play model (12 Nov, `benchmarks/rallies/README.md` "12 Nov: the play model in the pipeline", each use measured alone): the
players to fix rise because 12 and 55 more named touches are found (10 and 45 of them given to the right player). Both matches
have rallies where the ball bounces and play goes on (27 and 38 such floors in the reviewed touches): a floor used to end the
rally's touches, turning the rest into floors (one 31 s rally of the second match: 23 corrections -> 9). Weights in `models/play/`
(345 MB, trained on both matches, not in the repository): the PC has them, the Mac runs as before without them.

The touches on a piece with no identity were asked in the review as unknown players: they now come with a guess, right 16 times
in 20 on the two matches; the rule fits no number to them. How those guesses show in the review was not looked at.

The slower sets over the net (1.4 s or more) stay sets, as the owner calls them. The threshold comes from 65 sets over the net on
the two matches (none between 1.3 and 1.4 s): to check on the third match. The school clips' actions benchmark does not run
`by_flight` (no camera model), so it is unchanged by construction; its ball tracks are not on this machine.

## Tried and dropped

### The fine-tuned ball model, end to end (11-12 Nov, second match, model A trained on the first only)

Model A (`benchmarks/ball/finetune.py`; WASB fine-tuned on the first match's labels, the same size and input) finds 99.4% of
the second match's labelled balls against 81.3%, 97% of those only the 1024 teacher saw, median error 2.9 px against 4.3
(`finetune_eval.py`, at 0.2; 97.9% at 0.5). The whole second match re-tracked (`finetune_track.py`, resumable, about 55 min
alone) and rerun (`bench.py run --ball`), against today's 389:

| Run | To add | To remove | Types | Players | Winners | Total |
| --- | --- | --- | --- | --- | --- | --- |
| `players-near` (today) | 97 | 73 | 119 | 93 | 7 | 389 |
| `ball-A`: model A at 0.5 | 212 | 79 | 115 | 91 | 13 | 510 |
| `ball-A07`: at 0.7 | 257 | 56 | 82 | 80 | 15 | 490 |
| `ball-A-fill`: today's track, its frames with no ball inside the rally windows filled from A | 164 | 84 | 151 | 82 | 7 | 488 |
| `ball-A-in`: A's positions inside the windows, today's elsewhere | 205 | 70 | 117 | 86 | 11 | 489 |
| `ball-A-fill-tail`: the fill, to 2.5 s after each window | 156 | 90 | 152 | 86 | 7 | 491 |

With `ball-A`: touches lost for "ball seen under half" 25 -> 7, but "outside every window" 53 -> 142 (8 checked rallies with no
window) and "ball seen, no contact" 12 -> 39 (22 serves). The steps after the tracker rest on its habits: it only sees a
flying ball, so a ball-track run is a rally and a ball appearing is a serve. The fill keeps today's windows and serves and
still loses 67 touches: my reading (not checked contact by contact) is that touches are also found from the ball vanishing
near the hands (`contacts.hidden_contacts`) and from thresholds set on this track's jitter.
What it would take: contacts found again for the new track, e.g. a detector trained on the 2,150 reviewed touches (the
ball's path and the players around it); large and uncertain, today's finds 92% of the touches. Not started. The mirror
(model B on the second match, the first re-tracked) was not run: nothing gained to confirm.

The training set (11 Nov; `benchmarks/ball/finetune_data.py`, `finetune_labels.py`, `finetune_audit.py`;
`outputs/benchmarks/ball_finetune/MATCH/`, 19 GB a match):

- Frames as the pipeline feeds the model (`decode.piped` at 1280x720, then `ball.preprocess`), 57 and 64 rallies spread over
  the match, 29 and 32 clips between rallies: 45,258 and 44,521 frames. Against `ball.csv`: the ball in the same frames 99%,
  within 8 px at 4K 99.5-99.7%.
- Two teachers' candidates a frame: the model as the pipeline runs it, and the same fed 1024x576 (stride 3: its forward was
  the bottleneck, 79 windows a second).
- Labels (`labels.csv`): per flight between two reviewed touches, RANSAC then least squares on both teachers' candidates, a
  cubic in time from 25 frames (median residual 3.5 px), a quadratic under; tolerance 45 px (the ball is 35-55 px wide at
  4K, about 6 px at 512); a flight accepted with inliers on 40% of its frames, in 3 of its 4 quarters, a path of 100 px or
  more: 450 of 472 and 404 of 422 flights. `ball` 25,598 / 23,697 (65% / 62% of rally frames; 22% / 19% of them only the
  1024 teacher saw), `unsure` 1,637 / 1,454, `offscreen` 484 / 141, `skip` 11,739 / 12,829; between rallies, the model's
  own picks (`clip_ball` 1,584 / 1,278, `clip_none` 4,216 / 5,122).
- Audit by eye (`audit/*.png`): `ball` labels only the 1024 teacher saw 59 of 60 on the ball (1 cannot tell), both teachers
  30 of 30; `unsure` 31 of 40 with the ball there; the model's picks off the path (2.6% / 2.0% of its picks) 16 of 30 false
  (shoes, arms, another ball), 14 the real ball: those frames are left out of the training.

Ball, first test on the second match (model A, trained on the first only; `weights/eval_A_M2.log`), at the threshold 0.2:
labelled balls found 99.4% against 81.3% (97% of those only the 1024 teacher saw), median error 2.9 px against 4.3;
detections in the wrong place 71 against 1, and on 1,160 of 5,122 frames between rallies where the model in use sees none
(252 at 0.5, with 97.9% found): both near zero for the model in use by construction (the labels come from its picks). The
agent re-tracks the second match at 0.5.

### Players (11 Nov, `next_steps.md` "Players to fix (11 Nov)")

The 188 wrong players (first / second): the touch is another one, its type wrong too 25 / 22 (18 are a block credited to the
attack beside it); a wrong pick, the right player among the first two candidates 30 / 36; the right player a later candidate
or none 6 / 12; no track carrying the right player at that frame 23 / 34 (a wrong identity, or a toucher the tracker lost:
not told apart; 5 serves a match). No runs: 81 and 102 distinct track pieces. In 59 of 97 wrong picks the ball lies inside
the picked box, the real toucher 0.4 box heights away: two players in line with the camera.

| Idea (right players of 761 / 945 named touches with a candidate, one match trained, the other tested) | Result |
| --- | --- |
| The learned order trained on the other match's checked touches (770 / 953 instead of about 180 answers) | 686 / 850 against 687 / 849 as shipped |
| With the pose (both wrists, elbow, the pose's box), the move toward the ball, the box seen | 687 / 844 at best |
| With the candidate's distance to the ball's places around the contact | -3 to +11 over the two, by the window: noise |
| One identity not twice in a row, the touches decoded together (20 / 24 such pairs, the second wrong in 13 / 19) | +3 / +2 at best, offline only |
| A short piece given its track's neighbours' identity | the neighbours agree with it (2 of 420 differ) |

Out of reach: two players in line (a perfect order would give 729 / 905: a depth cue, the ball's size or the players in 3D),
the wrong identity pieces (the identity step keeps 77% of the held-out answers: a better re-identification).

### Types (11 Nov, `next_steps.md` "Types to fix (11 Nov)")

Of the 221 wrong types, 20 are a block the pipeline never saw (one touch serving an attack and a block 0.2 s apart: a touch to
add, counted as a type), 24 follow a wrong team, 26 a false touch just before: 151 are the typing's own.

| Idea | Result |
| --- | --- |
| Attack or relance from the height, the rise, the ball above the head, its rise in the picture, in grids | the rule in place (2.1 m, 6 m/s) is at the best on both matches (±3); trees of depth 1-3 lose 3-10 held out |
| The last touch typed floor made a pass or dig by the ball's height over the nearest player's feet | AUC 0.75 but overlapping: at 0.9 box heights 3 touches for 3 floors (first), 8 for 4 (second) |
| A first touch after the other team's attack, typed relance, made a dig | the owner calls the same flights relance 7 of 9 (first) and dig 8 of 14 (second) |
| A learned model | not built: no other cell has a signal to learn |

Out of reach: the missed blocks (detection: a second contact within 0.2 s), floor or touch (the hand on the ball), dig or
relance (meant or not: "The owner's answers").

A learned type from the gesture (11-12 Nov, `benchmarks/actions/README.md` "A learned type from the gesture"): a clip around
each contact, one match trained and the other tested. Alone every model is far under the rules; stacked with the rules' type
and features, a fine-tuned VideoMAE gains 16 and 15 right types (the bar: 15 on each), the other variants 0 to 14. With the
play model in, which fixes some of the same floors: 14 and 12, under the bar. Not wired in; none tells a false touch. To try
again with a third reviewed match.

### Rally windows (11 Nov, `next_steps.md` "Tried and dropped (11 Nov)", runs `win-whole`, `win-whole2`, second match only)

The 79 touches outside every window (first 26 / second 53): the rally's last 1-3 touches after the window's end 26 / 29 (the
ball seen under 30% of the time in 4 of 5 of those tails; 5 / 6 of them after a whistle that closed the window mid-rally); the
window starting late 0 / 23 (three rallies of 18, 5 and 3 touches whose server stays behind the end line after serving, so
`served` sees no serve); no window 0 / 2 (serve faults with the ball unseen).

| Idea | Result |
| --- | --- |
| A whistled serve holding windows that start over 8 s after it becomes one window | second match 410 -> 412 (the 31 s rally then dropped by `no_play` / `mark_dead`: its low touches near the camera type "floor") |
| A "floor" the ball crosses the net within 2 s after is a low touch | second match 410 -> 429 (to add 97 -> 126, winners 7 -> 15: 8 windows lost) |

Not run: the first match on either idea (the second already lost), the school clips' rally benchmark (their ball tracks are not
in `outputs/`). Out of a rule's reach: the unseen tails (about 40 touches: the ball model), the mid-rally whistles (11: a chain
of 3+ contacts follows 100+ real whistles a match too), the server staying behind the line (23: a serve found from the ball
leaving the server, and `mark_dead` not killing a long rally; a larger change, not tried).

### False touches (11 Nov, offline on the `baseline` runs, no rerun: no rule came close)

What they are (first / second match): 0.2-0.5 s from a real touch 23 / 34, of which a second touch on one the pipeline also
has 14 / 31 and the real one mistimed 9 / 3; no real touch within 0.5 s 23 / 39.

- The main double: a "block" 11 frames (`contacts.GAP` + 1) after a rightly timed attack, across the net: 5 of 14 and about 12 of 31.
  Real blocks at that spacing outnumber them (about 11 real for 1-3 false, 17 for 9): the turn's strength, the ball's direction
  and track jumps do not tell them apart.
- 5 of the first match's 9 mistimed are serves the owner placed 15-36 frames after the ball's first sighting, the ball already
  flying: the truth's time, not a slip (1 on the second).
- Those far from any real touch: often 2-4 relance/dig/set touches between the real attack and the floor; the ball is seen less
  around them (median 0.6-0.7 of ±0.4 s against 1.0) and its track jumps more (p90 270-810 px against 46), but both hit real touches.

| Rule (false removed for real lost) | First match | Second match |
| --- | --- | --- |
| Ball seen under 30-80% of ±0.4 s | 0 for 12 up to 13 for 143 | 4 for 19 up to 48 for 151 |
| A track jump over 80 px near the contact | 7 for 12 | 11 for 14 |
| One track twice within 0.6 s, the second dropped (23 pairs, one false in 17) | 5 for 6 | about 5 for 3 |
| A touch under 1.6x the threshold | 8 for 18 | 28 for 30 |
| A block under 1.25x the threshold | 0 for 0 | 6 for 3 |

Out of a rule's reach: the block after an attack needs the blockers' hands at the net (pose) or a learned filter; the rest a
better ball track.

## The owner's answers

- The Mac (11 Nov): the pipeline must still run on it end to end, but it may be a different one, a bit less accurate. So a
  stage with a heavy model or fine-tuned weights falls back to today's behaviour where they are missing (the guard the
  agents already build), and what the Mac's pipeline loses is said each time. One path for both when the results are close.
- Runtime (11 Nov): the pipeline got much faster, so a model taking more time is fine if it is clearly better; candidates
  that only run on the PC or carry another licence are tested too, and reported for the owner to decide.
- A first touch after the other team's attack that sends the ball straight back over (11 Nov): a relance when the player
  meant it, a dig when not. So no single type for it: only a cue of intent could retype it (how hard the attack came in,
  arms above the head or a low forearm save; not tried, 23 such touches on the two matches, relance 13, dig 10).

## State (12 Nov, midday)

Today's code with the play model's weights: 281 and 351 corrections (294 and 410 at the start, 283 and 389 on 11 Nov).
Three changes kept, all merged. The four agents' work of 11 Nov was finished on 12 Nov:

1. Re-identification, end to end: dropped ("Tried and dropped").
2. Rally ends: the play model, kept ("Kept"). The agent's other candidates (a stronger and a lighter video model, an audio
   whistle score: `play_candidates.py`, `play_audio.py`, never run) were not pursued: copies in `outputs/benchmarks/play/scripts/`.
3. Touch types from the gesture: at the bar on the pipeline of 11 Nov, under it with the play model: not wired in
   ("Tried and dropped", `benchmarks/actions/README.md`).
4. Pose: eight models compared with YOLO11m-pose on the same crops (`benchmarks/pose/README.md`; larger YOLO11 and YOLO26,
   RTMPose, RTMW, ViTPose, Sapiens): who touched the ball moves by 4 or less with the learned order (one +8), jumps and
   attack or relance stay level. None gains offline, so none went through the harness: YOLO11m-pose stays.

The agents' worktrees are removed. On disk, not in the repository, to delete when no longer wanted: `outputs/benchmarks/pose/`
(46 GB), `ball_finetune/` (38 GB), `bench/play/` (22 GB of frames), `act/` and `act-play/` (11 GB each), `reid/` (18 GB), and the
candidates' weights in `models/pose_candidates/` (7 GB) and `models/reid_candidates/` (2 GB): about 155 GB.

Runs: `ls outputs/benchmarks/corrections/*/runs/`.

## Re-identification: the models compared (11-12 Nov), dropped end to end

The same cached crops for every model (about 4 a piece, so OSNet scores a little under its usual 12). "Kept": the review's
held-out answers kept by the identity step (`benchmarks/identity/answers.py`); rank-1 and AUC: same or another player within
a team, pieces 120 s apart or more (181 and 133 queries).

| Model | Licence | First match kept (of 565) | rank-1 / AUC | Second match kept (of 338) | rank-1 / AUC | Embedding, min a match |
| --- | --- | --- | --- | --- | --- | --- |
| OSNet-AIN as today (12 crops) | MIT | 422 (74.7%) | | not reproduced | | 5.4 / 6.2 |
| OSNet-AIN (cached crops) | MIT | 410 (72.6%) | .80 / .76 | 238 (70.4%) | .77 / .85 | |
| PersonViT-S, MSMT17 (a third party's port) | Apache-2.0 | 437 (77.3%) | .89 / .90 | 259 (76.6%) | .76 / .91 | 0.8 |
| CLIP-ReID ViT-B/16, Market-1501 (ONNX, 345 MB) | MIT | 442 (78.2%) | .91 / .85 | 262 (77.5%) | .88 / .92 | 3.3 |
| SigLIP base | Apache-2.0 | 433 (76.6%) | .85 / .85 | 251 (74.3%) | .80 / .90 | 1.2 |
| DINOv2 small | Apache-2.0 | not run | .74 / .75 | 243 (71.9%) | .64 / .77 | 0.7 |
| DINOv2 base | Apache-2.0 | not run | .69 / .75 | 249 (73.7%) | .62 / .76 | 1.5 |
| PersonViT + CLIP-ReID | | 438 (77.5%) | .88 / .89 | 265 (78.4%) | .84 / .91 | |
| PersonViT + OSNet | | 434 (76.8%) | .85 / .84 | 256 (75.7%) | .75 / .88 | |
| CLIP-ReID + OSNet | | 432 (76.5%) | .84 / .79 | 233 (68.9%) | .80 / .87 | |

PersonViT and CLIP-ReID lead on both matches; DINOv2 does not beat OSNet; joining a model to OSNet does not help. The
weights' training sets (MSMT17, Market-1501) are research-only, as OSNet's in use already are. PersonViT and SigLIP and
DINOv2 run on both machines; CLIP-ReID was run with ONNX on CUDA, the Mac not checked; no time measured on the Mac. No
SOLIDER or TransReID weights found to test. The "77%" of the docs was not reproduced: today's code gives 74.7% on the first
match; on the second, OSNet's own cache lacked pieces and a decode error stopped it.

End to end (12 Nov, runs `reid-*`: the match rerun with the candidate's vectors in `embeddings.npz`, the code of the worktree
with `identity.DIM` read from `REID_DIM`, since removed):

| Vectors | First match | Second match |
| --- | --- | --- |
| OSNet, today (`players-near`; the control `reid-orig` the same) | 283 (players 79) | 389 (players 93) |
| PersonViT | 279 (players 75) | 393 (players 97) |
| CLIP-ReID | 280 (players 76) | 443 (players 147) |

Neither gains on both: not kept. CLIP-ReID's 147 holds 51 touches of one player left with no name on the second match (the
names given in the review no longer land on one of its identities); 96 without them. The candidates' caches lacked 13 of the
second match's 20,983 pieces: given empty vectors, and OSNet with the same 13 emptied scores 389 too (`reid-orig-z13`). The
runs of 11 Nov under these names were invalid (the rerun's subprocess imported the main checkout's code) and deleted. What
the offline scores promised (about 77% of the held-out answers kept against 70-73%) does not reach the touches: most wrong
players are a wrong pick among the candidates at the ball, not a wrong identity ("Players"). Scripts:
`outputs/benchmarks/reid/scripts/` (`e2e.py`, and `reid_all.sh` for the order of the runs).

## Next

What is left with the play model in (run `play-eskb`, first / second match: 281 / 351), `breakdown.py`:

- To add (62 / 62): the ball seen under half of ±0.4 s 30 / 39; ball seen, no contact 16 / 13; outside every window 8 / 2
  (26 / 53 before); a contact with no player at the ball 5 / 6.
- To remove 47 / 74, types 82 / 105, players 81 / 103, winners 9 / 7.

1. A third reviewed match: the touch-type model and the play model both train on about 900-1,200 touches and 130-150 rallies
   a match, and every threshold here was set on two matches.
   The owner films one on 12 Nov. Once it is reviewed, in this order:
   - before any retraining, `bench.py freeze` then `bench.py score real` on it: the first numbers on a match nothing was tuned
     or trained on (the play model's windows, `actions.SET_OVER_S`'s 1.3 s, the touch on a nameless piece of track);
   - then the play model and the touch-type model trained on two matches and tested on the third, each way round, and
     the final play weights trained on the three.
2. The ball unseen around a touch (69 touches to add): the fine-tuned ball model finds it (99% of the labelled balls against
   81%) but the steps after it rest on today's tracker's habits ("Tried and dropped"): contacts found again for its track.
3. The block right after an attack (20 missed, about 17 made up over the two matches): the blockers' hands at the net.
4. The play model on the Mac (weights not copied, never run on MPS) and retrained with each reviewed match.
