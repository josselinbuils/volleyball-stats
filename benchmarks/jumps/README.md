# Attack jump benchmark

`jumps.measure` against hand labels: each attack's takeoff, landing and run-up start, and from them the contact's
timing against the flight's top, for the coach's advice on attacks.

## Run

```bash
uv run python benchmarks/jumps/bench.py [--verbose] [--sweep]
uv run python benchmarks/jumps/sheets.py MATCH OUT_DIR [COUNT]   # the sheets the labels come from
```

The poses come from each match's `jumps.json`, made on the first run (about 3 s an attack on the M4: 6 min for the
first match's 134 attacks, 8 min for the second's 174).

## Ground truth

`ground_truth/labels.csv`: 20 attacks drawn at random from each match's `actions.csv` (seed 0), labelled by Claude
on `sheets.py`'s crops at 50 fps: whether the outlined player is the attacker and jumps, the first frame with both feet
off the floor (`takeoff`), the first back on it (`landing`), the hand on the ball (`contact`, when seen) and the frame
the final run-up starts (`start`, `none` for a standing jump; every 5 frames). 3 outlined players are not the attacker,
4 hit with no jump, 2 of the 33 jumps are jump sets; the labellers give ±1-5 frames on takeoff and landing. One takeoff checked again on 2x crops of the feet
(attack 126339): the label stands to the frame.

## Method

YOLO11m-pose on a crop around the attacker's track over ±0.8 s. The lower ankle's path in the picture: a jump where it
stands 0.15 m over its lower envelope (the floor) near the contact; the edges where its fastest rise and fall slow
under 0.2 of their speed, then moved by the heel (+3 frames at takeoff, -2 at landing). A flight outside 0.3-0.8 s
has a foot hidden at one end: that end mirrors the other about the ankle's highest, else it is dropped. The hit: within 0.24 s of the ball's contact, the frame the ball is seen nearest a wrist. The run-up: going back from takeoff on the tracked feet, until the player came under 0.1 m
nearer the net over 0.5 s.

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
