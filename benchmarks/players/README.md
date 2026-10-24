# Player detection and tracking benchmark

`volleyball_stats.players` detects the people of each frame with a pretrained YOLO11 (COCO
"person"), keeps those whose feet map near this court, tracks them with BoT-SORT and cleans the
tracks offline. This folder compares detectors and trackers on hand-labelled feet of two clips of
the same fixed camera, tuned on `side_club` and checked on `side_holdout`.

## Use

```bash
uv run --group bench python -m volleyball_stats.players data/match.mp4 outputs/court/match.json [--out DIR] [--overlay]
```

Writes `<video>_players.csv`: one row per frame and track with the box, its confidence, the feet
point (box bottom center) in pixels and in court meters (`court.py` frame: net at x = 0, near
sideline at y = 4.5), and the team as the side of the net (`left`/`right`). `--overlay` also writes
the video with the tracks drawn. From Python, `players.track(video, calibration)` returns the same
rows. Weights download to `models/yolo11m.pt` on first use.

`ultralytics` is only in the `bench` dependency group: it has to move to the main dependencies
before `match.py` can call this module. Its trackers import `lap`, which is not installed; until it
is, `players.make_tracker` stands in ultralytics' own assignment solver for it.

## Run

```bash
uv run --group bench python benchmarks/players/bench.py detect \
  data/side_club.mp4:benchmarks/players/ground_truth/side_club.csv \
  data/side_holdout.mp4:benchmarks/players/ground_truth/side_holdout.csv
uv run --group bench python benchmarks/players/bench.py track \
  data/side_club.mp4:benchmarks/players/ground_truth/side_club_sequence.csv \
  data/side_holdout.mp4:benchmarks/players/ground_truth/side_holdout_sequence.csv \
  [--model yolo11x --imgsz 1280 --conf 0.4] [--trackers bytetrack,botsort,botsort-reid] [--buffer 60]
```

`detect` picks each detector's confidence threshold on the first clip (best F1) and scores both
clips with it. `track` runs the module's pipeline over each labelled sequence (30 frames of warm-up
before the first label), online then after the offline pass. Both use the court calibration fitted
on `benchmarks/court/ground_truth/side_club.json` (least squares on the 7 line landmarks, no lens
model): the camera is the same in both clips.

## Ground truth

Same clips as the rally and contact benchmarks (720p, 29.97 fps, wide-angle camera next to the
near net post, other courts behind).

| File | What | Count |
| --- | --- | --- |
| `side_club.csv` | feet of every player on this court, 20 frames spread over the 7 rallies | 237 players (30 hidden, 2 on the floor) |
| `side_holdout.csv` | same, 20 frames over 17 rallies of the held-out clip | 235 players (20 hidden, 1 on the floor) |
| `side_club_sequence.csv` | identity of every player, every 10th frame of frames 2000-2300 (a 10 s rally) | 31 frames, 362 labels, 12 players |
| `side_holdout_sequence.csv` | same, frames 11250-11550 (blocked attack rally) | 31 frames, 348 labels, 12 players |

Frames: `frame,x,y,team,note`, the feet point (between the feet, on the floor; the lowest point for
a player down) read on 4-5× crops with a 5 px grid, `note` = `hidden` when the feet are hidden by
another player (placed from the visible body, ±5-10 px) or `down`. Referees, coaches, line judges,
substitutes, spectators and players of other courts are not labelled. Proposals came from YOLO11x
at 1280 and 1920 px with a 0.05 threshold; every player was checked on the crops and missing ones
were added by hand.

Sequences: `frame,player,x,y`, players `W1`-`W6` (white team, left) and `N1`-`N6` (navy, right),
liberos included (the navy libero wears white in `side_club`, black in `side_holdout`). Identities
were proposed by YOLO11x at 1920 px + ByteTrack, then checked on every labelled frame and corrected
by eye with jersey numbers, shoes and zoomed strips over the crossings; a player whose feet are
hidden in a frame is left out of that frame. Limit: a player the reference detector missed in a
frame was not added back, so recall on the sequences is optimistic (the detection frames above have
no such bias).

## Metrics

- A detection matches a labelled player when its feet point is within 20 px (greedy, closest
  first). Detection feet sit 5.3 px from the labels at the median, 11.5 px at the 90th percentile
  and 15.4 px at the 95th (YOLO11x, `side_club`); two labelled players are closer than 20 px in
  only 2.5% of cases (5th percentile 35 px), so 20 px accepts box jitter without pairing a
  detection with the neighbour. 20 px is 0.5 m across and 0.5-1 m in depth on the far side.
