# Court calibration benchmark

`volleyball_stats.court` maps image pixels to court meters with one homography over the floor
(after lens undistortion when a lens JSON exists). A court is calibrated once: the user clicks
rough landmark positions, they are snapped to the painted lines of the video's median frame, and
the result is stored by court name. Later videos of the same court are calibrated by `auto`, which
finds a stored court on its own and refuses other courts. This folder scores each step on
hand-located landmarks of two clips.

## Use

```bash
uv run python -m volleyball_stats.court click data/match.mp4            # window: click the landmarks it names
uv run python -m volleyball_stats.court fit outputs/court/match_clicks.json data/match.mp4 --court gym
uv run python -m volleyball_stats.court auto data/next_match.mp4        # tries every outputs/courts/*.json
```

`click` shows the median frame (players removed) with a court sketch marking the landmark to click;
`s` skips a hidden one, `u` undoes, Enter saves. `fit` prints, per landmark, how far it snapped or
that it kept the click, and stores the court in `outputs/courts/<name>.json` (`--out` for another
path) with the clicks, the snapped landmarks, the lines' colour and line samples for `auto`.
`grid` still writes a frame with a pixel grid for reading coordinates without a display.

## Run

```bash
uv run --group bench python benchmarks/court/bench.py manual \
  data/side_club.mp4:benchmarks/court/ground_truth/side_club.json \
  data/side_vnl.mp4:benchmarks/court/ground_truth/side_vnl.json
uv run --group bench python benchmarks/court/bench.py refine \
  data/side_club.mp4:benchmarks/court/ground_truth/side_club.json \
  data/side_vnl.mp4:benchmarks/court/ground_truth/side_vnl.json [--seeds 20]
uv run --group bench python benchmarks/court/bench.py auto
```

## Ground truth

`ground_truth/<clip>.json`: the frame index, the image position of every visible landmark of
`court.LANDMARKS`, where it is worse than 2 px the reading tolerance, and `background` when the
camera is fixed (the benchmarks then use the median frame).

| Clip | Frame | Landmarks | Missing |
| --- | --- | --- | --- |
| `side_club` | 1500 (fixed camera) | 7 line landmarks + 2 post bases | near corners (off frame), `center_far` (behind the near post) |
| `side_vnl` | 785 (t = 31.4 s, main camera) | 8 line landmarks | `center_*` and the posts (behind the post and the referee) |

Method: each court line is traced on 8-12× grid crops, then refined: a 9×9 top-hat filter gives
the line's brightness over its surroundings, its centroid is taken every row or column within
±6-9 px of the hand-drawn line, a polynomial is fitted (residual RMS 0.15-0.5 px) and the
landmarks are the intersections. Landmarks sit on the line centers (lines are 5 cm wide). The club
clip is traced on the median of 60 frames, which removes the players (the camera is fixed), like
[DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) does for
fixed cameras; visual reads at 8-12× agreed with the traces within 2-3 px, and the traces match
the brightness profiles. `side_long` and `side_holdout` are the same match and camera: their median
frames are shifted by under 0.05 px from `side_club`'s (phase correlation), so its ground truth
scores them too.

Limits: on `side_club` the far sideline is only visible on x ∈ [440, 590] (window glare on the
floor), so `corner_left_far` and `attack_right_far` extrapolate it (tolerance 4 px) and
`corner_right_far` uses the mirrored height of the left side (6 px); `center_near` is where the
near post's padding edge meets the sideline, the center line itself being hidden behind the post
(5 px); the post bases are the bottom of the paddings (5 px) and the post distance to the sideline
is unknown, so the posts stay out of the fits and are only predicted. The snapping below uses the
same top-hat idea as the ground truth, so its sub-pixel agreement with it is partly by
construction: the ground truth is good to the 1-2 px of the visual check, not better.

## Results: homography from exact landmarks

Leave-one-out: each landmark is predicted by the homography fitted on the other line landmarks;
error in pixels (reprojected − labelled) and in meters (back-projected − model).

| Clip | Fit on all, RMS px | LOO RMS px | LOO median m | LOO max m |
| --- | --- | --- | --- | --- |
| `side_vnl` (broadcast, 720p) | 5.8 | 8.6 | 0.15 | 0.27 |
| `side_club` (wide-angle, 720p) | 15.1 | 51.4 | 0.55 | 1.38 |

