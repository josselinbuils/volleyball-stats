# Contact attribution benchmark

`volleyball_stats.attribution` says which player track touched the ball at each typed contact
(`contacts.py` + `actions.py`), or none (floor, net). Scored against hand-labelled touchers of every
labelled contact of [benchmarks/contacts](../contacts/README.md): tuned on `side_club` and
`side_long`, then run once on the held-out `side_holdout`.

## Use

```bash
uv run python -m volleyball_stats.attribution ACTIONS_CSV PLAYERS_CSV --fps 29.97 [--out DIR]
```

Reads the actions CSV of `actions.py` or `match.py` and the tracks of `players.py`, writes
`<clip>_attribution.csv`: `frame,x,y,type,side,track` (`track` empty for no player). From Python,
`attribution.attribute(typed, rows, fps)` returns the track (or None) per typed contact, and
`attribution.read_players(path)` reads a players CSV back into `players.Row`s. No model, no video:
1,500 contacts take 0.1 s.

## Run

```bash
uv run --group bench python benchmarks/attribution/bench.py side_club side_long [--verbose] [--pose]
uv run --group bench python benchmarks/attribution/bench.py side_holdout
```

Each clip reads `data/CLIP.mp4` (only with `--pose`), `outputs/ball/CLIP_ball.csv`,
`outputs/players/CLIP_players.csv` and both ground truths. The player tracks are `players.py` on the
whole clips with the court fitted by least squares on the 7 line landmarks of
[benchmarks/court/ground_truth/side_club.json](../court/ground_truth/side_club.json) (same camera in
the three clips, as in the players benchmark):

```bash
uv run --group bench python -c "
import json; from pathlib import Path; from volleyball_stats import court
p = json.loads(Path('benchmarks/court/ground_truth/side_club.json').read_text())['points']
court.fit({n: tuple(v) for n, v in p.items() if not n.startswith('post')}, ransac=False).save(Path('outputs/court/side_club_lines.json'))"
for clip in side_club side_long side_holdout; do
  uv run --group bench python -m volleyball_stats.players data/$clip.mp4 outputs/court/side_club_lines.json --out outputs/players
done
```

Whole clips rather than windows around the contacts: the method needs a track around each contact
only, but a track cut at a window edge loses the offline stitching and filtering of `players.py`.
13, 34 and 35 minutes on the M4 Pro (MPS), three clips in parallel. `players.track` crashes on
`side_long`: on a frame where BoT-SORT returns no track, `track_frames` indexes its 1-D empty output
(`tracks[:, [4, 7]]`); the tracks here were made with that output reshaped to `(0, 8)`, which is
the fix.

## Ground truth

`ground_truth/<clip>.csv`: one row per labelled contact of the contacts benchmark,
`frame,toucher,x1,y1,x2,y2,x,y`.

- `toucher`: `visible`, `occluded` (the toucher overlaps another player in the image), `none` (no
  player: floor and net contacts, and one unclear touch of `side_club`, 2079, where nobody touches
  the ball). No toucher was out of sight: every one shows at least an arm or a head.
- `x1..y2`: the toucher's box at the contact frame. Proposals came from YOLO11x at 1280 px with a
  0.05 threshold, a detector independent of the tracks scored; when none fitted the toucher (blur,
  a dive, two players in one box), the box was drawn by hand and `x,y` holds a point on the
  visible torso.
- Read on 2× crops of frames t-3, t-1, t, t+2 around the ball, with 3× zooms of t-3..t+2 for the
  doubtful ones (37 of 138); the toucher is the player whose arms or hands meet the ball and who
  sends it off.

| Clip | Contacts | Visible | Occluded | No player | Drawn boxes |
| --- | --- | --- | --- | --- | --- |
| `side_club` | 37 | 27 | 3 | 7 | 3 |
| `side_long` | 48 | 33 | 10 | 5 | 11 |
| `side_holdout` (held out, labelled before any method ran) | 53 | 39 | 8 | 6 | 7 |

