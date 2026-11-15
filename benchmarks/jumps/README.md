# Attack jump benchmark

`jumps.measure` against hand labels: each attack's takeoff, landing and run-up start, and from them the contact's
timing against the flight's top, for the coach's advice on attacks.

## Run

```bash
uv run python benchmarks/jumps/bench.py [--heldout] [--verbose] [--sweep]
uv run python benchmarks/jumps/sheets.py MATCH OUT_DIR [COUNT]   # the sheets the labels come from
```

The poses come from each match's `jumps.json`, made on the first run (about 3 s an attack on the M4: 6 min for the
first match's 134 attacks, 8 min for the second's 174).

## Ground truth

`ground_truth/labels.csv`: 20 attacks drawn at random from each match's `actions.csv` (seed 0), labelled by Claude on
`sheets.py`'s crops at 50 fps: whether the outlined player is the attacker and jumps, the first frame with both feet off
the floor (`takeoff`), the first back on it (`landing`), the hand on the ball (`contact`, when seen) and the frame the
final run-up starts (`start`, `none` for a standing jump; every 5 frames). 3 outlined players are not the attacker, 4
hit with no jump, 2 of the 33 jumps are jump sets; the labellers give ±1-5 frames on takeoff and landing. One takeoff
checked again on 2x crops of the feet (attack 126339): the label stands to the frame.

## Method

YOLO11m-pose on a crop around the attacker's track over ±0.8 s. The lower ankle's path in the picture: a jump where it
stands 0.15 m over its lower envelope (the floor) near the contact; the edges where its fastest rise and fall slow under
0.2 of their speed, then moved by the heel (+3 frames at takeoff, -2 at landing). A flight outside 0.3-0.8 s has a foot
hidden at one end: that end mirrors the other about the ankle's highest, else it is dropped. The hit: within 0.24 s of
the ball's contact, the frame the ball is seen nearest a wrist. The run-up: going back from takeoff on the tracked feet,
until the player came under 0.1 m nearer the net over 0.5 s.

Checked only on the ASPOM matches' 4K footage with its lens calibrated. Without a camera model (a calibration with no
lens, the 720p school clips) it measures nothing: a player's box height as the scale there gave 3 jumps of 9 attacks
on `side_holdout`, the 2 checked by eye wrong (a crouched dig then a run, a serve).

## Results (7 Nov)

| | First match | Second match |
| --- | --- | --- |
| Jumps measured / missed / false | 10 / 5 / 1 | 14 / 2 / 0 |
| Takeoff within 2 frames | 8 of 10 | 14 of 14 |
| Landing within 2 frames | 9 of 10 | 12 of 14 |
| Hit within 2 frames of the hand on the ball | 8 of 8 | 9 of 10 |
| Hit against the top, median error | 25 ms (top alone 15) | 25 ms (top alone 10) |
| … within 60 ms | 10 of 10 | 12 of 14 |
| Run-up start's distance to the net, median error | 0.12 m | 0.08 m |

The heel's shift and the speed threshold are the same on both matches; the run-up's from the first. On the 27
attacks with the hand on the ball labelled, the ball's contact frame (`contacts.py`) is within 2 frames 20 times and
within 4 frames 21 times, 5-15 frames off on 6; the hit 24 and 27 times (the higher wrist's highest frame: 21 and 24).
Timing within 60 ms went from 7 of 10 and 8 of 12 with the contact frame to 10 and 10 with the hit; the 2 left are
a foot hidden at one end of the flight. Mirroring that end (7 Nov) brought 2 of the second match's 4 missed jumps
back (timing off by 10 and 60 ms), none on the first; of all attacks, 86 -> 91 of 134 and 98 -> 116 of 174 get a jump:
the others have none, or a foot hidden.

## The hips' check (15 Nov)

The height came from the flight time alone: one frame off at each end moves a 0.6 s flight's 44 cm by about 12 cm, and the
owner found records that looked wrong (a 71 cm jump). The hips free-fall with the player (their path fitted with a free
curvature gives g at 10.2 m/s2, 10-90%: 8.5-12), so their rise from the frame before takeoff to their highest is a second
reading of the height. Where the two part by over 0.2 m an edge of the flight is wrong, and the jump is dropped
(`jumps.AGREE_M`). Against the labelled flights' heights (the labellers' ±1-5 frames are about ±5-10 cm), before -> after:

| | Jumps | Height error, median | 90% | Worst |
| --- | --- | --- | --- | --- |
| First match | 10 -> 7 | 6.0 -> 5.9 cm | 16.8 -> 16.8 | 16.8 -> 16.8 |
| Second match | 14 -> 11 | 4.5 -> 2.8 | 22.7 -> 8.1 | 30.3 -> 8.7 |
| First match, held out | 11 -> 11 | 2.4 -> 2.4 | 10.3 -> 10.3 | 13.1 -> 13.1 |
| Second match, held out | 13 -> 11 | 6.4 -> 6.1 | 22.2 -> 9.2 | 33.1 -> 12.2 |

