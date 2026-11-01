# Plan in progress (1 Nov)

## Touches

Missed on the 129 checked rallies, 101 of 945: 71 no contact in the ball track, 23 outside a window, 7 removed after
detection. 48 of the pipeline's 883 touches are false. `benchmarks/rallies/checked.py` scores the windows on the whole
match.

Done: `LIVE_SPEED` per second (812 -> 829 touches in windows, `side_holdout` 0.75 -> 0.86).

Running: WASB on frames t, t+2, t+4 over the whole match, into
`outputs/first_match/experiments/ball_step2.csv` (frame, x, y, peak). `ball.csv` is untouched. The scripts
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
still checked, same set scores. The hosted page is behind it by one floor contact (frame 186492).

Next:

1. The 23 touches outside windows and the 7 removed after detection, then the 48 false ones.
2. The 71 with no contact: filtering the extra detections better, or the ball model fine-tuned on the RTX 5080.

Tried and dropped: see `benchmarks/rallies/README.md`.

## Page: online

"Mon match" (`web/src/components/MyMatch/`), "L'histoire du match" (`web/src/components/Story/`) and "Les trophées"
(`web/src/components/Trophies/`), uploaded 1 Nov 22:03. The owner's rule on points is in `web.credited`.

## Page: built, not uploaded

"Le coin du coach" (`web/src/components/Coach/`): waits for the owner's "Mettre en ligne".

Tried and removed (owner's call, not useful enough; code in `3377048`): the score of each six and a serve map by zone.
From them: lineups from the positions, smoothed over 2 rallies each side, gave the first match 4 and 3 sixes whose
scores add up to the given sets; on clips with unreviewed names 4 and 7 sixes for 15 rallies.

## Page: lighter (1 Nov)

The players' positions are one file a minute (`positions/N.js`, 13 KB compressed), loaded as the replay reaches
them; the balls dropped between two players read theirs from `data.js` (`around`). Lighthouse, mobile, 3 runs on
localhost, the first match without footage: first load 1,824 -> 282 KB, LCP 2.73 -> 2.41 s, time to interactive
10.9 -> 3.05 s, blocking 664 -> 644 ms, score 80 -> 82 (desktop 99, 99). The first file loads 500 ms after mounting:
a script running before the paint is recorded counts as blocking it in Lighthouse's simulated LCP. Moving the review
screens to their own bundle would save 24 KB compressed, not done; `i18next` (15 KB) and `cn` (8 KB) stay.

## Page: other ideas, not started

- **Le résumé** and **personal links** came out as the smallest next steps: a button playing the story's
  moments back to back; a link opening the page on a player's Mon match.

1. **Broadcast mode in 3D** (the owner's wish for the 3D scene, and open item "the ASPOM gymnasium"): the
   real gym, a TV camera following the ball and cutting to net-side angles on attacks, replays from the
   attacker's or blocker's point of view, generated French commentary. No footage, so the whole match can
   be public without consent. Needs a real 3D ball path: its height is only estimated today.
2. **Le résumé en 3 minutes**: a highlight reel of the longest rallies, comebacks and set points, behind the
   password in video, in 3D for everyone.
3. **La saison**: each player's progress over matches and the team's form. Needs a second match.
