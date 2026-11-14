# Action classification benchmark

`volleyball_stats.actions` types each contact of a rally (serve, pass, dig, set, attack, block,
floor, net) and gives its side of the net, by rules on the rally's structure: no training. Scored
on the typed contacts of [benchmarks/contacts](../contacts/README.md): tuned on `side_club` and
`side_long`, then run once on the held-out `side_holdout`.

## Run

```bash
uv run --group bench python benchmarks/actions/bench.py \
  data/benchmarks/side_club.mp4:outputs/benchmarks/ball/side_club_ball.csv:benchmarks/contacts/ground_truth/side_club.csv:outputs/benchmarks/players/side_club_players.csv \
  data/benchmarks/side_long.mp4:outputs/benchmarks/ball/side_long_ball.csv:benchmarks/contacts/ground_truth/side_long.csv:outputs/benchmarks/players/side_long_players.csv [--verbose]
uv run --group bench python benchmarks/actions/bench.py \
  data/benchmarks/side_holdout.mp4:outputs/benchmarks/ball/side_holdout_ball.csv:benchmarks/contacts/ground_truth/side_holdout.csv:outputs/benchmarks/players/side_holdout_players.csv
uv run python -m volleyball_stats.actions CONTACTS_CSV NET_CSV RALLIES_CSV --fps 29.97 --court COURT_JSON
```

The CLI reads the outputs of `contacts.py` and `rallies.py` and a calibration from `court.py`
(or `--net-x`, without floor detection), and writes `<clip>_actions.csv`: `frame,x,y,type,side`.

Three scores, pooled over the clips given:

- **truth**: the labelled contacts (positions from the ball track), rally windows and net crossings:
  the rules alone.
- **detected**: the contacts and crossings of `contacts.detect` (29.97 fps, net at x=612) in the
  labelled windows, matched one to one to the labelled contacts within ±2 frames.
- **pipeline**: `match.py`'s windows, contacts and crossings (`match.rally_windows`: spare balls by
  the camera masked, the court's scale, the serves of the players' CSV when given), the real chain.

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
2. **serve**: the first contact, unless a net crossing comes before it (the serve was not seen) or
   its floor projection lies under 8 m from the net, below the horizon (no serve is taken inside
   the court: typed dig). A window whose first contact comes before its start, so opens on it, is
   then no rally but the ball thrown back to the server: `actions.served` drops it before typing.
3. **block**: a touch within 0.33 s after an attack; its side is the attacker's opposite. It does not
   count as a touch, and the touch after it is a dig.
4. **net**: a touch before any crossing, after the serve: the serving side cannot touch it again.
5. Otherwise the touches since the last crossing count: **pass** (1st after the serve's crossing),
   **dig** (1st after any other crossing or a block), **set** (2nd), **attack** (3rd and later).
6. A **dig** that sends the ball straight to the other side (a crossing before the next contact, or
   the next contact on the other side, a floor included) is an **attack**, unless it is the rally's
   first contact (the reception of a serve nobody saw). From the first ASPOM
   match's review: the owner retyped 6 such digs as attacks and kept none as digs, viewers reported
   5 more ("Défense" → "C'est une attaque"); a pass sent straight over stays a pass (one validated
   rally). On the clips it changes one labelled contact, the tuning dig 577 that falls on the
   other side, labelled dig before this convention: truth 80 → 79 of 81, detected, pipeline and
   held-out unchanged (77/81, 71/81; 46/48, 40/48, 33/48). On the first match it turns about 22 digs into
   attacks, 6 of them the owner's corrections. Sets sent straight over were left: 1 retyped as an
   attack, 4 seen and kept, 20 never seen.

7. After the relances (`mark_relances`, `by_flight`): a **relance** as a team's first touch (after the other side's touch but
   a serve, or after a block) is a **dig**, as its second a **set** (`relances_by_touch`, the owner's rule of 14 Nov: both
   hands make a dig on the first touch, a set on the second, sent over or not, a relance on the third).

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
  data/benchmarks/side_club.mp4:outputs/benchmarks/ball/side_club_ball.csv:benchmarks/contacts/ground_truth/side_club.csv \
  data/benchmarks/side_long.mp4:outputs/benchmarks/ball/side_long_ball.csv:benchmarks/contacts/ground_truth/side_long.csv \
  data/benchmarks/side_holdout.mp4:outputs/benchmarks/ball/side_holdout_ball.csv:benchmarks/contacts/ground_truth/side_holdout.csv
