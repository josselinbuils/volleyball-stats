# Action classification benchmark

`volleyball_stats.actions` types each contact of a rally (serve, pass, dig, set, attack, block,
floor, net) and gives its side of the net, by rules on the rally's structure: no training. Scored
on the typed contacts of [benchmarks/contacts](../contacts/README.md): tuned on `side_club` and
`side_long`, then run once on the held-out `side_holdout`.

## Run

```bash
uv run --group bench python benchmarks/actions/bench.py \
  data/side_club.mp4:outputs/ball/side_club_ball.csv:benchmarks/contacts/ground_truth/side_club.csv \
  data/side_long.mp4:outputs/ball/side_long_ball.csv:benchmarks/contacts/ground_truth/side_long.csv [--verbose]
uv run --group bench python benchmarks/actions/bench.py \
  data/side_holdout.mp4:outputs/ball/side_holdout_ball.csv:benchmarks/contacts/ground_truth/side_holdout.csv
uv run python -m volleyball_stats.actions CONTACTS_CSV NET_CSV RALLIES_CSV --fps 29.97 --court COURT_JSON
```

The CLI reads the outputs of `contacts.py` and `rallies.py` and a calibration from `court.py`
(or `--net-x`, without floor detection), and writes `<clip>_actions.csv`: `frame,x,y,type,side`.

Three scores, pooled over the clips given:

- **truth**: the labelled contacts (positions from the ball track), rally windows and net crossings:
  the rules alone.
- **detected**: the contacts and crossings of `contacts.detect` (29.97 fps, net at x=612) in the
  labelled windows, matched one to one to the labelled contacts within ±2 frames.
- **pipeline**: the same in the windows of `rallies.py` (whistles from the video), the real chain.

Unclear contacts (empty type) are not scored. `-` in the tables is a labelled contact with no
detection, or a detection with no labelled contact. The court is fitted by least squares on the
7 line landmarks of [benchmarks/court/ground_truth/side_club.json](../court/ground_truth/side_club.json)
(no lens model, RMS 8.5 px; the posts are left out, their distance to the court being unknown); the
three clips share the camera.

No type was added to the ground truth: the 4 unclear touches of the tuning clips stay unclear on
the crops (net cord or block 3 frames after a crossing, a third-touch bump, a deflection 3 frames
before the floor, a touch 2 frames after the floor).

## Rules

In frame order, within a rally window (`rallies.py` windows start 0.33 s earlier, as they start
1-7 frames after the serve contact):

1. **floor**: the contact's floor projection (court calibration) lies on the near part of the court,
   court y ≥ 2 m toward the camera; or the contact is the rally's last and projects on the court
   (y ≥ -4.5, the far sideline). Every contact after a floor is a floor. Projections more than 2 m
   outside the court are ignored: balls in the air, or above the horizon, which map behind the
   camera.
2. **serve**: the first contact, unless a net crossing comes before it (the serve was not seen).
3. **block**: a touch within 0.33 s after an attack; its side is the attacker's opposite. It does not
   count as a touch, and the touch after it is a dig.
