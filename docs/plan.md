# Plan in progress (1 Nov)

## Touches

Missed on the 129 checked rallies, 118 of 944: 71 no contact in the ball track, 40 outside a window, 7
removed after detection. 43 of the pipeline's 860 touches are false. `benchmarks/rallies/checked.py`
scores the windows on the whole match.

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

Next:

1. Score the gap filling (`tube` in `ev2.py`) on all 129 rallies. Check the rallies starting late, which
   follow the ball track.
2. If it holds, make it the pipeline's: a second pass when the frame rate is about twice the model's
   (a step of `round(fps / 30)`, so the school clips do not move), about 95 min on the M4 for this match.
3. Then the 7 touches removed after detection, the 43 false ones, and the ball model fine-tuned on the
   RTX 5080 only if the rest leaves it worthwhile.
4. Tell the owner to launch "Apprendre de mes réponses": it fills the "Progrès" tab with the new
   code. Without `--rerun`, `learn` only scores the old outputs. Report what improved and what did not.

Tried and dropped: see `benchmarks/rallies/README.md`.

## Page: being built

- **Mon match** (`web/src/components/MyMatch/`): pick a name, remembered; their story, touches to replay,
  best points, serve run, who sets whom, what they lead the team in, the card to save (no picture on
  the hosted page).
- **L'histoire du match** (`web/src/components/Story/`): the score gap rally by rally with the key
  moments, plain sentences per set, each moment replaying.

Upload only once the owner has seen them.

## Page: other ideas, not started

1. **Broadcast mode in 3D** (the owner's wish for the 3D scene, and open item "the ASPOM gymnasium"): the
   real gym, a TV camera following the ball and cutting to net-side angles on attacks, replays from the
   attacker's or blocker's point of view, generated French commentary. No footage, so the whole match can
   be public without consent. Needs a real 3D ball path: its height is only estimated today.
2. **Le résumé en 3 minutes**: a highlight reel of the longest rallies, comebacks and set points, behind the
   password in video, in 3D for everyone.
3. **Le coin du coach**: who sets whom and with what success, the score with each lineup, where serves cause
   trouble, three things to work on. Lineups are the least certain (about 9 players a team rotate in).
4. **Les trophées**: end-of-match awards ("Le Mur", "L'Infatigable", the longest rally). Positive only, never
   ranking faults: attribution is about 90% right and these are teammates.
5. **La saison**: each player's progress over matches and the team's form. Needs a second match.