## Metric

A predicted track is right when its box at the labelled contact frame has IoU ≥ 0.5 with the
labelled box or contains the labelled point; a track missing at that frame is scored on its box
interpolated over up to 0.17 s, as the method sees it. None is right only for `none` touchers.

- **truth**: the labelled contacts at their labelled frames, with the labelled types and the sides
  of `actions.classify_rally` (attribution alone). Headline: `typed`, the player contacts with a
  type (unclear touches excluded: the method needs the type).
- **detected**: `contacts.detect` in the labelled windows, typed by `actions.classify_rally`,
  matched one to one to the labelled contacts within ±2 frames (as in the actions benchmark); a
  labelled contact with no detection counts as wrong. Rows are the labelled types.
- 95% intervals: 2,000 bootstrap resamples of the contacts of each row.

## Method

Candidates are the tracks of the contact's side of the net (`actions.py`'s side; a block's side is
the blocker's), the team of a track being its median side (`players.py`). The toucher is the
candidate whose box is nearest to the ball, in box heights so that a near player 200 px tall and a
far one 60 px tall compare. Three additions, the first two from failures seen on the tuning clips,
the third from the first ASPOM match:

- **Tracks missing up to 0.17 s around the contact.** The detector drops the toucher at the very
  frames of a touch: blurred arms, a dive, a teammate in front, the setter in the net crowd. 8 of
  the 12 tuning touchers with no box at the contact frame had a track 1-5 frames away; such a track
  stays a candidate, its box interpolated over the gap. 4-6 frames score the same, 3 and 8 frames
  two fewer.
- **An arm above the head for serves, attacks and blocks.** The detector leaves the blurred
  hitting arm out of the box (as the pose model does, see the actions benchmark's relances): the
  ball is up to 0.6 box heights above the hitter's box (over 0.15 in 11 of the 16 tuning
  attacks), while a teammate standing by has it at her head. For these types the box reaches 0.5
  heights higher; among the candidates whose reach holds the ball, the nearest plain box wins. Any
  reach from 0.3 to 1.0 scores the same.
- **Feet past the net at the contact frame.** A track that swaps players in the net crowd keeps the
  median side of the player it followed first: on the first ASPOM match a block was given to a
  player of the other team, his feet 0.6 m past the net. A candidate whose feet stand over
  `SIDE_M` = 0.5 m past the net on the other side at the contact frame is out. It changes no
  labelled contact here (0, 0.25, 0.5 and 1 m score the same) and that one block on the match.