| `side_vnl` landmark | px | m | | `side_club` landmark | tol px | px | m |
| --- | --- | --- | --- | --- | --- | --- | --- |
| corner_left_far | 4.4 | 0.11 | | corner_left_far | 4 | 56.7 | 1.38 |
| attack_left_far | 4.2 | 0.09 | | attack_left_far | 2 | 16.8 | 0.51 |
| attack_right_far | 3.7 | 0.07 | | attack_right_far | 4 | 19.5 | 0.46 |
| corner_right_far | 2.9 | 0.06 | | corner_right_far | 6 | 56.7 | 1.16 |
| corner_left_near | 12.3 | 0.27 | | attack_left_near | 2 | 96.4 | 0.64 |
| attack_left_near | 8.2 | 0.15 | | center_near | 5 | 29.9 | 0.32 |
| attack_right_near | 9.0 | 0.17 | | attack_right_near | 2 | 34.8 | 0.55 |
| corner_right_near | 15.0 | 0.27 | | post_near (predicted) | 5 | 40.3 | 0.51 |
| | | | | post_far (predicted) | 5 | 9.2 | 0.32 |

- `side_vnl`: a plain homography maps the broadcast frame to ~0.15 m. The residuals of the fit on
  all 8 points are symmetric (attack ends 4 px inside the model on the near side, 2.5 px on the
  far side, corners the other way), i.e. mild lens distortion of the zoom lens rather than reading
  noise (traces are good to ~1 px).
- `side_club`: the wide-angle lens bows the near sideline by 55 px (y = 531 at the center, 476-489
  at the frame edges), so a homography alone is 0.3-1.4 m off. This is the project's camera setup:
  lens undistortion is mandatory before the homography, which is why `court.fit` takes a lens
  JSON. The clip's intrinsics are unknown and were not estimated; the DJI Osmo Action 3 must be
  calibrated once with a checkerboard (`cv2.fisheye`, settings locked). Fitting a one-parameter
  division model from the lines' straightness is the fallback if a checkerboard is not possible.

## Results: snapping rough clicks

`bench.py refine`: 20 seeds of simulated clicks, each landmark moved 10-20 px in a random direction
from the ground truth, on the median frame of `side_club` and on frame 785 of `side_vnl` (the
broadcast camera moves, so no median frame there). "Court" is the error in meters at the
ground-truth landmarks of the homography fitted on the clicks (least squares) or on the refined
points; these landmarks are the fitted ones, so it is an in-sample figure, unlike the
leave-one-out above.

| | `side_club` | `side_vnl` |
| --- | --- | --- |
| Landmarks snapped | 60/120 (3 of 6 snappable, every seed) | 149/160 (93%) |
| Error once snapped, px: median / max | 0.85 / 1.1 | 0.33 / 3.9 |
| Points, px: clicks → refined, median | 15.0 → 10.8 (clicks kept where not snapped) | 15.4 → 0.36 |
| Court, m: clicks → refined, median | 0.34 → 0.30 | 0.31 → 0.06 |
| Court, m: clicks → refined, max | 2.1 → 2.0 | 0.8 → 0.5 |

- No snap lands on a wrong line: the worst is 3.9 px (`side_vnl` `attack_left_near`, where a
  player stands on the line in this single frame). A landmark that cannot be snapped safely keeps
  its click.
- On `side_vnl` snapping turns 15 px clicks into a 0.06 m court (0.31 m from the clicks alone).
- On `side_club` only 3 landmarks snap: the far corners and `attack_right_far` sit in window glare
  where the far sideline is invisible or flanked by brighter lines within click range (a wall-base
  line 34 px above, a light line 18 px below), and the center line is behind the post. With the
  fisheye uncorrected the court error stays at 0.3 m whatever the points.
- RANSAC (10 px) on rough clicks picks degenerate subsets: up to 1,605 m off on `side_club` and
  229 m on `side_vnl`. Rough clicks are fitted by least squares, snapped landmarks alone (RANSAC)
  once at least 4 snap.

How it snaps: the clicks' least-squares homography projects the two court lines through each
landmark, shifted onto its click, out to the neighbouring landmarks but at most 150 px. Each line is
traced across ±30 px, fitted by RANSAC to a straight line within 10° of the projection, then
traced again across ±8 px of that fit; the landmark is the intersection. The tracing reads each
pixel's colour minus its 15 px median (thin lines of any colour stand out, the floor and wide glare
cancel), projected on the lines' colour, which is learnt from the clicks: the strongest pixels
near the projected lines are grouped by colour (k-means, 3 groups) and the group whose pixels form
the most straight lines along the court wins. This picks the white lines over the floor's dark
basketball and green lines, which outnumber them near the club's clicks. A window with a second
parallel line holding half the first one's samples is ambiguous and keeps the click; snapping
`center_*` and the posts is off (see the `UNSNAPPED` note). Pixel values are for 720p and scale
with the frame height; `tests/test_court.py` checks the snapping on blue lines over a yellow floor
with red decoy lines next to the sidelines.

