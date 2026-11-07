# Next steps from the review's answers (1 Nov)

## Rallies carried on (4 Nov)

`rallies.carried_on`: no window of the two matches ends on a whistle when a rally is cut short: the ball lost near a player ends it. A window now plays on
through 3 contacts or more under 2.5 s apart before the next whistle (fewer are mostly the dead ball's: 16 real of 44). `benchmarks/rallies/checked.py`, touches in windows and
contacts that are none: second match 681 → 701 of 766 and 130 → 142, first 869 → 875 of 945 and 175 → 186. The full pipeline against the checked rallies: touches to add 133 → 113,
to remove 33 → 37, types 46 → 49, winners 5 → 4 (second); 102 → 95, 44 → 44, 65 → 63, 7 → 7 (first). The rest is out of the ends' reach: 55 and 60 of those touches have no contact at all,
the ball unseen; better tracking near the floor is what would find them.

What the first match's answers (`outputs/matches/2026-10-29-aspom-1-vs-aspom-2/identity_answers.json`: 277 touches, 71
added, 34 rallies, 23 type fixes, 81 results) and the viewers' 18 reports taught the pipeline,
what is in the code since, and what is left, with the numbers to start from.

## In the code since 1 Nov

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

## The first match

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

## Learning from the review

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

1. Retrain the ranker and re-sweep `SHARPEN` after each review (both on the answers); a second match
   to hold out whole.
2. A settings search for the rallies' rules (serve lead, `no_play`, ends) on the rally answers and
   checked rallies.
3. Asked of the owner: validate whole rallies (the unbiased labels) more than single questions.

## Later on 1 Nov (page and review)

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

## Left, by value

Since 2 Nov (`docs/plan.md`): 2 (the 3D ball path in the learned attribution), 4 (sets sent over: tried, the owner calls many
sets), 12 (hidden contacts place the serves) and 1 (pins: tried, worse) are settled.

1. **Identity behind wrong touches.** 9 of the 135 answered players are among no candidate: tracks
   with no identity (3), and long tracks chopped into many pieces whose identities jump (track 275:
   pieces of identities 2, 14, 4, 11, 16 over 14162-23115; both serves 21875 and 31080 land on a
   piece of team 1's identity 14, the owner says 4 and 8). Idea: feed touch answers to the identity
   step as constraints when the answered player is among no candidate (the toucher's track is then
   probably right and its piece wrong): the piece holding the nearest candidate at that frame is
   that player. Score with `benchmarks/identity/answers.py`.
2. **Wrong picks among tracked players.** Before the pose 26 answered players came second; after it, 104 first, 31 wrong, 9 of those with no candidate. Next: the ball's path
   after the touch (the player it leaves from), the 3D ball path for depth (`README` of
   attribution, "Not tried").
3. **Contacts the ball track misses.** Of the 71 added touches (41 outside the old windows), 18 have the ball
   visible under half of ±0.4 s, and 20 have a velocity change under `contacts.THRESHOLD` (15.5 px
   a frame at 4K): the ball tracker's recall, not the contact rule. A lower threshold only where
   players crowd the ball would find some; not tried.
4. **Sets sent straight over.** 1 retyped as an attack, 4 seen and kept as sets (in touch questions,
   where the type is not asked), 20 never seen: ask the owner, or ask the type in the Match tab.
5. **Empty windows.** 120243 (no contact, "no play") and 158580 (no contact, 0.4 s, "rally"): no
   rule separates them; 36995 (a serve then 4 net contacts) and 180776 (a dig then 5 floors) are
   the other "no play" windows a rule could take: 4+ net or floor contacts in a row after at most
   one touch, untested on other matches.
6. **Same player twice in a row** at identity level (the next candidate when within 0.05-0.2): +1-2
   of 136, and identities do not exist when `match.py` attributes; only worth it inside the identity
   step.
7. **Ties within 0.02 box heights** to the bigger box: 97 instead of 93 alone on the answers, one
   fewer detected contact on the tuning clips. Retry once a second match is answered.
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
    clips), now that 131 of 137 windows open on a serve.