Comparison, typed contacts (all 4 steps are `bench.py`'s methods):

| Method | Tuning truth | Tuning detected | Held-out truth | Held-out detected |
| --- | --- | --- | --- | --- |
| Nearest box, either side (baseline) | 50/70 (0.71) | 49/70 (0.70) | 31/42 (0.74) | 28/42 (0.67) |
| Nearest box of the contact's side | 50/70 (0.71) | 49/70 (0.70) | 32/42 (0.76) | 28/42 (0.67) |
| + tracks missing up to 0.17 s | 56/70 (0.80) | 55/70 (0.79) | 32/42 (0.76) | 29/42 (0.69) |
| + an arm above serves, attacks, blocks | 58/70 (0.83) | 56/70 (0.80) | 33/42 (0.79) | 30/42 (0.71) |
| **+ feet past the net at the contact frame out (`attribute`)** | **58/70 (0.83)** | **56/70 (0.80)** | **33/42 (0.79)** | **30/42 (0.71)** |
| + pose veto on sets, passes, digs (`--pose`, not in the module) | 59/70 (0.84) | 59/70 (0.84) | 35/42 (0.83) | 32/42 (0.76) |

The side filter alone changes one contact: at the contact frame an opponent is rarely the nearest
box, the net separating the teams in the image. It matters for blocks and touches at the net.

### Results of `attribute`

| Type | Tuning truth | Tuning detected | Held-out truth | Held-out detected |
| --- | --- | --- | --- | --- |
| serve | 11/11 | 11/11 | 7/7 | 5/7 |
| pass | 7/10 | 7/10 | 4/7 | 4/7 |
| set | 16/19 | 15/19 | 10/11 | 10/11 |
| attack | 13/16 | 13/16 | 6/9 | 7/9 |
| dig | 11/13 | 10/13 | 4/6 | 4/6 |
| block | 0/1 | 0/1 | 2/2 | 0/2 |
| **typed** | **58/70, 0.83 [0.74-0.91]** | **56/70, 0.80 [0.70-0.89]** | **33/42, 0.79 [0.67-0.90]** | **30/42, 0.71 [0.57-0.83]** |
| unclear touches | 3/3 | 0/3 | 3/5 | 3/5 |
| no player (floor, net) | 11/12 | 10/12 | 6/6 | 3/6 |

- Detected: among the labelled contacts `contacts.detect` finds, attribution is as good as on the
  labelled ones: 56/68 on tuning (0.82), 30/37 held-out (0.81). The end-to-end loss is the
  detector's misses: 2 held-out serves hidden in the ball track, 2 blocks merged with their attack,
  an attack placed 4 frames late in a joust at the net, a tuning set and block. A contact detected
  1-2 frames off moves the ball, and the pick changes in crowds: 5 tuning contacts right on the
  label are wrong on the detection, 3 the other way.
- No player: floor and net contacts get no track when typed right; the detected misses are floor
  and net contacts the detector does not find, and the tuning error is the unclear touch 2079.

## Doubts

`ranked` gives each contact's candidates, nearest first; `gap_to_next`, the box heights between
the toucher and the next one. Two players about as near the ball is where wrong picks are (the
failures below): a gap under `DOUBT` = 0.05 makes the pick a doubt, written to `actions.csv`'s `gap`
column by `match.py` and asked in the review (`review.doubtful`).

| Clips | Doubts | Wrong picks among them | Wrong picks elsewhere |
| --- | --- | --- | --- |
| Tuning, truth | 14 of 70 | 5 of 14 | 7 of 56 |
| Tuning, detected | 15 of 68 | 6 of 15 | 6 of 53 |
| Held-out, truth | 6 of 42 | 3 of 6 | 6 of 36 |
| Held-out, detected | 7 of 37 | 2 of 7 | 5 of 30 |

Half of the doubts are wrong, against 1 in 6 of the other picks. Thresholds of 0.1 and 0.2 catch
7 and 9 of the 12 tuning errors but flag 24 and 33 touches. The review also asks the touches with no
player of their team (`unknown`), one player touching twice in a row in a rally, blocks aside
(`twice`, the less sure of the two; on the first match 9 of the 33 are the ball flying out of the
frame taken for a touch, answered "nobody"), and 10 spot checks among the others, to count the wrong
picks the doubts miss. `answers.py` scores the automatic picks on a match's answers, by reason and
by gap, to set `DOUBT` from them:

```bash
uv run python benchmarks/attribution/answers.py outputs/first_match
```

On the first ASPOM match (4K, 649 touches), the 138 touches asked were all answered: the automatic
pick was right for 10 of the 10 spot checks, 59 of the 86 close calls and 6 of the 33 players twice
in a row; 22 of the touches asked were no touch at all (mostly the ball flying out of the frame).

## Pose

`bench.py --pose` runs YOLO11m-pose at frames t-1, t and t+1 of each set, pass, dig and unclear
touch, takes the pose detection overlapping each candidate's box by IoU ≥ 0.5, and demotes a
candidate whose confident wrists (≥ 0.7) are all over 0.4 box heights from the ball. On the 112
typed contacts it wins 3 and loses none (1 tuning, 2 held-out), and end to end it adds 3 tuning and
2 held-out contacts. The 3: 10147 and 17251, a passer partly hidden by the player in front of her,
and 3136, a setter side by side with a teammate, the ball above both heads and the teammate's
wrists low.

It is not in the module: the 3 parameters are the best of 36 combinations on the tuning clips
(55-59 of 70 across them), it needs the video and three pose inferences per contact, and it cannot
help where it is most needed. The pose model misses the small and hidden touchers (no pose for a
setter 46 px tall), and in a crowd a pose detection overlaps two track boxes and lends one player's
wrists to the other. Scoring candidates by wrist distance instead (fallback: box distance) loses
1-3 contacts: a box contains the ball at distance 0, which no wrist beats. Wrists give no help on
attacks, where the hitting arm is blurred (actions benchmark).

## Tried and dropped

- Anchors per type (distance to a point above the box top for attacks, at mid-height for passes):
  43-47 of 70, against 50 for the plain box at that stage (before the gap step).
- The jump, as a tie-break for attacks: the hitter's feet rise by over 0.2 box heights in the last
  second in 8 of the 16 tuning attacks, but a player walking away from the camera rises as much
  (13662: the "jumper" walks to the net); no gain over the plain box.
- Excluding the previous contact's toucher (no player touches twice in a row): loses one contact,
  because track identities swap in the net crowd (one track is both the setter and the hitter of a
  rally).
- Not tried: the ball's path (the player the ball leaves from) and the last ground position of a
  jumping player. The remaining errors are two players overlapping in the image, a depth question a
  2D outgoing direction does not settle; court positions (where mid-jump feet are wrong) are used
  by no rule here. Worth trying with the 3D ball path.

## Failures

`attribute` on the labelled contacts: 12 tuning errors and 9 held-out, of two kinds.

- **The toucher has no track near the contact frame** (4 tuning: 2101, 3954, 4551, 11017; 4
  held-out: 4711, 4839, 8546, 15393). A passer bent low and a digger diving (3954, 4839: boxes 60
  and 46 px tall), touchers hidden behind a teammate or the net (2101, 4711, 8546, 15393), a blocker
  in the net crowd (11017). 3954 and 4551 are detected at the contact frame (confidence 0.34 and
  0.6, feet on the court) but in no kept track within 0.5 s: a track shorter than `players.py`'s
  15 frames, dropped by its offline pass, or one the tracker never confirmed. 66 of 70 tuning and
  38 of 42 held-out touchers have a track within 0.17 s: the ceiling of any rule on these tracks.
- **A wrong pick among tracked players** (8 tuning, 5 held-out), all two or three players
  overlapping in the image with the ball on or between their boxes: passes (451, 10147, 11214,
  17251), sets (9161, 14070, 3136), a diving digger beside a standing player (4024), and attacks at
  the net where a teammate's box is nearer the ball than the jumping hitter's (541, 13794, 14237,
  11576, 17400). The image gives no depth: a ball at a player's head 2 m in front of the hitter
  looks the same.

## Limits

- 112 typed contacts from one match and one camera, labelled by one person; per type most
  intervals span 0.3-0.7 (blocks: 3 contacts in all).
- 720p30 footage of another camera: at 4K50 the hitting arm stays in the box more often and the
  pose model resolves wrists, which may change the reach and the pose verdicts.
- Team is the median side of a track (`players.py`): a track whose identity crosses the net, or a
  contact typed on the wrong side (ball at the net), searches the wrong team.
- The track is not the player: `players.py` swaps identities in crowds, so per-player counts need
  the identity step (jersey numbers) on top of this.

## Next steps

- Detector recall at contact frames is the ceiling: rerun the detector at a lower threshold or on a
  zoomed crop around the ball when no candidate is near it, and let the tracker coast longer.
- Depth for crowds: the ball's apparent size or its 3D path (parabola + calibration) puts it at one
  player's depth.
- The pose veto, once the pipeline runs pose on contact frames anyway or on 4K footage.
- A learned scorer over box, pose and ball features once a few hundred contacts are labelled.
