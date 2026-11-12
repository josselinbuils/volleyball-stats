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
| A touch typed block over 1.6 m from the net is none, dropped once the touches are typed (`actions.off_net_blocks`; run `block-net` against `ctl`, 12 Nov) | 281 -> 279 (to add 62 -> 63, remove 47 -> 46, types 82 -> 81, players 81 -> 80) | 351 -> 345 (to add 62 -> 65, remove 74 -> 68, types 105 -> 103, players 103 -> 102) |

The play model (12 Nov, `benchmarks/rallies/README.md` "12 Nov: the play model in the pipeline", each use measured alone): the
players to fix rise because 12 and 55 more named touches are found (10 and 45 of them given to the right player). Both matches
have rallies where the ball bounces and play goes on (27 and 38 such floors in the reviewed touches): a floor used to end the
rally's touches, turning the rest into floors (one 31 s rally of the second match: 23 corrections -> 9). Weights in
`outputs/learned/play/` (345 MB, trained on both matches, not in the repository), shared between the machines by the backup.

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

### The fine-tuned ball model's contacts added to today's (12 Nov, evening; both matches, each tracked by the model trained on the other)

Today's track kept for everything; the contacts the fine-tuned track finds (`contacts.detect_contacts` on it) added where today's
sees the ball in under half of ±0.4 s and has no contact within `GAP`. Model B (trained on the second match, 45 min) tracked
the first (`ball_B_M1_t05.csv`, at 0.5, 55 min); model A's track of the second as above. Runs `ctl` (today's code with the
held-out `play.npz`, `bench.py run --play`: 281 / 351, as `play-main`) and `extra-*`:

| Variant | First match | Second match |
| --- | --- | --- |
| Every such contact (`extra-A0.5`; 1.01: every one, whatever today's sees, 361) | | 351 -> 354 (to add 62 -> 30, remove 74 -> 93, types 105 -> 111, players 103 -> 114) |
| Today's gaps filled from the fine-tuned track within 0.5 / 1 s of each contact, for every step after the contacts | | 366 / 363 (players 107, types 126 / 123) |
| Filtered (`extra-filt`): not a contact hidden in a gap, a turn under 2.5 times `THRESHOLD`, the ball by a player's head (from 0.25 box heights under the box's top to 1 above, within 0.8 box heights of the box) | 281 -> 284 (add 62 -> 45, remove 47 -> 55, types 82 -> 87, players 81 -> 88) | 351 -> 343 (add 31, remove 83, types 110, players 113) |
| Filtered, the gaps filled within 1 s for the players' order only (`ball3d.flight_places` of the learned order; `extra-filt-places`) | **281 -> 280** (players 84) | **351 -> 335** (players 105) |
| The same, the extras 0.5 s or more from any contact (`extra-apart`) | 283 | 336 |

The filter was set on the second match's 60 extras in its checked rallies (real 35, false 25: real ones by a head, turns 369-806
px/s but one; false ones low, at the feet, or a track jump): offline it keeps 34 of 35 and 7 of 25 there, 18 of 22 and 6 of 35 on
the first match. End to end the extras find 17 and 31 touches, but each found one brings about half a correction back: a type
(6 of 17 on the first), a player (the players' order reads the flight from today's track, empty there: fixed in part by the
fill) and the false ones (8, half of them 0.1-0.5 s from a real touch).

Not wired in: -1 on the first match is no gain, and it costs a second ball pass a match (about 55 min on the 5080, more on the
Mac) and the fine-tuning of the ball model in "Apprendre de mes réponses" (the labels' frames, 19 GB a match, then 45 min). To
decide on the third match: model A+B (both matches) tracking it, `extra-filt-places` against today's. The pipeline's change is
`outputs/benchmarks/ball_finetune/scripts/extra_contacts.patch` (its `VB_EXTRA_*` variables are the variants above), the offline
scripts beside it.

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

### The block right after an attack (12 Nov, evening; runs `block-*` against `ctl`: 281 / 351)

Where blocks cost corrections (`ctl`, first / second match): blocks to add 9 / 6, blocks typed something else 14 / 9 (attack
9 / 8), false blocks 3 / 12. The truth's blocks come 0.02-0.54 s after their attack, most at 0.22 s: the pipeline's spacing
(`contacts.GAP` + 1 frame) the owner kept.

- False blocks (18 in the checked rallies, against 26 real): the pipeline's attack 11-13 frames early and the real attack typed
  block (4), or the attack's turn seen again 0.22 s later as the ball flies on into the defence, a dig 11-13 frames after (most of
  the second match's). The wrists don't tell them (the blockers' hands are up by the ball both times: nearest wrist 0.04-0.8 box
  heights, raised); the turn's strength partly (the second match's false ones 364-480 px/s, but 6 real ones under 650); where
  the contact projects does: real blocks within 1.5 m of the net but 2 of 26 (2.4, 4.1 m), false ones past 1.6 m 9 of 18.
  Typing them as another touch (`block-retype`): 281 / 373, the touches around retyped. Dropping them inside the typing
  (`block-drop`): 279 / 352, the touches the players' reach keeps (`attribution.unreached`, which types first) move. Dropped
  once typed: kept ("Kept").
- Missed blocks: mostly one contact for an attack and its block 4-13 frames apart, under `GAP` (0.2 s): the turn signal
  (0.17 s fits on each side) cannot split them. An attack followed by a touch on its own side with no crossing (only possible
  after a block): 15 on the two matches, 6 with a block. Attacks whose ball does not cross within 1.5 s: 17 of the 23 merged
  blocks, but 44 of 295 clean attacks (mostly into the net); with the next touch on the same side or the rally's end, 16
  blocked against 27: a block put there would make more false than it finds. Not run end to end.

