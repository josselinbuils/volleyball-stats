# Next steps from the review's answers (1 Nov)

What the first match's answers (`outputs/first_match/identity_answers.json`: 277 touches, 71
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
| match | a window with no serve gets the one the players' positions show (`match.unseen_serves`) | serves typed 108 → 131 of 137, labelled 43 of 43 within ±1 s, the owner's 6 added serves' players all matched | `side_holdout`: 2 serves added, both labelled |
| match | windows with 2+ floors and no touch dropped (`actions.no_play`) | 2 of the 6 "no play" windows, no rally lost | 50:00-60:00 F1 ±1 s 0.57 → 0.59, P 0.88 → 0.95 |

Scored with `benchmarks/attribution/answers.py outputs/first_match --rerank [--video data/first_match.mp4]`
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

1. Done: `learn` scores every step on the answers and the checked rallies (full labels) and keeps
   the history (`learn.json`); `wrists.json` caches the wrists' pose.
2. Next: cache the relances' pose (11.5 min) and the teams' looks (15.5 min) like `wrists.json`, so
   a rerun takes minutes; a `learn --rerun` (and a review button) that reruns from the caches,
   rekeys and scores.
3. Then: a settings search per step (contact threshold, wrist veto and margin, serve lead, rally
   rules, tie-breaks), a change kept only if it gains on the answers held out (sets 1-2 against set
   3, then the next match) and loses nothing on the school benchmarks; kept values in a committed
   `params.json` with the report.
4. Then: a learned attribution ranker (numpy logistic regression on distance, box size, wrists,
   side, track age) on the 277 touch answers and the school labels; a projection of the re-ID
   embeddings from the same/different pairs; the contact threshold where players crowd the ball from
   the added touches.
5. Asked of the owner: validate whole rallies (the unbiased labels) more than single questions; a
   few random easy touches as spot checks.

## Left, by value

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