4. **net**: a touch before any crossing, after the serve: the serving side cannot touch it again.
5. Otherwise the touches since the last crossing count: **pass** (1st after the serve's crossing),
   **dig** (1st after any other crossing or a block), **set** (2nd), **attack** (3rd and later).

**Side**: left or right of the net's image line, the line through the calibrated net feet on both
sidelines (`--net-x` without a calibration). The camera stands (nearly) in the net plane, so the plane
projects to that line whatever the ball's height. The floor projection's sign (court x) is not used:
an airborne ball projects farther from the camera, |x| grows by H/(H−h) for a camera at height H,
and flips sign above the horizon (camera ≈3 m high here, horizon at y≈196 px).

Why floor level needs the calibration: from one image point a ball in the air and a ball on the floor
farther away look the same. Near the camera, digs project under 1.3 m and floor bounces from 2.4 m
(7 of 10 tuning floors); far from it, only the last contact can be told apart, because a ball played
high or far projects beyond the far sideline (the last contacts that are not floors, a dig and an
attack, at -6.5 m and -16 m; the last floors from -2.9 m).

Constants, from the tuning clips, each inside a plateau where the tuning scores do not move: block window 0.27-0.63 s, `FLOOR_Y` 1.3-2.4 m, `LAST_FLOOR_Y` -6 to -2.9 m, margin 1-5 m.

## Results

| Score | Tuning (12 rallies, 81 typed contacts) | Held-out (7 rallies, 48 typed contacts) |
| --- | --- | --- |
| truth | **0.988** (80/81) | **0.958** (46/48) |
| detected | **0.951** (77/81); 0.987 of the 78 found | **0.833** (40/48); 1.000 of the 40 found |
| pipeline | 0.877 (71/81); 0.959 of the 74 found | 0.292 (14/48); 1.000 of the 14 found |
| sides agreeing with the labelled crossings (truth) | 82/83 | 50/51 |

The side check takes the first contact's side and flips it at each labelled crossing (blocks
excluded). The one disagreement on each set is a floor bounce under the net, 10 px from its line
after a dig (tuning) and 4 px after a block (held-out): either side is defensible.

### Tuning: side_club + side_long

Truth (rows labelled, columns predicted):

| | serve | pass | dig | set | attack | block | floor | net | recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| serve | 11 | | | | | | | | 1.00 |
| pass | | 10 | | | | | | | 1.00 |
| dig | | | 12 | | 1 | | | | 0.92 |
| set | | | | 19 | | | | | 1.00 |
| attack | | | | | 16 | | | | 1.00 |
| block | | | | | | 1 | | | 1.00 |
| floor | | | | | | | 10 | | 1.00 |
| net | | | | | | | | 1 | 1.00 |

Detected:

| | serve | pass | dig | set | attack | block | floor | net | - | recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| serve | 11 | | | | | | | | | 1.00 |
| pass | | 10 | | | | | | | | 1.00 |
| dig | | | 12 | | 1 | | | | | 0.92 |
| set | | | | 18 | | | | | 1 | 0.95 |
| attack | | | | | 16 | | | | | 1.00 |
| block | | | | | | | | | 1 | 0.00 |
| floor | | | | | | | 10 | | | 1.00 |
| net | | | | | | | | | 1 | 0.00 |
| - | 1 | | | | | | | | | |

- The one rule error: a third touch labelled dig (a bump saving a bad set, `side_club` 4024) is
  typed attack.
- Detected: the 3 other errors are the detector's misses (a set, the block 3 frames after its
  attack, the serve into the net where the tracker loses the ball); its one false contact (the ball
  entering at the top edge before the first pass) is typed serve.
- Pipeline: the 5 serves `rallies.py` starts after are recovered by the 0.33 s lead (6/11 without
  it). 4 floor bounces fall outside the windows: 3 later bounces of a dead ball, and the floor of a
  window ending 7 frames early. The dig before that floor is then the window's last contact and
  becomes the floor, like a pass in a window closed by a fault whistle with the ball in the air.

### Held-out: side_holdout

Run once, after the rules and constants were fixed.

Truth:

| | serve | pass | dig | set | attack | block | floor | net | recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| serve | 7 | | | | | | | | 1.00 |
| pass | | 7 | | | | | | | 1.00 |
| dig | | | 6 | | | | | | 1.00 |
| set | | | | 11 | | | | | 1.00 |
| attack | | | | | 9 | | | | 1.00 |
| block | | | | | | 2 | | | 1.00 |
| floor | | | 1 | | | | 4 | | 0.80 |
| net | | | | 1 | | | | | 0.00 |

Detected:

| | serve | pass | dig | set | attack | block | floor | net | - | recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| serve | 5 | | | | | | | | 2 | 0.71 |
| pass | | 7 | | | | | | | | 1.00 |
| dig | | | 6 | | | | | | | 1.00 |
| set | | | | 11 | | | | | | 1.00 |
| attack | | | | | 8 | | | | 1 | 0.89 |
| block | | | | | | | | | 2 | 0.00 |
| floor | | | | | | | 3 | | 2 | 0.60 |
| net | | | | | | | | | 1 | 0.00 |
| - | 1 | | 1 | 1 | 1 | 2 | | | | |

