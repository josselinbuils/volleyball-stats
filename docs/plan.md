# Plan in progress (2 Nov)

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

Next:

1. The 73 touches still missed: mostly the ball model, fine-tuned on the RTX 5080.
2. The 46 false ones; ends with no whistle on 50:00-60:00, which the settings cannot reach; the merged attack and block.

Tried and dropped: see `benchmarks/rallies/README.md`.

## Page: online

"Mon match" (`web/src/components/MyMatch/`), "L'histoire du match" (`web/src/components/Story/`) and "Les trophées"
(`web/src/components/Trophies/`), uploaded 1 Nov 22:03. The owner's rule on points is in `web.credited`.

## Page: online since 2 Nov

"Le coin du coach" (`web/src/components/Coach/`) and "Mode TV" (README, `Watch/Broadcast.tsx`, `scene3d/hall.ts`).

The ball in 3D (`benchmarks/ball3d/bench.py`, first match, no 3D truth): the camera found at x 0.1, y 11.83, 3.93 m high (set up
on the net's line, about 6 m from the sideline, 3.6 m high: 7.3 m from it); path to the ball in the picture, median and 90%,
typical heights 93 and 205 px, fitted 8 and 77; median heights attack 2.66, block 2.60, serve 2.39, set 1.85, pass 1.29, dig 1.46.
Floor position found with the feet hidden, median: set 0.70 m, pass 0.94, dig 0.96, relance 1.66, attack 2.11, block 3.72, serve 2.90
(a serve's frame can be late, next_steps 12). No drag or spin; a flight over 2.2 s (a missed touch) is left out. Without a lens the
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

"Ton film" (`web/src/components/MyMatch/Film.tsx`, `helpers/film.ts`): a vertical film of under 45 s of a player's match in the page's 3D, 720x1280, made in
the viewer's browser and leaving it only if they save it: a title, up to 4 moments each played then replayed slowly, an end. It records live with `MediaRecorder`, so it takes the film's length,
the page must stay open, a slow device drops frames. Checked in headless Chrome only (10 frames a second on its software 3D): not yet on a phone.

## Page: players' movements (2 Nov)

The page showed each 0.1 s sample as it was: a jump every 0.1 s, 3.1% of moves in rallies over 7 m/s (depth mostly: a box's foot), players blinking in holes over 0.5 s. Now `web.natural_motion` at build (outliers, holes, a Gaussian of 0.2 s, for the positions' files only: stats stay on the tracking), the page's `playersAt` between samples, in both views, and bodies turning over 0.12 s (`benchmarks/players/motion.py`).

## Page: lighter (2 Nov, positions)

The first match's 67 position files, gzip: JSON per sample 821 KB, 12.3 a file; per person in columns 732; at 5 cm 450 (6.7 a file; 2.8 cm off at most, speeds unchanged).
Left aside: binary at 5 cm 373, which needs `fetch` and so no longer opens from `file://` (in base64 437); 10 cm 346, 7 cm off.
Files of 5 minutes (from 1): 34 KB each, 460 to 428 KB in all, the whole match in rallies 5 waits instead of 21, a wait barely longer (the request's time weighs more than the size: 76 ms for 13.6 KB, 104 for 29.7).

## Page: lighter (1 Nov)

The players' positions are one file a minute (`positions/N.js`, 13 KB compressed), loaded as the replay reaches
them; the balls dropped between two players read theirs from `data.js` (`around`). Lighthouse, mobile, 3 runs on
localhost, the first match without footage: first load 1,824 -> 282 KB, LCP 2.73 -> 2.41 s, time to interactive
10.9 -> 3.05 s, blocking 664 -> 644 ms, score 80 -> 82 (desktop 99, 99). The first file loads 500 ms after mounting:
a script running before the paint is recorded counts as blocking it in Lighthouse's simulated LCP. Moving the review
screens to their own bundle would save 24 KB compressed, not done; `i18next` (15 KB) and `cn` (8 KB) stay.

## Page: other ideas, not started

1. **La saison**: each player's progress over matches and the team's form. Needs a second match.