- `R visible`: recall on the players not marked hidden. `R far`: recall on the far half (y < 0).
- `false/frame`: kept detections matching no labelled player, per frame, after the detection court
  filter (feet within 3 m of the end lines and 2 m of the sidelines). Includes the truncated boxes of
  half-hidden players, whose bottom is the occluder's edge, not the feet.
- Feet error: distance in court meters between matched detection and label, both mapped with the
  same calibration (so it measures the box against the label, not the calibration).
- Tracking, on the labelled frames of each sequence: CLEAR-MOT ID switches (a labelled player's
  matched track changes from its previous match), track IDs per labelled player (fragmentation),
  IDF1 (players and tracks paired one to one by shared frames), team accuracy, and `other tracks`:
  tracks present in labelled frames that never match a labelled player (referees, coaches,
  spectators kept).
- Speed: whole loop (decoding, detection, tracking) on an M4 Pro, PyTorch on MPS.

## Results: detection

Confidence threshold chosen on `side_club` per detector and inference size.

Tuning, `side_club`:

| Detector | imgsz | conf | P | R | F1 | R visible | R far | false/frame | feet error, m (median / p90) | fps (720p) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yolo11n | 640 | 0.20 | 0.773 | 0.747 | 0.760 | 0.831 | 0.543 | 2.60 | 0.24 / 0.57 | 114 |
| yolo11n | 1280 | 0.35 | 0.891 | 0.865 | 0.878 | 0.952 | 0.713 | 1.25 | 0.20 / 0.52 | 95 |
| yolo11n | 1920 | 0.50 | 0.869 | 0.869 | 0.869 | 0.961 | 0.734 | 1.55 | 0.23 / 0.53 | 49 |
| yolo11s | 640 | 0.30 | 0.898 | 0.819 | 0.857 | 0.918 | 0.660 | 1.10 | 0.25 / 0.59 | 107 |
| yolo11s | 1280 | 0.45 | 0.868 | 0.890 | 0.879 | 0.981 | 0.755 | 1.60 | 0.24 / 0.56 | 51 |
| yolo11s | 1920 | 0.60 | 0.863 | 0.848 | 0.855 | 0.937 | 0.702 | 1.60 | 0.25 / 0.52 | 25 |
| yolo11m | 640 | 0.20 | 0.855 | 0.895 | 0.874 | 0.976 | 0.787 | 1.80 | 0.28 / 0.57 | 59 |
| **yolo11m** | **1280** | **0.50** | 0.864 | 0.886 | 0.875 | 0.971 | 0.766 | 1.65 | 0.26 / 0.51 | 23 |
| yolo11m | 1920 | 0.45 | 0.828 | 0.916 | 0.870 | 0.990 | 0.809 | 2.25 | 0.27 / 0.53 | 10 |
| yolo11x | 640 | 0.15 | 0.871 | 0.882 | 0.876 | 0.976 | 0.745 | 1.55 | 0.26 / 0.53 | 28 |
| yolo11x | 1280 | 0.40 | 0.868 | **0.941** | **0.903** | **1.000** | **0.862** | 1.70 | 0.24 / 0.50 | 9 |
| yolo11x | 1920 | 0.65 | 0.850 | 0.882 | 0.865 | 0.961 | 0.798 | 1.85 | 0.23 / 0.47 | 4 |

Held out, `side_holdout` (same thresholds):

| Detector | imgsz | P | R | F1 | R visible | R far | false/frame | feet error, m (median / p90) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yolo11n | 640 | 0.766 | 0.766 | 0.766 | 0.823 | 0.657 | 2.75 | 0.28 / 0.78 |
| yolo11n | 1280 | 0.815 | 0.804 | 0.809 | 0.860 | 0.685 | 2.15 | 0.20 / 0.47 |
| yolo11n | 1920 | 0.873 | 0.817 | 0.844 | 0.884 | 0.694 | 1.40 | 0.22 / 0.48 |
| yolo11s | 640 | 0.881 | 0.817 | 0.848 | 0.888 | 0.685 | 1.30 | 0.23 / 0.53 |
| yolo11s | 1280 | 0.892 | 0.843 | 0.867 | 0.902 | 0.769 | 1.20 | 0.23 / 0.50 |
| yolo11s | 1920 | 0.902 | 0.826 | 0.862 | 0.893 | 0.750 | 1.05 | 0.23 / 0.45 |
| yolo11m | 640 | 0.910 | 0.906 | 0.908 | 0.963 | 0.815 | 1.05 | 0.25 / 0.56 |
| **yolo11m** | **1280** | 0.928 | 0.872 | 0.899 | 0.940 | 0.750 | 0.80 | 0.24 / 0.46 |
| yolo11m | 1920 | 0.873 | 0.911 | 0.892 | 0.967 | 0.833 | 1.55 | 0.24 / 0.47 |
| yolo11x | 640 | 0.917 | 0.894 | 0.905 | 0.944 | 0.787 | 0.95 | 0.24 / 0.49 |
| yolo11x | 1280 | 0.914 | **0.949** | **0.931** | **0.991** | **0.898** | 1.05 | 0.22 / 0.47 |
| yolo11x | 1920 | 0.900 | 0.881 | 0.890 | 0.935 | 0.815 | 1.15 | 0.22 / 0.40 |