## Results: finding a stored court

`bench.py auto`: each ground-truth clip is stored as a court (ground truth as clicks), then matched
on other frames. Same-camera rows are scored against the ground truth; the moved rows warp the
`side_long` median frame and its ground truth with a similarity. "Found" is the share of the
court's line samples on a line of the frame (±2 px) at the best roll and shift.

| Court → frame | Found | Snapped again | Verdict | Landmarks, px max | Court, m median |
| --- | --- | --- | --- | --- | --- |
| side_club → side_club, side_long, side_holdout | 1.00 | 3/3 | match | 0.9 | 0.20-0.21 |
| side_club → side_long moved 40, 20 px | 1.00 | 3/3 | match | 0.9 | 0.20 |
| side_club → side_long moved 90 px | 1.00 | 3/3 | match | 0.9 | 0.21 |
| side_club → side_long rolled 2° / 4° | 1.00 / 0.81 | 3/3 | match | 0.9 | 0.20 |
| side_club → side_long zoomed ×1.06 | 0.76 | 3/3 | match | 0.8 | 0.18 |
| side_club → side_long moved 60, −30 px, 2.5°, ×1.05 | 0.78 | 3/3 | match | 0.8 | 0.20 |
| side_club → side_long moved 120 px / rolled 6° / ×1.1 | 0.77-0.84 | 0/3 | no | | |
| side_club → side_vnl (3 frames), backcourt, club | 0.42-0.83 | 0/3 | no | | |
| side_vnl → side_vnl 785 | 1.00 | 7/7 | match | 0.6 | 0.06 |
| side_vnl → side_vnl 1500, 2500, 4300 (re-framed, ×1.4 zoom) | 0.50-0.54 | 1-2/7 | no | | |
| side_vnl → side_club, backcourt, club | 0.67-0.73 | 0/7 | no | | |

- Same court, same or nudged camera (up to ±90 px, 4° of roll, 6% zoom): found every time, the
  landmarks within 0.9 px of where they moved; the landmarks that never snap follow the similarity
  fitted on those that do. Larger moves, and the broadcast operator's re-framing of `side_vnl`,
  are refused: they need new clicks.
- Every other court is refused. What decides is the share of stored landmarks that snap again
  (needed 75%; matches 100%, refusals at most 2/7). The line-sample share alone does not separate
  courts (busy floors with many lines reach 0.83, a zoomed match 0.76), so it is only a floor
  (`MATCH_FOUND` 0.6). The fit residual is not used: without a lens model the club's is 9-14 px
  for the right court, so it says little.
- A court where few landmarks snap is matched on few points: `side_club` rests on 3, so 3 chance
  snaps on another court would pass. Calibrating with the lens JSON and in light without glare
  should snap more.
- 0.7 s per stored court at 720p, plus 2 s for the median frame of a 10-minute video.

How it matches: the court's line samples (the snapped lines' pixels, 1,000 kept) are turned by
−3° to 3° and slid by ±90 px over the frame's line pixels (in the court's colour); at the best fit
the stored landmarks are moved alike and snapped (±30 px), the ones that do not snap follow the
similarity fitted on those that do, and the court is fitted again.

## Earlier attempt: line detection without clicks

Commit bb61b49 tried to find the court from nothing: top-hat threshold, `HoughLinesP` segments
merged into lines, the two longest near-horizontal lines with floor colour between them taken as
the sidelines, the crossing lines assigned to the court's five transverse lines by the best
homography. It picked wrong sidelines on `side_club` (median 12 m) and the apron edge instead of
the near sideline on `side_vnl` (median 1.08 m): sponsor boards, apron edges, other sports' lines,
glare and the fisheye curvature all beat the two strongest white lines. Removed.

## Next steps

- A standard-placement starting guess for a new court: with the camera at the documented spot
  (sideline, aligned with the net, 3.6 m high, a few meters back) and the lens JSON, the court's
  expected image position is known well enough to seed the snapping without clicks, or with one
  or two.
- The lens JSON of the Osmo Action 3 (checkerboard), then this benchmark on a match filmed with it.
- Prior art if clicks must go: a keypoint net on a Roboflow volleyball court dataset (CC BY 4.0,
  ~860 images) with RANSAC, which the literature puts at 0.1 m on broadcast frames but 0.5 m on gym
  images. The click-based 4-corner tool of
  [beach-volley-vision](https://github.com/ddecks/beach-volley-vision) (MIT) inspired `click`; no
  code reused.
