# History (1-11 Nov)

What was measured, kept and dropped from the first review's answers to the work on fewer corrections, which goes on in
[corrections_log.md](corrections_log.md) from 11 Nov. Where the project stands: [state.md](state.md).

- [Left, by value](#left-by-value)
- [The pipeline](#the-pipeline)
- [The page](#the-page)

## Left, by value

What was left to do on the pipeline, most useful first, kept up to 13 Nov. Settled items keep their number, which other notes cite.

1. Settled (2 Nov): touch answers as identity pins, worse (608 -> 507 of 673 held out, "The touches (2 Nov)").
2. Settled: the 3D ball path is in the learned attribution (2 Nov), the ball's width tells two players in line apart (13 Nov,
   `benchmarks/attribution/README.md`).
3. **Contacts the ball track misses.** Of the 71 added touches (41 outside the old windows), 18 have the ball
   visible under half of ±0.4 s, and 20 have a velocity change under `contacts.THRESHOLD` (15.5 px
   a frame at 4K): the ball tracker's recall, not the contact rule. A lower threshold only where
   a player is at the ball: tried and dropped ("Tried and dropped (7 Nov)").
4. Settled (11 Nov): a set crossing the net within 1.3 s is an attack or a relance (`actions.SET_OVER_S`), the slower
   ones stay sets, as the owner calls them.
5. **Empty windows.** 120243 (no contact, "no play") and 158580 (no contact, 0.4 s, "rally"): no
   rule separates them; 36995 (a serve then 4 net contacts) and 180776 (a dig then 5 floors) are
   the other "no play" windows a rule could take: 4+ net or floor contacts in a row after at most
   one touch, untested on other matches.
6. **Same player twice in a row** at identity level (the next candidate when within 0.05-0.2): +1-2
   of 136, and identities do not exist when `match.py` attributes; only worth it inside the identity
   step. Tried as a fix of the review's flag ("Tried and dropped (4 Nov)"): dropped.
7. **Ties within 0.02 box heights** to the bigger box: 97 instead of 93 alone on the answers, one
   fewer detected contact on the tuning clips. Not retried since the second match was answered.
8. **Pose cost.** `by_wrists` runs YOLO11m-pose 3 times per touch below the head with 2+
   candidates: 409 of the first match's 718 contacts, about 1 s each on the M4 Pro (3 crops); measure
   on the RTX 5080 with `speed.py`.
9. **Automatic results.** Of the 81 result answers, 73 come with touches the owner added (the
   editor's default); 8 correct an automatic result, all to "play" (a viewer: "La deuxième n'est
   pas faute"). Rebuild the page's contacts (`web.contacts`, `web.result`) for those 8 frames to see
   which landing the rule misread.
10. **Fewer close-call questions.** Pose-confident picks (the pick's wrists within 0.1-0.15 box
    heights, the next candidate's 0.2 farther or vetoed) are still wrong 3 times in 16-27 on the
    answers: the review keeps asking every close call.

11. **Winners on the first match.** The rally labels' notes (`benchmarks/rallies/ground_truth/
    first_match_*.csv`, "left serves", "right serves") give each rally's server, so the winner of
    the one before: a points benchmark on the 4K match (`benchmarks/points` has only the school
    clips), now that 131 of 137 windows open on a serve. Done another way: `learn` scores the winners on
    the checked rallies (117 of 128).
12. Settled (2 Nov): hidden contacts place the added serves (`contacts.hidden_contacts`, "The touches (2 Nov)").
13. **The review's answers as benchmarks.** `answers.py --rerank` scores attribution on them; the
    same for `action` types (`actions.classify_rally` on `actions.csv`'s contacts against the
    owner's types) and `rally` verdicts would score those steps without labels.
14. Done (12 Nov): **the learned play / no-play clip model** is in the pipeline where its weights are (`playing.py`, the
    stage "play"; `benchmarks/rallies/README.md` "12 Nov"): ends carried on and starts pulled back through its play, the
    windows it sees play in kept, a rally going on after a bounce played on. Corrections 283 -> 281 and 389 -> 351, the
    model held out. VideoMAE-base fine-tuned on the reviewed matches (base weights CC BY-NC 4.0: fine for a
    non-commercial project, the owner, 12 Nov), 345 MB in `outputs/learned/play/`, shared between the machines by the
    backup; "Apprendre de mes réponses" on a fully checked match trains it again (`play_training.py`). About 10 min a
    match on the 5080, 1 h 30 on the Mac's GPU (the same P(play)), 7 hours on a processor alone. Left (`corrections_log.md` "Next"): a
    check that a retrained model is better, someone else's footage (worse windows on the one other match: the stage stays on
    the camera's 4K footage, the weights are not published), and the ends themselves (it only carries them on: cutting them back where
    P(play) falls loses the last floor contact).

## The pipeline

What the first match's answers (`outputs/matches/2026-10-29-aspom-1-vs-aspom-2/identity_answers.json`: 277 touches, 71
added, 34 rallies, 23 type fixes, 81 results) and the viewers' 18 reports taught the pipeline,
what went in the code from it, and what was left.

### In the code since 1 Nov

| Step | Change | First match answers | Labelled clips (school) |
| --- | --- | --- | --- |
| attribution | equal distances to the bigger box (front player) | 85 → 93 of 135 | tuning 58/70, 56 → 57/70; held-out 33/42, 30/42 |
| attribution | other side's tracks over `CROSS_M` 1 m inside the contact's side | 93 → 97 | unchanged |
| attribution | `by_wrists`: pose on touches below the head (veto 0.4, then nearest wrists within 0.2) | 97 → 104 | tuning 58 → 61, 57 → 60; held-out 33 → 36, 30 → 32 |
| actions | a dig sending the ball straight over is an attack (not a rally's first contact) | 6 owner fixes, 5 viewer reports | tuning truth 80 → 79 (dig 577), rest unchanged |
| match | a window opening up to 1 s after its serve starts at it (`actions.serve_starts`) | serves typed 81 → 108 of 137 windows, labelled 19 → 35 of 43 | unchanged |
| decode | a frame reached by its timestamp (`decode.timestamps`), not OpenCV's seek, a frame early from frame 142115 of the first match, never on the second | exact 58 of 58 against 43 (first match), 73 of 73 (second), checked on counted frames; touches right first by_wrists 590 → 592, learned 597 → 598, ranked 582; no retraining for it |
| match | a window with no serve gets the one the players' positions show (`match.unseen_serves`) | serves typed 108 → 131 of 137, labelled 43 of 43 within ±1 s, the owner's 6 added serves' players all matched | `side_holdout`: 2 serves added, both labelled |
| match | windows with 2+ floors and no touch dropped (`actions.no_play`) | 2 of the 6 "no play" windows, no rally lost | 50:00-60:00 F1 ±1 s 0.57 → 0.59, P 0.88 → 0.95 |

Scored with `benchmarks/attribution/answers.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 --rerank [--video data/matches/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4]`
(the module's ranking run again on `actions.csv`'s contacts, the touch's player being its track's
identity), `benchmarks/attribution/bench.py ... [--pose]`, `benchmarks/actions/bench.py`.

### The first match rerun (1 Nov)

Rerun on 1 Nov (owner's go), answers moved by `volleyball_stats.rekey` (28 rally answers, 30 added
touches, 3 checked rallies onto their new windows; 21 rally answers saved 16 frames late by a review
bug, fixed). `volleyball_stats.learn`, before and after:

| Score | Before | After |
| --- | --- | --- |
| attribution: answered touches | 85/135 | 108/139 |
| contacts: added touches found | 13/71 | 42/71 |
| contacts: false ones gone | 18/26 | 20/26 |
| actions: types set | 0/19 | 6/19 |
| rallies: labelled serves with a window | 41/43 | 43/43 |
| points: labelled servers | 22/41 | 43/43 |
| points: labelled winners | 32/39 | 39/41 |
| checked rallies (8): touches found | 62/103 | 92/108 |
| checked: pipeline touches kept | 61/61 | 92/94 |
| checked: types | 49/62 | 82/92 |
| checked: named players | 51/55 | 75/83 |

Report: 134 rallies (136), 867 contacts in rallies (718), set drifts +0 +2, +2 +4, +1 +5 (team 1,
team 2). The rerun lost a real rally (43678, 14:33): the 31 Oct `served` opened it on the server's
bounces, typed floor, so the whole rally was dead and `no_play` dropped it; fixed since
(`actions.behind_end_line`, a serve bounced again is a catch), back with the next rerun. The touches
the review added and the pipeline now finds too (0-20 frames off) are one (`web.ADDED_SAME_S`).

### Learning from the review (1 Nov)

In the code since 1 Nov:

- `learn` scores every step on the answers and the checked rallies (full labels), each run kept in
  `learn.json`, a rerun's with what the results it replaced scored on the same answers; the review's
  "Progrès" tab opens on that comparison, the curves per measure in its history.
- The review's "Apprendre de mes réponses" (`learn --rerun`) reruns the pipeline, moves the answers
  (`rekey`) and scores; `wrists.json`, `relances.json`, `jumps.json` and `looks.npz` cache the poses and looks
  (side_holdout: 3 min, then 6 s). "Mettre en ligne" uploads; an apply no longer does.
- Attribution: a learned order (`ranker.py`, `benchmarks/attribution/ranker.py --write` retrains it
  on the answers), on 4K footage only: +12 of 180 held-out answered touches, -6 of 120 on the 720p
  school clips. Not in the first match's outputs yet: the next "Apprendre de mes réponses".
- Identity: `SHARPEN` 0.5 -> 0.9 (the share of the embedding weights learned from the answers):
  69.5% -> 73.4% of the held-out answers kept.
- Contacts: the threshold sweep on the checked rallies and added touches is flat (360 and 0.17 s
  stay): the 11 checked touches missed are the ball tracker's.

Left:

1. Retrain the ranker and re-sweep `SHARPEN` after each review (both on the answers): done on 5 Nov
   with the second match, which the learned attribution trains on since.
2. A settings search for the rallies' rules (serve lead, `no_play`, ends) on the rally answers and
   checked rallies.
3. Asked of the owner: validate whole rallies (the unbiased labels) more than single questions.

### Later on 1 Nov (page and review)

- Page: a touch the rally goes on after is no fault (let serves: serve faults 24 -> 15 on the first
  match); the running score counts the rally winners; a rally goes to the team serving the next
  one within `web.NEXT_SERVE_S` 40 s (set scores 9 -> 5 points off the given 25-23, 25-12, 25-18).
- `rekey` moves a no play, winner or end answer only onto a window that is mostly its rally: 3 real
  rallies had been dropped (put back by hand, `identity_answers.before-noplay-fix.json`).
- Relances: `ABOVE, LIFT = 0.03, 0.6` (6 of the owner's 8 relances, 2 of 24 checked attacks; school
  labels unchanged). In the first match's outputs at the next "Apprendre de mes réponses".
- Review: live warnings in the editor (`helpers/checks.ts`, the automatic reports' rules, the
  winner taken from a last touch's fault or point), "Charger les signalements"
  (`feedback.fetch`), the next rally played once one is checked, full screen, pinch zoom, a held
  click slowing the video, a draggable caption.

Checked and left as they are (1 Nov): the rally rules on the 4K spans and the school clips
(`WHISTLE_AFTER_S` 1 or 3, `MOTION_BRIDGE_S` 1 or 3, `LIVE_SPEED` 10 or 20: none gains; 26:00-36:00
F1 ±1 s 0.90, 50:00-60:00 0.57, side_club 0.93, side_long 0.95, side_holdout 0.75); the 5 "no play"
windows still found (a serve then only net and floor contacts, a dig then a floor, an empty one):
no rule separates them from real short rallies, a serve into the net being one; the review's
answers drop them from the page. Not started: identities jumping inside a long track (cutting
tracks where their embedding jumps, scored by `benchmarks/identity/answers.py`); the ball
tracker's misses (29 of 71 added touches: fine-tune the ball model on the owner's added touches
and checked rallies, on the RTX 5080).

### Tried and dropped (1 Nov)

On the 135-136 answered touches, tie-breaks other than the bigger box: the smaller box 65, the ball
nearest the box centre 66, nearest its centre x 75, an anchor per type 80, a track seen at the frame
first 77. Pose alone with no veto: 102-105 depending on margin and confidence; the veto alone (the
attribution README's 720p rule) 101; a box distance standing in for unseen wrists 98-104. A window
starting at its serve rather than `LEAD_S` after it: 2 school rallies lost at ±1 s. Moving a window
to a serve whose next contact is the server's own bounce (`BOUNCE_PX`): the real serve then typed
"net" (`side_holdout` 17202).

### The touches (2 Nov)

Missed on the 129 checked rallies, 101 of 945: 71 no contact in the ball track, 23 outside a window, 7 removed after
detection. 48 of the pipeline's 883 touches are false. `benchmarks/rallies/checked.py` scores the windows on the whole
match.

Done: `LIVE_SPEED` per second (812 -> 829 touches in windows, `side_holdout` 0.75 -> 0.86).

Tried: WASB on frames t, t+2, t+4 over the whole match, in
`outputs/matches/2026-10-29-aspom-1-vs-aspom-2/experiments/ball_step2.csv` (frame, x, y, peak), dropped below. `ball.csv` is untouched. The scripts
are in that folder: `pass2.py` (the pass), `track_exp.py` (the sample), `ev2.py` (its scoring).

On 25 sampled rallies, touches found of 205 and contacts that are no touch:

| Track | Touches | No touch | Ball visible |
| --- | --- | --- | --- |
| `ball.csv` | 188 | 40 | 73% |
| 1024x576 input | 187 | 200 | 91% |
| frame step 2 | 191 | 88 | 88% |
| `ball.csv`, gaps filled from step 2 at peak 0.5 | 193 | 49 | 84% |

Whole match, the full pipeline on copies (`ball.csv` then gaps filled from step 2 at peak 0.5, gaps up to 2 s), on
the 129 checked rallies: touches found 822 -> 840 of 944, pipeline touches real 813/859 -> 830/921, types 86.5% ->
83.7%, named players 88.7% -> 88.6%; 26:00-36:00 F1 ±1 s 0.90 -> 0.88, 50:00-60:00 0.57 -> 0.62. Dropped: 18 touches
found for 45 false ones, F1 0.907 -> 0.895, and 95 min more per match on the M4. The scores matching exact frames or
rally starts (answered touches, types set, rallies kept, checked winners) fall by construction on a copy whose
answers were not moved, so they say nothing.

Last "Apprendre de mes réponses", 1 Nov 21:41, with `LIVE_SPEED` per second: touches found 826/944 -> 844/945, pipeline
touches real 817/860 -> 835/883, types 86.7% both, named players 89.1% both, checked winners 114 -> 115, all 129 rallies
still checked, same set scores.

In the code and the first match's outputs since 2 Nov (the owner's "Apprendre de mes réponses", 10:17), against the last run: touches
found 844 -> 872 of 945, pipeline touches real 835/883 -> 863/909, types 732/844 -> 778/872, named players 651/731 -> 679/761, answered
touches 607/673 -> 610/668, checked winners 115 -> 117 of 128, added touches found 95 -> 131 of 198. All 129 checked rallies, their winners, running scores and named players came through, no
warning, sets 25-23, 25-12, 25-18; 3 rallies change by a floor or net contact, which the lock does not hold. F1 ±1 s is unchanged
(26:00-36:00 0.90, 50:00-60:00 0.57); the school clips too, but serves 5/7 -> 6/7 on `side_holdout`, one more wrong pick of 38 and
`side_long`'s score drift 1 -> 2 (a warm-up window moved). All tuned on this match: the second one is the test.

- Contacts hidden in the ball track's gaps (`contacts.hidden_contacts`), the benchmark's README.
- Late serves and windows that are no rally (`actions.late_serves`, `no_play`): rally starts 123 -> 126 of 129, windows 135 -> 130.
- A touch at the nearest player's feet is a bounce (`attribution.FEET`): 7 false, no real one.
- The ball's 3D place in the learned attribution (`ball3d.flight_places`, `ranker.py`), and attack or relance from its flight
  (`actions.by_flight`, calibrated footage only): 137 -> 144 of 169, each set held out.
- `web.with_added`: an older added touch near a row found at a frame the review gave no longer loses that touch.

Tried and dropped, 2 Nov (numbers in the benchmarks' READMEs): a learned filter on contacts below the threshold (F1 0.89 against
0.895), carrying a rally past its window (7 real touches for 16-29 false), a shorter `contacts.GAP` for blocks (0.16 s: 3 more
blocks right, 21 more false), a set sent over typed attack (13 fixed, 10 broken: the owner calls many sets), the 3D height for
touches typed floor (real floors fit up to 2 m), touch answers as identity pins (608 -> 507 of 673 held out), tracks cut between
rallies (678 -> 679 of 761, 15 min more). 30 settings searched one at a time, sets 1-2 apart from set 3: a plateau, nothing changed.

Next, as of 2 Nov: the touches still missed (the ball model fine-tuned, tried 11-12 Nov), the false ones, the ends with no
whistle on 50:00-60:00 (the play model since 12 Nov), the merged attack and block: all taken up in
[corrections_log.md](corrections_log.md). Tried and dropped: see `benchmarks/rallies/README.md`.

### Rallies carried on (4 Nov)

`rallies.carried_on`: no window of the two matches ends on a whistle when a rally is cut short: the ball lost near a player ends it. A window now plays on
through 3 contacts or more under 2.5 s apart before the next whistle (fewer are mostly the dead ball's: 16 real of 44). `benchmarks/rallies/checked.py`, touches in windows and
contacts that are none: second match 681 → 701 of 766 and 130 → 142, first 869 → 875 of 945 and 175 → 186. The full pipeline against the checked rallies: touches to add 133 → 113,
to remove 33 → 37, types 46 → 49, winners 5 → 4 (second); 102 → 95, 44 → 44, 65 → 63, 7 → 7 (first). The rest is out of the ends' reach: 55 and 60 of those touches have no contact at all,
the ball unseen; better tracking near the floor is what would find them.

### Tried and dropped (4 Nov): fixes from the automatic reports

Servers fixed from the rotation (`auto.serverOrder`).

The first match's reviewed servers follow each team's rotation of 6 strictly, every set. The pipeline's
serve players were right 117 of 126. One server per turn (a team serving in a row), by majority: 117 → 115.
The rotation order learnt per set and team (a decoding that allows missed and split turns): 117 → 115;
with 10, 25 or 50 % of the serves answered as anchors, the unanswered ones 523 → 510, 449 → 446 and 317 → 318 over 5 draws.
Two cycles a set leave the order weak, and the rally list's slips (missed rallies, a turn split by a false
one) shift it. `auto.serverOrder` stays a flag: of its 14 on the pipeline's first match, 6 sit on a wrong
server and 1 on a missed rally.

The less sure touch of one player twice in a row (`auto.samePlayer`) given to the next candidate of
another player: right 8 → 3 of 11 on the first match, 6 → 6 of 19 answered on the second; on ties
(gap 0) +3 -1 and +1 -1. The second's pairs are often a third player's (7 of 19). It stays a review question.

Contacts searched again with a lower threshold inside stretches of over `GAP_S` between touches (`auto.gap`):
on the first match the 14 stretches hold 13 of the 72 touches the pipeline misses; at the threshold
×1.0 4 found for 5 false, ×0.6 6 for 8, ×0.3 6 for 20; on the second, at ×0.6 1 for 3 false. The ball's
track alone cannot tell them: the players at the ball would have to.

### The score board (4 Nov)

`scoreboard.py` reads the scorer's flip board near the camera before each serve; `review.board_off` reports
the rally after which the running score parts from it for two readings in a row. First match (board mostly
out of view): 21 readings for 129 rallies, 19 equal to the reviewed score, no report. Second match: 82
readings for 144 rallies, 16 equal to the page's score (its 3 sets end off the given score), 7 reports;
its last readings per set match the given scores. About 6 min on the M4 the first time, nothing on a rerun.

### Pose on every touch and serve rotation (5 Nov)

The pose on passes, sets and digs is in: `attribution.by_wrists` (the rule, below the head) and the learned order, which
poses every touch with two candidates on 4K. The rule posing serves, attacks and blocks too loses, right picks of the
touches answered or labelled: first match 609 → 594 of 691, second 844 → 828 of 957, `side_club` 25 → 22, `side_long`
39 → 38, `side_holdout` 39 → 39. Dropped.

The second match's reviewed servers follow each team's rotation of 6 too: 6 servers a set, 8 a team over the match
(substitutions between sets), one swap in 82 turns (set 3, 73:29, `auto.serverOrder`'s one flag: a real rotation fault, the owner says). Fixing the pipeline's
servers from it still loses (first, second, of 126 and 138): the rotation decoded 117 → 115, 129 → 117; one server per
turn by majority 117 → 119, 129 → 123; a server between two agreeing ones of the turn 117, 129. `auto.serverOrder` stays
a review flag.

### Tried and dropped (7 Nov)

On the two reviewed matches' checked rallies and answers (M1 first, M2 second):

| Idea | Result |
| --- | --- |
| A "relance" with a jump becomes an attack | 59-68% of real attacks are jumped, but so are 26-30% of real relances: 6 fixed for 11 broken (M1) |
| A set sent over typed attack when the toucher jumped | M1 5 fixed, 3 broken; M2 8 fixed, 9 broken |
| A learned retyping of the rules' types (multinomial logit on the rule's type, neighbours', sides, touch count, timing, place), one match trained, the other tested | 940 → 942 of 1057 (M2), 749 → 751 of 839 (M1) at best; overfits |
| A rally's last contact typed floor turned into a touch when a player's wrists are at the ball | wrists within 0.15 box heights: M1 6 fixed, 6 broken; M2 10 fixed, 3 broken |
| A lower contact threshold where a player is at the ball ("Left" item 3) | missed touches under the threshold with a player there: 1 (M1), 7 (M2), against 78 and 82 false candidates |
| Made-up contacts (answered "no touch") dropped when the ball is little seen or turns weakly | every threshold loses more real touches: seen ≤ 40% and turn < 1.5×: 6 false for 18 real (M2), 2 for 14 (M1) |
| False touches told by the distance to the nearest player (`gap`) | same spread as real ones (median 0.33 vs 0.37 box heights) |
| The hitting height from the pose (wrist over the floor at the hit) to fill attacks the 3D fit leaves | +38 and +30 attacks, but within-player spread 0.096-0.109 m against 0.07-0.085 m for the ball's |
| Attack heights from the 3D ball fitted at each attack's hit frame | within-player spread 0.080 → 0.105 m (M1), 0.120 → 0.110 m (M2) |
| Jumps without a camera model (no lens), the box height as the scale | `side_holdout`: 3 of 9 attacks measured, the 2 checked by eye wrong |
| The hips' fastest rise and fall as a jump's edges where the ankles give none | of 11 jumps the ankles miss on the 80 labelled attacks, 6 recovered, but 4 false jumps added |
| An attack credited to the one candidate who jumps when the credited player shows none | 80 labelled attacks, 7 credits wrong: 5 switches, 1 fix, 4 breaks (a jump hidden behind another player) |
| Attacks named at the hit rather than the contact frame | of M2's 145 answered attacks with the player posed, 8 wrong, 3 of them with the contact over 4 frames off: at most +3 |

Also found: on 55 attacks labelled to the frame (`benchmarks/jumps/ground_truth/`, the hand on the ball), the ball's
contact frame is a frame early at the median, within 2 frames 45 times, over 4 frames off 7 times, 6 of them early (5-21
frames): the ball seen nearest the attacker's wrist (`jumps.hit`) is within 2 frames on 36 of 38 measured jumps. The
page's touches keep the contact frame (the answers name them by it); the jump timing uses the hit, the films their own
search of the ball nearest the hands (`film.touch_time`).
Also found: of the touches with a clear ball turn but no contact, most sit outside the windows of the matches' outputs, which
predate the 5 Nov rally fixes (59 of 64 on M2); today's code: 869 → 880 of 945, 1074 → 1103 of 1199 touches in windows.

### Tried and dropped (8 Nov): an image action model for the types

VolleyVision's YOLOv8m (block, defense, serve, set, spike; AGPL-3.0, broadcast images) on 4K crops around the ball at each
touch of the checked rallies, ±2 frames, both matches (1,953 touches): a detection on 879. Attacks seen as spikes 203 of 312,
but so are 78 of 440 sets and 34 of 129 relances; passes and digs never seen as defense (0 of 565), sets as sets 7 of 440.
On the rules' confusions: a set retyped attack when it says spike fixes 15 for 68 broken (13 for 39 at confidence 0.5), a
relance 8 for 20 (8 for 8). Fine-tuning on the owner's types would be the next try; the arm's shape needs more than this model.

## The page

### Lighter (1 Nov)

The players' positions are one file a minute (`positions/N.js`, 13 KB compressed), loaded as the replay reaches
them; the balls dropped between two players read theirs from `data.js` (`around`). Lighthouse, mobile, 3 runs on
localhost, the first match without footage: first load 1,824 -> 282 KB, LCP 2.73 -> 2.41 s, time to interactive
10.9 -> 3.05 s, blocking 664 -> 644 ms, score 80 -> 82 (desktop 99, 99). The first file loads 500 ms after mounting:
a script running before the paint is recorded counts as blocking it in Lighthouse's simulated LCP. The review's
screens are their own script since 7 Nov (`review-app.js`, `vite.review.config.ts`, loaded by `main.tsx` when review.js
is there): the page's script 255 -> 221 KB compressed, the download only (from disk, 4x slower CPU: script time and
first paint unchanged, 932 vs 944 ms and 1156 vs 1152). `i18next` (15 KB) and `cn` (8 KB) stay.

### Online (1 Nov): Mon match, the story, the trophies

"Mon match" (`web/src/components/MyMatch/`), "L'histoire du match" (`web/src/components/Story/`) and "Les trophées"
(`web/src/components/Trophies/`), uploaded 1 Nov 22:03. The owner's rule on points is in `web.credited`.

### Online since 2 Nov: the coach, TV mode, the 3D ball, the voice, the films

"Le coin du coach" (`web/src/components/Coach/`) and "Mode TV" ([match-page.md](match-page.md), `Watch/Broadcast.tsx`, `scene3d/hall.ts`).

The ball in 3D (`benchmarks/ball3d/bench.py`, first match, no 3D truth): the camera found at x 0.1, y 11.83, 3.93 m high (set up
on the net's line, about 6 m from the sideline, 3.6 m high: 7.3 m from it); path to the ball in the picture, median and 90%,
typical heights 93 and 205 px, fitted 8 and 77; median heights attack 2.66, block 2.60, serve 2.39, set 1.85, pass 1.29, dig 1.46.
Floor position found with the feet hidden, median: set 0.70 m, pass 0.94, dig 0.96, relance 1.66, attack 2.11, block 3.72, serve 2.90
(a serve's frame can be late, "Left" item 12). No drag or spin; a flight over 2.2 s (a missed touch) is left out. Without a lens the
focal length may not come out (`side_holdout`): typical heights stay.

Players' animation (`Watch/helpers/pose.ts`): by code on the jointed figures. The ball from the feet of who touches it, median,
on the first match: set 0.63 m, dig 0.86, pass 0.89, relance 1.24, attack 1.46, block 2.44, serve 2.57; within 1.5 m: set 85%, pass 73%,
dig 75%, attack 52%, block 33%, serve 14%: hence the lunge, and a stock gesture past 2.5 m. Real movements from the video: not done
(pose on every player and frame, unreliable in 3D from one camera, and the owner's call on consent).

The voice (`speech.py`, `voice.py`): the owner's pick by ear among Chatterbox, Piper, Kokoro and Kokoro variants, Kokoro's `ff_siwis` at 1.2 (their
"E"); 19-22 characters a second against 15 for the ones judged flat. Every named touch is called, in full or by the name, the most telling taking the room first (`speech.RANKS`), the silence around each clip trimmed (Kokoro leaves about half a second: "Manon" 1.07 s, 0.5 s trimmed). First match: 601 of the 689 touches to call are, 97 of 97 attacks, 189 of 198 sets, 75 of 128 digs, 1 of 12 blocks (they come right after an attack); 405 texts, 3 minutes on the M4. Whisper small
reads it back at 0.60 of the words (it writes numbers as digits, so that understates it; very short lines are the weakest). Not done: Phonon 40M's French
voices (CC BY-NC, gated: the owner's Hugging Face login), English audio (the browser's voice).

The gym, measured through the camera: the handball court 39.4 m by 20 against the real 40, the near goal line on the camera's post.
Later: a hall per gym (every match shows this one); the near goal; a sharper replay choice from the viewers' reports. The voice is the
browser's: not heard in the checks, which run without sound.

Tried and removed (owner's call, not useful enough; code in `3377048`): the score of each six and a serve map by zone.
From them: lineups from the positions, smoothed over 2 rallies each side, gave the first match 4 and 3 sixes whose
scores add up to the given sets; on clips with unreviewed names 4 and 7 sixes for 15 rallies.

Serve speed and attack height (`ball3d.measure`, `benchmarks/ball3d/measures.py`, first match, no radar or tape measure): a serve's
speed is read over its mid-flight, 0.2 s in from each contact, the raw flight's 122 km/h from a late contact gone: 90 of 123 serves, median
42 km/h, most 61; contact frames +-5 move it 0.6% (2.3% at 90%), a third fewer sightings 0.3%, the feet 1 m in depth 1.6%; a player's odd and
even serves correlate 0.85 over 9 players. An attack's height is the fit's, kept between 1.8 and 3.8 m with its ball seen: 89 of 156, median 2.66 m,
contact frames +-2 move one attack 0.17 m (0.33 at 90%) and a player's median at most 0.16, so the page only gives that median, from 5 attacks, to the decimetre:
odd and even correlate 0.75 over 10 players, and it follows their own heights at 0.71, 0.86 m above the head. The scale: heads on court 1.79 m, gravity found 9.4-10.4 m/s2.
Left open: along a serve's flight the ball shows almost no slowing (-0.06 m/s2) where drag should show, unexplained; a radar, then the second match, should settle both.

"Ton film": a player's vertical film cut from the real video like a broadcast, cut as the match's (below: clips from the set or the toss, hard cuts, a hit on each point, a hook), 6 moments with their starred touches always, about 6 MB for 35 s, made ahead of time by the review's button (`film.py`, `outputs/matches/MATCH/films/`), only those whose `plan` changed; never during an apply. It goes only beside a page with the video, so hosted only behind the password. The moments are those the 3D film had (removed, 2 Nov: git history). The ball: searched again around the first pass at up to 4 times the detail (`film_ball.json`, kept), what stays still dropped, the longest chain a ball could follow, flights split where its velocity changes; a touch's recorded frame can be some frames off. Frames are cut by their real times (`frame_times.npy`). On Olivier's 4 live moments the path is on the ball on every 4th frame checked. At a serve a named track inside the court follows the teammate behind the line (one moment on the first match); elsewhere a track slip still shows: a ball's 3D place is too often off to correct it by (13 of 72 moments would change, most wrongly).
The match's own film (`film.HIGHLIGHTS`, 50 s, its own button), cut as sports recaps are (dead time out, a hook first, a replay only where it tells something): its most striking point as a hook before the title, then in match order the touches starred in the review's Match tab always (as their rally's clip, or one of their own), the longest rally as its 3 best exchanges (an attack and the dig that saved it, about 2 s each) and its end, the match point, set points, late ties, aces, blocks and kills (a long rally counts, capped), across the sets, both teams and many players; each clip from the set or the serve's toss to the point's banner gone (about 3.6 s), hard cuts between them, 2 replays, each point's touch hit with a flash, a jolt and a bass; a touch at fault is never the one named; in 16/9 at 1080p. Balls of other courts: a flight whose upper sizes are under 70% of the smallest a ball can look there while on our court (the camera, from the calibration) is dropped and its frames searched again away from it; on the summary's 5 rallies 14 stretches, 165 of 2,308 frames. Where nothing is found no effect is drawn: holes are bridged only up to 0.2 s.

### Players' movements (2 Nov)

The page showed each 0.1 s sample as it was: a jump every 0.1 s, 3.1% of moves in rallies over 7 m/s (depth mostly: a box's foot), players blinking in holes over 0.5 s. Now `web.natural_motion` at build (outliers, holes while the team has under 6 there, a Gaussian of 0.2 s, for the positions' files only: stats stay on the tracking; filling every hole doubled moments over 12 players, from 14% to 26%), the page's `playersAt` between samples, in both views, and bodies turning over 0.12 s (`benchmarks/players/motion.py`).

### The first match's video timing (2 Nov)

4 of its frames last 33 ms (frames 96157, 111731, 142115, 173361), so a frame's real time runs up to 2.3 frames past `frame / 50` late in the match. Cutting exact frames needs the file's timestamps (`ffprobe ... packet=pts_time`); the page's video is up to about 45 ms off its data there, not visible and not changed.

### Lighter (2 Nov, positions)

The first match's 67 position files, gzip: JSON per sample 821 KB, 12.3 a file; per person in columns 732; at 5 cm 450 (6.7 a file; 2.8 cm off at most, speeds unchanged).
Left aside: binary at 5 cm 373, which needs `fetch` and so no longer opens from `file://` (in base64 437); 10 cm 346, 7 cm off.
Files of 5 minutes (from 1): 34 KB each, 460 to 428 KB in all, the whole match in rallies 5 waits instead of 21, a wait barely longer (the request's time weighs more than the size: 76 ms for 13.6 KB, 104 for 29.7).

### La saison (4 Nov)

A tab of the match list, shown once a named team has 2 listed matches (`Season/`), at its own address (the list's with `#saison`): the team's results, then each player's season in words, as the match pages tell it (5 Nov, the owner found the ratings compared side by side too judgy): their match pages' strengths added up over the matches they showed in (2 at most), what went up from their first match to their last (half a rating out of 5, a point per set; never a fall), and what their last match's page gave them to work on. Nothing ranks players against one another. Same rules as the match pages (`lines`, `strengths`), each match's `data.js` loaded when the tab opens. A player is followed by name, else jersey; a value needs 5 touches in the match (5 rated ones for a rating). Online since both matches are hosted (5 Nov): it follows ASPOM 2. Its team picker offers the club's teams the "Club" dialog ticks (`club.json`'s `teams`, first guessed from the club's name's first word; every named team while none is ticked).