- Visible players are found: 0.94-1.00 recall for m and x at 1280. What is missed is occlusion: on
  `side_club` all 14 players YOLO11x at 1280 misses are marked hidden, behind a nearer player in the
  same image column, mostly on the far side (`R far` 0.75-0.90 against 0.94-1.00 overall visible).
- A larger inference size does not help on these clips: 1920 px upsamples a 720p frame without
  adding detail and scores below 1280 for s, m and x on both clips (n gains on the held-out clip
  only). Tiling was skipped for the same reason; it
  needs real 4K footage, where far players are 3× taller in pixels than here.
- No labelled player was dropped by the court filter (`dropped` = 0 for every row of `bench.py`).
- The feet error is ~0.25 m at the median and ~0.5 m at the 90th percentile for every detector:
  boxes end at the lowest shoe, 4 px below the labelled point between the feet on average.

## Results: tracking

Each detector at its threshold above; `online` is the tracker alone, `offline` adds the module's
offline pass (stitching, short and off-court tracks dropped, team). Offline unless said otherwise.

| Detector | Tracker | `side_club`: ID switches / IDs per player / IDF1 / recall | `side_holdout` (held out) | fps (720p) |
| --- | --- | --- | --- | --- |
| yolo11n 1280 | ByteTrack | 10 / 1.58 / 0.787 / 0.878 | 20 / 2.17 / 0.731 / 0.928 | 80 |
| yolo11n 1280 | BoT-SORT | 11 / 1.75 / 0.750 / 0.884 | 19 / 2.33 / 0.718 / 0.917 | 87 |
| yolo11s 1280 | ByteTrack | 4 / 1.33 / 0.845 / 0.898 | 9 / 1.67 / 0.818 / 0.945 | 45 |
| yolo11s 1280 | BoT-SORT | 5 / 1.42 / 0.826 / 0.912 | 7 / 1.50 / 0.872 / 0.954 | 48 |
| yolo11s 1280 | BoT-SORT + ReID | 3 / 1.25 / 0.869 / 0.909 | 7 / 1.50 / 0.877 / 0.957 | 16 |
| yolo11m 640 | ByteTrack | 10 / 1.50 / 0.827 / 0.848 | 11 / 1.75 / 0.771 / 0.908 | 53 |
| yolo11m 640 | BoT-SORT | 7 / 1.42 / 0.837 / 0.854 | 9 / 1.75 / 0.755 / 0.920 | 57 |
| yolo11m 1280 | ByteTrack | 9 / 1.75 / 0.788 / 0.953 | 8 / 1.58 / 0.918 / 0.983 | 21 |
| **yolo11m 1280** | **BoT-SORT** | **5 / 1.33 / 0.902** / 0.961 | **5 / 1.42 / 0.905** / 0.977 | 22 |
| yolo11m 1280 | BoT-SORT + ReID | 5 / 1.33 / 0.902 / 0.961 | 6 / 1.50 / 0.894 / 0.977 | 11 |
| yolo11x 1280 | ByteTrack | 7 / 1.58 / 0.868 / 0.972 | 8 / 1.67 / 0.856 / 0.989 | 9 |
| yolo11x 1280 | BoT-SORT | 4 / 1.33 / 0.879 / 0.972 | 7 / 1.58 / 0.866 / 0.989 | 9 |

The chosen pipeline, online then offline:

| `yolo11m` 1280 + BoT-SORT | ID switches | IDs per player | IDF1 | precision | other tracks | team |
| --- | --- | --- | --- | --- | --- | --- |
| `side_club` online | 9 | 1.75 | 0.732 | 0.765 | 7-8 (runs differ on MPS) | |
| `side_club` offline | 5 | 1.33 | 0.902 | 0.983 | 0 | 1.000 |
| `side_holdout` online | 7 | 1.58 | 0.839 | 0.897 | 1 | |
| `side_holdout` offline | 5 | 1.42 | 0.905 | 0.977 | 0 | 1.000 |

