# Court calibration benchmark

The manual calibration of `volleyball_stats.court` (named landmarks read on a gridded frame, one
homography over the floor) scored on hand-located landmarks of two clips, plus an automatic line
detection attempt that is not reliable and stays out of the product.

## Run

```bash
uv run --group bench python benchmarks/court/bench.py manual \
  data/side_club.mp4:benchmarks/court/ground_truth/side_club.json \
  data/side_vnl.mp4:benchmarks/court/ground_truth/side_vnl.json
uv run --group bench python benchmarks/court/bench.py auto \
  data/side_club.mp4:benchmarks/court/ground_truth/side_club.json \
  data/side_vnl.mp4:benchmarks/court/ground_truth/side_vnl.json [--debug outputs/court]
```

## Ground truth

`ground_truth/<clip>.json`: the frame index, the image position of every visible landmark of
`court.LANDMARKS` and, where it is worse than 2 px, the reading tolerance.

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
the brightness profiles.

Limits: on `side_club` the far sideline is only visible on x ∈ [440, 590] (window glare on the
floor), so `corner_left_far` and `attack_right_far` extrapolate it (tolerance 4 px) and
`corner_right_far` uses the mirrored height of the left side (6 px); the post bases are the bottom
of the paddings (5 px) and the post distance to the sideline is unknown, so the posts stay out of
the fits and are only predicted.

## Results: manual calibration

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
| attack_left_near | 8.2 | 0.15 | | center_near | 3 | 29.9 | 0.32 |
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

## Results: automatic line detection

`bench.py auto`: top-hat threshold → `HoughLinesP` segments merged into lines, the two longest
near-horizontal lines with floor color between them taken as the sidelines, the lines crossing
them assigned to the court's five transverse lines by the homography that fits them best.

| Threshold | `side_club` | `side_vnl` |
| --- | --- | --- |
| 40 | wrong sidelines (bowed lines, glare): median 12 m | no sideline pair found (far sideline too faint: gray 216 on 190) |
| 15 (kept) | wrong sidelines: median 12.6 m | far sideline exact (3 landmarks within 0.7 px), near sideline taken as the blue apron edge 44 px lower: RMS 30.6 px, median 1.08 m |

Not reliable: the sidelines are never simply the two strongest white lines (sponsor boards, apron
edges, an extra white line 2 m inside the club court, glare, and the fisheye curvature all win),
and every fix tried is specific to one clip. The manual calibration is the product: one frame, a
dozen points read once per camera setup. Prior art for later: a keypoint net on a Roboflow
volleyball court dataset (CC BY 4.0, ~860 images) with RANSAC, which the literature puts at 0.1 m
on broadcast frames but 0.5 m on gym images; the click-based 4-corner tool of
[beach-volley-vision](https://github.com/ddecks/beach-volley-vision) (MIT) needs a display,
hence the gridded frame and JSON here.