Left: a blocked attack from a picture of the hands at the net (the ball deflected or not), with about 60 blocks a match to
learn from; the attack's timing (4 of the false blocks are the attack found 0.25 s early).

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
- Every system (12 Nov, now a rule of `CLAUDE.md`): the project is generic and runs at least on Windows and macOS; nothing
  relies on one system or machine, a more optimised pipeline on some is fine. So the play model's weights moved beside the
  matches, where the backup shares them between the machines, its stage and its training run on any device (measured on the
  PC's card and on its processor alone, and on the Mac's GPU), and "Apprendre de mes réponses" trains it.
- The weights in the repository (12 Nov)? Not as they are: "are they generic enough to improve performance for any new user
  or too specific to me?" was measured, and they do not help the one other match there is ("State", item 6).
- Licences (12 Nov): a non-commercial one is no obstacle, the project is not sold.
- Runtime (11 Nov): the pipeline got much faster, so a model taking more time is fine if it is clearly better; candidates
  that only run on the PC or carry another licence are tested too, and reported for the owner to decide.
- A first touch after the other team's attack that sends the ball straight back over (11 Nov): a relance when the player
  meant it, a dig when not. So no single type for it: only a cue of intent could retype it (how hard the attack came in,
  arms above the head or a low forearm save; not tried, 23 such touches on the two matches, relance 13, dig 10).

## State (12 Nov, evening): hand-over

Today's code with the play model's weights: 281 and 351 corrections (294 and 410 at the start, 283 and 389 on 11 Nov); 279
and 345 since the blocks away from the net are dropped (12 Nov, evening).
Three changes kept, all merged and pushed; nothing runs, no worktree is left, the review server is not started.

Done on 12 Nov, each with its numbers further down or in its benchmark's README:

1. Re-identification, end to end: dropped ("Re-identification").
2. Rally ends: the play / no-play model, kept ("Kept", `benchmarks/rallies/README.md` "12 Nov: the play model in the
   pipeline"). The 11 Nov agent's other candidates (`play_candidates.py`, `play_audio.py`, never run) were not pursued:
   copies in `outputs/benchmarks/play/scripts/`.
3. Touch types from the gesture: at the bar on the pipeline of 11 Nov, under it with the play model: not wired in
   (`benchmarks/actions/README.md`).
4. Pose: eight models compared with YOLO11m-pose (`benchmarks/pose/README.md`): none gains, YOLO11m-pose stays.
5. The owner's rule of 12 Nov (nothing for a single system, `CLAUDE.md`): the play model's weights moved to
   `outputs/learned/play/`, shared between the machines by the backup (sent to the server's backup on 12 Nov, 15:39);
   its stage and its training run on a card, a Mac's GPU or a processor (`play_training.py`); "Apprendre de mes réponses"
   on a fully checked match trains it again. Measured on the PC's card and processor, and on the Mac ("Next", item 4).
6. The weights are not published (the owner asked whether they belong in the repository): on the one other match there
   is, the model's windows are worse (F1 ±1 s 0.87 -> 0.66), so the stage stays on the camera's 4K footage and someone
   else trains their own (`benchmarks/rallies/README.md`, "On someone else's footage").

Waiting on the owner:

- A third match, filmed on 12 Nov, to process on the PC. When its pipeline has finished and before the review starts, copy
  its folder aside (`cp -r outputs/matches/NAME outputs/benchmarks/corrections/NAME-automatic`): the only output of a match
  nothing was tuned or trained on. Once reviewed: "Next", items 1 and 2 (the ball model fine-tuned on both matches tracking it;
  `finetune.py` takes one match today).

On disk, not in the repository, to delete when no longer wanted: `outputs/benchmarks/pose/` (46 GB), `ball_finetune/`
(38 GB), `bench/play/` (22 GB: the frames `play.py` trains held-out models from), `act/` and `act-play/` (11 GB each),
`reid/` (18 GB), the candidates' weights in `models/pose_candidates/` (7 GB) and `models/reid_candidates/` (2 GB); and
`outputs/cache/play/` (22 GB: the training's frames, made again when missing).

Runs: `ls outputs/benchmarks/corrections/*/runs/` (`play-eskb`: the kept change, held out; `play-main`, `play-main2`: the
merged code, the same numbers; `play-stage`, `play-stage2`: the stage run inside the pipeline, not held out).

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
   81%) but the steps after it rest on today's tracker's habits ("Tried and dropped"). Its contacts added to today's where
   today's loses the ball (12 Nov, evening): 281 -> 280 and 351 -> 335, not wired in; to decide on the third match ("The
   fine-tuned ball model's contacts added to today's"). What would make it pay: the new touches' types and players (half a
   correction each), the ball's flight from the fine-tuned track for the typing too without its jitter elsewhere.
3. Done (12 Nov, evening): the block right after an attack. The blocks away from the net dropped (279 / 345, "Kept"); the
   merged attack and block and the rest out of a rule's reach ("Tried and dropped", "The block right after an attack").
4. Done (12 Nov): the play model on the Mac (M4 Pro, `play_device.py --cpu`, one minute of the first match): its GPU (MPS)
   gives the processor's P(play) (0 clips of 233 differ) at 1.32 times the video's length, about 1 h 30 a match (10 min
   on the 5080), the processor alone 2.66 times; a training step 8.6 s, about 5 hours for the 2000. No fix needed. The
   weights came from the server's copy (`sync.merge_shared`, nothing sent).
5. A check that a retrained play model is better before it replaces the weights (the learned order has one): with three
   matches, train on two and compare the windows on the third.
6. The play model on someone else's footage: its windows are worse on the one other match (`benchmarks/rallies/README.md`);
   a threshold or uses set per footage, or training on more views, before it runs on anything but the footage it knows.
