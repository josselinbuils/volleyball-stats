# Next steps from the review's answers (1 Nov)

What the first match's answers (`outputs/first_match/identity_answers.json`: 277 touches, 71
added, 34 rallies, 23 type fixes, 80 results) and the viewers' 18 reports taught the pipeline,
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

None of the above is in its outputs: they take a pipeline rerun (owner's go; backup in
`outputs/first_match/backup-before-rally-fix/`). What a rerun would bring, measured on the current
outputs:

- Rallies (31 Oct fixes, `match.rally_windows` as it stands, cached in the session's
  `windows_now.json`, 137 windows): it opens the rallies of the owner's added touches at 1:45
  (4853-5348), 2:07 (6161-6612), 2:37 (7688-9497) and covers the 17 s rally of 4:13 (12660-14086,
  14 touches added by hand). Still missed: the first rally's serve at 0:09 (window from 0:16.6), a
  serve at 11:20 (34013), 18:38 (55893), 19:05 (57277), a block at 17:17 (51853), passes at 0:48 and
  26:13.
- Attribution: 28 picks change, 20 of them already answered (the answers win): little for this
  match, the gain is for the next ones.
- `serve_starts` moves about 30 window starts 0.1-0.6 s earlier (to their serve + 0.33 s).
- The answers stay valid: they point at frames (touches) and rally starts; a rally whose start
  moves loses its rally answers (`rally`, `join`, `added`'s `start`), so check
  `identity_answers.json`'s `added` starts against the new `rallies.csv` after a rerun.

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

## Tried and dropped (1 Nov)

On the 135-136 answered touches, tie-breaks other than the bigger box: the smaller box 65, the ball
nearest the box centre 66, nearest its centre x 75, an anchor per type 80, a track seen at the frame
first 77. Pose alone with no veto: 102-105 depending on margin and confidence; the veto alone (the
attribution README's 720p rule) 101.