- Truth, 2 errors: a floor bounce projecting 13 m past the far sideline (an out ball, or a ball
  position above the floor) is typed dig; a dig into the net after a crossing is typed set (the net
  rule only covers the serve).
- Detected: every contact found is typed right; all 8 errors are the detector's (see the contacts
  held-out check). 2 serves hidden in the track; an attack and its block in a joust, and another
  block, detected 3-4 frames late, typed attack and block but outside ±2 (they count as missed and
  false); 2 floor bounces and the ball into the net not detected. The 3 other false contacts are typed set, dig and
  serve (the first detection when the serve is missed).
- Pipeline: `rallies.py` finds 3 of the 7 rallies (the soft or masked end whistles of its held-out
  check); inside them, 14/14.

Each floor rule on its own (truth / detected): without the last-contact rule, 77/81 and 73/81 on
tuning, 42/48 and 37/48 held-out; without a calibration (no floor at all), 70/81 and 67/81 on
tuning, 42/48 and 37/48 held-out. On `side_holdout` every floor found comes from the last-contact
rule: no floor bounce there is close enough to the camera for the first one.

## Relances

`actions.mark_relances` retypes as `relance` (free ball) an attack played without attacking: the
ball not above the player's box top and the feet lifted under 0.1 player height over the previous
second, on boxes from YOLO11m-pose run on the attack frames only (the pose model's boxes leave out
the motion-blurred hitting arm; its wrists miss that arm too, so hands are not counted).
`relance.py` runs it on every labelled 3rd-or-later touch of the three clips:

| Label | Typed attack | Typed relance |
| --- | --- | --- |
| attack | 24 | 1 |
| relance (labelled dig) | 0 | 1 |
| unclear | 0 | 3 |
| set (4th touch) | 1 | 0 |

The 3 unclear touches are, by eye, two two-handed forearm passes at chest height and a low save
around the knees, all feet down. The false relance is a crowded net (side_long 13662): the rule
takes the player in front, ball at her head, while the hitter jumps behind her. The jump alone is
weak at 720p: about half the youth attacks show no measurable lift of the box bottom.

```bash
uv run python benchmarks/actions/relance.py \
  data/side_club.mp4:outputs/ball/side_club_ball.csv:benchmarks/contacts/ground_truth/side_club.csv \
  data/side_long.mp4:outputs/ball/side_long_ball.csv:benchmarks/contacts/ground_truth/side_long.csv \
  data/side_holdout.mp4:outputs/ball/side_holdout_ball.csv:benchmarks/contacts/ground_truth/side_holdout.csv
```

## Limits

- The order rules are only as good as the contacts and crossings: a missed contact shifts the
  count (a missed set turns the attack into a set), a false one too. The pipeline score is bounded by
  `rallies.py` (3 of 7 held-out rallies found) and `contacts.py` (blocks merged into their attack).
- Floor away from the camera rests on the rally's last contact: it fails when the window ends before
  the dead ball (a fault whistle, a ball run cut short), when a touch after the floor is detected
  (a catch), and on balls landing far out. The ball's height from its parabola and the calibration
  (3D by physics, see [docs/literature.md](../../docs/literature.md)) would type every floor bounce.
- A ball into the net is only found after a serve. A rule at the net line (contact within a few
  pixels of it, ball then dropping without crossing) needs labelled examples: 2 today, both missed
  by the detector anyway.
- Every touch from the third is an attack: a bump saving a bad set, or a free ball, too; an attack
  on the second touch (setter dump) is a set. Pose or the ball's speed after the touch would split
  them.
- Sides assume a camera in the net plane; quality grades, set types and attack zones are not typed.
- 19 rallies, one match, one camera, one annotator; the tuning clips set the constants, and the
  held-out clip's 2 blocks and 1 net are too few to measure those rules.