On the three matches' attacks, 112 -> 96, 138 -> 114 and 144 -> 130 jumps; the highest left 53, 64 and 60 cm (were 71, 67,
64). Tried and dropped: the hips' rise alone (median error 10 cm), its mean with the flight time (90% 18.3 cm), and, where
the two part, the half flight from the hips' highest to the nearer edge that agrees with them (no jump brought back right,
one 78 cm off).

## Held out (7 Nov)

`ground_truth/heldout.csv`: a second draw of 40 attacks (seed 7, 20 per match, none of the first 40), labelled the same
way after every setting above was chosen, never tuned on (`bench.py --heldout`). 35 outlined players are the attacker,
30 of them jump.

| | First match | Second match | Both, against the tuning set's |
| --- | --- | --- | --- |
| Jumps measured / missed / false | 11 / 2 / 0 | 13 / 2 / 0 | 24 of 28, none false (24 of 31, 1 false) |
| Takeoff within 2 frames | 8 of 11 | 10 of 13 | 18 of 24 (22 of 24) |
| Landing within 2 frames | 11 of 11 | 9 of 13 | 20 of 24 (21 of 24) |
| Hit within 2 frames of the hand on the ball | 7 of 7 | 12 of 13 | 19 of 20 (17 of 18) |
| Hit against the top, median error, within 60 ms | 30 ms, 10 of 11 | 20 ms, 10 of 13 | 20 of 24 (22 of 24) |
| Run-up start's distance to the net, median error, within 0.5 m | 0.24 m, 7 of 10 | 0.10 m, 11 of 12 | 18 of 22 (17 of 21) |

## The same players in both matches (7 Nov)

The 6 players with 4 measured attacks on a teammate's set or more in both matches (`web.match_data`'s contacts, reviewed
players), their medians from one match to the other: timing against the top correlates 0.93 (median gap 10 ms), the
carry towards the net 0.93 (0.10 m), the jump height 0.88 (3 cm), the run-up 0.43 (0.68 m). The first three read as a
player's own habits; the run-up's length moves from match to match (or with the play): its tip is gone from the page
(7 Nov). Where the run-up starts holds better (0.71, median gap 0.27 m; the takeoff point 0.44), still short of the
others. The jump height feeds "Mon match" ("Détente") and a trophy ("Le Ressort").

"Le saut d'attaque" from 5 jumps: 5 random measured attacks of a player give the same tips as all of theirs 69% of
the time (the 12 players with 8 or more on a set, both matches, 200 draws each), 82% for the 7 with 12 or more, and 8
attacks 87%. The timing tips almost never flip (0-2%), the run-up and carry ones do (6-20%), near their limits.

## Against the attacks' results (7 Nov)

239 measured attacks with a result on the two reviewed matches, in thirds of each measure: hit within 23 ms of the top,
10% faults (18-19% further off); jumps over 0.38 m, 32% points (18% under 0.28 m); carry over 0.66 m, 24% faults (11-13%
under it); run-ups under 0.77 m, 22% points (28-31% over it). About 80 a third and correlations only, but each of "Le
saut d'attaque"'s tips points the way the results do.

## Blocks (7 Nov, exploration: nothing on the page)

`ground_truth/blocks.csv`: 30 defenders within 1.5 m of the net at random attacks (15 per match, seed 1), labelled by
Claude like the attacks: whether they jump, takeoff and landing (the frame is the attack's contact). With `CONTACT_S`
0.4 (a block is not at the attack's contact): of 14 real jumps 11 found, all within 60 ms of the labelled flight's top
(median 30 ms); 2 false jumps among the 15 who stay down, both over 0.7 s of flight with under 0.33 m of ankle lift (a
player backing away from the camera, a box over two players): keeping flights of 0.7 s or less and lifts of 0.33 m or
more keeps the 11 and drops the 2. The labelled blocks top 20-390 ms after the attack's contact frame, median 180 ms;
measured on every defender at the net with that filter, 185 ms (second match) and 225 ms (first), 4-5% before it. That
is mostly the ball's way to the net: against its first net crossing after the attack (`net.csv`, within 0.8 s), the
blocks with no block touch after them top a median 30 ms after it (25-75%: -42 to +110 ms, 128 jumps); those followed by
a block touch, a median 5 ms after that touch (-40 to +48 ms, 38 jumps). The blockers top when the ball reaches them:
no sign of late (or early) blocks.