12. **Added serves' frames.** `unseen_serves` puts the serve where the server's stand ends, 0.1-0.5 s
    after the contact: the page's serve clips start that late. The ball's first sighting after
    the stand, or the window's first ball run, would place it closer.
13. **The review's answers as benchmarks.** `answers.py --rerank` scores attribution on them; the
    same for `action` types (`actions.classify_rally` on `actions.csv`'s contacts against the
    owner's types) and `rally` verdicts would score those steps without labels.

## Tried and dropped (1 Nov)

On the 135-136 answered touches, tie-breaks other than the bigger box: the smaller box 65, the ball
nearest the box centre 66, nearest its centre x 75, an anchor per type 80, a track seen at the frame
first 77. Pose alone with no veto: 102-105 depending on margin and confidence; the veto alone (the
attribution README's 720p rule) 101; a box distance standing in for unseen wrists 98-104. A window
starting at its serve rather than `LEAD_S` after it: 2 school rallies lost at ±1 s. Moving a window
to a serve whose next contact is the server's own bounce (`BOUNCE_PX`): the real serve then typed
"net" (`side_holdout` 17202).

## Tried and dropped (4 Nov): fixes from the automatic reports

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

## The score board (4 Nov)

`scoreboard.py` reads the scorer's flip board near the camera before each serve; `review.board_off` reports
the rally after which the running score parts from it for two readings in a row. First match (board mostly
out of view): 21 readings for 129 rallies, 19 equal to the reviewed score, no report. Second match: 82
readings for 144 rallies, 16 equal to the page's score (its 3 sets end off the given score), 7 reports;
its last readings per set match the given scores. About 6 min on the M4 the first time, nothing on a rerun.

## Pose on every touch and serve rotation (5 Nov)

The pose on passes, sets and digs is in: `attribution.by_wrists` (the rule, below the head) and the learned order, which
poses every touch with two candidates on 4K. The rule posing serves, attacks and blocks too loses, right picks of the
touches answered or labelled: first match 609 → 594 of 691, second 844 → 828 of 957, `side_club` 25 → 22, `side_long`
39 → 38, `side_holdout` 39 → 39. Dropped.

The second match's reviewed servers follow each team's rotation of 6 too: 6 servers a set, 8 a team over the match
(substitutions between sets), one swap in 82 turns (set 3, 73:29, `auto.serverOrder`'s one flag: a real rotation fault, the owner says). Fixing the pipeline's
servers from it still loses (first, second, of 126 and 138): the rotation decoded 117 → 115, 129 → 117; one server per
turn by majority 117 → 119, 129 → 123; a server between two agreeing ones of the turn 117, 129. `auto.serverOrder` stays
a review flag.

## Tried and dropped (7 Nov)

On the two reviewed matches' checked rallies and answers (M1 first, M2 second):

| Idea | Result |
| --- | --- |
| A "relance" with a jump becomes an attack | 59-68% of real attacks are jumped, but so are 26-30% of real relances: 6 fixed for 11 broken (M1) |
| A set sent over typed attack when the toucher jumped | M1 5 fixed, 3 broken; M2 8 fixed, 9 broken |
| A learned retyping of the rules' types (multinomial logit on the rule's type, neighbours', sides, touch count, timing, place), one match trained, the other tested | 940 → 942 of 1057 (M2), 749 → 751 of 839 (M1) at best; overfits |
| A rally's last contact typed floor turned into a touch when a player's wrists are at the ball | wrists within 0.15 box heights: M1 6 fixed, 6 broken; M2 10 fixed, 3 broken |
| A lower contact threshold where a player is at the ball (item 3 above) | missed touches under the threshold with a player there: 1 (M1), 7 (M2), against 78 and 82 false candidates |
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