- BoT-SORT, run without its appearance model and without camera motion compensation (fixed camera),
  has as few or fewer ID switches than ByteTrack in 8 of 10 detector × clip pairs, at the same
  speed; IDF1 is split 5 to 5. Its appearance
  model (`yolo11n-cls` embeddings) halves the speed and changes 0-2 switches either way: generic
  crops do not tell same-team players apart.
- The offline pass removes 2-10 switches per sequence and every non-player track: the coach standing
  1 m off the near sideline, a referee by the near post (feet out of frame), people behind the right end line
  and in the far left corner. Raising the tracker's buffer from 1 s to 2 or 3 s changes nothing for
  BoT-SORT (5 / 5 switches) once the offline pass runs.
- What remains are true swaps or new IDs where two players overlap in the image, nearly all at
  the net: two navy front-row players crossing behind each other (`side_holdout` N1/N3 at frame
  11330), a libero getting up from a dive behind a teammate (`side_club` N4, frame 2170), a blocker
  among the net crowd (N2, frames 2120-2190), two white back-row players overlapping in depth (W1/W2,
  frame 2100). Motion cannot separate them; identity needs appearance (jersey number), the job of
  the identity step.
- Team as the side of the net is right for every matched label of both sequences.
- These are small counts (4-11 switches on 360 labels): differences of 1-2 are noise.

Choice: **YOLO11m at 1280 px + BoT-SORT + offline pass**. Best IDF1 and fewest switches on the
tuning clip and on the held-out one; YOLO11x finds 5-8 more players in 100 on single frames but
tracks no better at 2.4× the time. YOLO11s at 1280 is the fallback at twice the speed (IDF1
0.83 / 0.87).

## Speed on 4K

A 10 s cut of `side_club` upscaled to 3840×2160 at 50 fps (HEVC, like the Osmo Action 3), first
300 frames, whole loop on the M4 Pro:

| Pipeline | fps | 2-hour match at 50 fps |
| --- | --- | --- |
| decoding only | 141 | 0.7 h |
| yolo11n 1280 | 69 | 1.5 h |
| yolo11s 1280 | 36 | 2.8 h |
| **yolo11m 1280** | **21** | **4.8 h** |
| yolo11x 1280 | 9 | 11.5 h |

The detector's input is 1280 px wide whatever the source, so the cost per frame barely depends on
4K. The match pipeline runs on the RTX 5080, not measured here.

## Limits

- Occlusions: a player hidden behind a nearer one is missed (0.75-0.90 recall on the far half), and
  a half-hidden one gets a box that ends at the occluder, its "feet" too high in the image, so 0.5-2
  m too far from the camera (the residual `false/frame` is mostly these). The tracker coasts over
  short gaps; the offline pass joins longer ones only when the motion is plausible.
- Jumps and dives move the feet point: a foot h above the floor maps h / (H − h) farther along the
  floor ray from the camera (H = camera height), so a 0.5 m block jump seen from 3.6 m lands about
  16% too far, ~1.5 m at 10 m. Contacts happen mid-jump: positions at contact frames need the feet
  of the last ground frame. A player on the floor is placed by the lowest point of the body.
- The lens is not corrected: on this camera the plain homography is 0.3-1.4 m off (court
  benchmark), more toward the frame edges, so court positions and the margins below carry that
  error. The feet error above compares boxes to labels in the same calibration and does not include
  it. Fitting the court with the Osmo's lens JSON (`lens.py`) fixes most of it.
- Court filter: detections need their feet within 3 m of the end lines and 2 m of the sidelines,
  tracks their median feet within 1 m and 0.5 m. A player who runs out for a ball keeps a track; a
  substitute warming up at the end line, or a coach standing on the line, would be kept (none in
  these clips). Measure the gym's free zone and the bench position on the first match.
- Team is the side of the net, true within a set; sides swap between sets and the identity step has
  to link them. Jersey colour clustering was not used: each libero wears another colour than the
  team (white for navy, black for white), so a colour team would be wrong exactly for them.
- The test clips are 720p30 YouTube footage of another camera, not the Osmo at 4K50: far players
  are 60-90 px tall here. The thresholds and the inference size need checking on the first match.
- The offline pass holds the whole match in memory and compares all track pairs (see the
  `ponytail` notes in `players.py`).

## Next steps

- The first match at 4K50 with the lens JSON: label one sequence, rerun `track`, and try 1280 px
  against tiles of the 4K frame for the far side.
- Feet during jumps: hold the last ground position while the box bottom rises (or use pose ankles).
- Identity across occlusions and sets: jersey number OCR and re-ID over the tracks (pipeline
  step 6); pose (wrists) for contact attribution.
- Processing every second frame of 50 fps footage halves the cost; check the switches at 25 fps on
  real 50 fps footage first (these clips are 30 fps).