```

## Limits

- The order rules are only as good as the contacts and crossings: a missed contact shifts the
  count (a missed set turns the attack into a set), a false one too. The pipeline score is bounded by
  `rallies.py` (3 of 7 held-out rallies found) and `contacts.py` (blocks merged into their attack).
- Floor away from the camera rests on the rally's last contact: it fails when the window ends before
  the dead ball (a fault whistle, a ball run cut short), when a touch after the floor is detected
  (a catch), and on balls landing far out. The ball's height from its parabola and the calibration
  (3D by physics, see [docs/literature.md](../../docs/literature.md)) was tried on the first match:
  real floors fit up to 2 m (2 Nov, [history.md](../../docs/history.md)).
- A ball into the net is only found after a serve. A rule at the net line (contact within a few
  pixels of it, ball then dropping without crossing) needs labelled examples: 2 today, both missed
  by the detector anyway.
- A touch from the third is an attack unless the pose makes it a relance ([Relances](#relances)) or,
  on calibrated footage, its flight does ([below](#attack-or-relance-from-the-flight-2-nov)); an
  attack on the second touch (setter dump) is a set.
- Sides assume a camera in the net plane; quality grades, set types and attack zones are not typed.
- 19 rallies, one match, one camera, one annotator; the tuning clips set the constants, and the
  held-out clip's 2 blocks and 1 net are too few to measure those rules.

## Attack or relance from the flight (2 Nov)

`actions.by_flight`, on calibrated footage with a lens, after the pose rule: an attack leaves from 2.1 m or higher, rising at under
6 m/s until the next contact (`ball3d.flight_places`, no player's feet in it); else a relance; a contact with no such flight
keeps the pose rule's type. A set that crosses the net within 1.3 s of its touch (SET_OVER_S) is the same case (an attack, or a relance by the flight; an attack with no flight known): the owner calls the slower ones sets. On the first match's checked rallies, 169 attacks and relances: pose 137, thresholds set on the other
two sets 144 (149 at their best on all; a logit on height, speed and rise 150 over 5 folds). All types: 764 -> 777 of 871.


## A learned type from the gesture (11-12 Nov, `learned/`, dropped for now)

The owner's reviewed types as labels: one example per pipeline contact of the checked rallies (917 and 1167; "none" for a
contact that is no touch, 46 and 73), a clip of 16 frames every 3 around it cut on the credited player and the ball
(`learned/dataset.py`, about 9 min a match), trained on one match and tested on the other, both ways. The bar set before:
15 more right types on each match.

    uv run python benchmarks/actions/learned/dataset.py MATCH [RUN]       # outputs/benchmarks/act/MATCH/ (ACT_DIR for another folder)
    uv run python benchmarks/actions/learned/videomae.py TRAIN TEST video  # also dino.py, skel.py: outputs/benchmarks/act/preds/
    uv run python benchmarks/actions/learned/evaluate.py videomae-video

Right types of the touches found, the rules at 794 of 871 (first match) and 983 of 1094 (second). "Alone" is the model's
own class; "over the rules" replaces the rules' type above a confidence tuned on the training match; "stacked" is a small
head on the model's scores, the rules' type and what the rules see (order, timing, side, the ball's 3D height and speeds),
trained on the training match's out-of-fold scores.

| Model | First match: alone / over the rules / stacked | Second match |
| --- | --- | --- |
| DINOv2-base frozen, 3 frames | 592 / 794 / 794 | 758 / 983 / 992 |
| DINOv2-base frozen, 16 frames in a temporal head | 573 / 794 / 800 | 744 / 985 / 991 |
| The toucher's skeleton and the ball's path (YOLO11m-pose on the clip) | 685 / 782 / 803 | 859 / 980 / 993 |
| The same with the rules' features in the head | 783 / 797 / 803 | 978 / 997 / 991 |
| VideoMAE-base fine-tuned on the clips (about 6 min a direction on the 5080) | 660 / 792 / **810** | 821 / 986 / **998** |
| VideoMAE with the rules' features fused in | 792 / 802 / 805 | 995 / 996 / 990 |

Alone, every model is far under the rules (pass or dig, dig or set: the order of the touches says it, the gesture hardly).
Stacked, each gains 0 to 16; the best, VideoMAE stacked, +16 and +15: at the bar, and the variants differ by as much. Its
fixes: attack for relance and back, a pass or a set the rules called floor; it breaks relance into dig 6 times on the
first match (the owner's call there is the player's intent, `docs/corrections_log.md`). None tells a false touch: at best
14 of 73 caught for 8 real touches lost.

On the pipeline with the play model (`ACT_DIR=act-play`, the set built on the run `play-eskb`; the rules at 800 of 873 and
1032 of 1129, some of the floors already fixed): VideoMAE stacked +14 and +12, under the bar. Not wired in: a second
345 MB model and a decoding pass around every contact for about 13 types of 95 a match. To try again with a third reviewed
match in the training set (the models alone are weak for lack of examples: about 900 a match).
