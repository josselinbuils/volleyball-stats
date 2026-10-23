# Ball tracking benchmark

Pretrained open-source ball trackers, scored on hand-labelled frames of four public matches: two
filmed from the sideline next to the net, like this project, and two from behind the baseline.

## Run

```bash
./benchmarks/ball/setup.sh   # weights and third-party model code, into .cache/bench
uv run --group bench python benchmarks/ball/bench.py run data/side_club.mp4
uv run --group bench python benchmarks/ball/bench.py compare \
  data/side_club.mp4:benchmarks/ball/ground_truth/side_club.csv \
  data/side_vnl.mp4:benchmarks/ball/ground_truth/side_vnl.csv
```

`bench.py` imports `candidates.py` from its own folder: run it with `PYTHONPATH=benchmarks/ball`.
`hits` scores only the labelled ball frames, so it does not depend on the "no ball" labels.

## Videos

| Clip | Source | Segment | Setup |
| --- | --- | --- | --- |
| `side_club.mp4` | [BIS vs CCAS Women's Volleyball](https://www.youtube.com/watch?v=bFLVvZ09YJo) | 1800–1980 s, 720p30 | wide-angle camera raised next to the net post, other courts in view |
| `side_vnl.mp4` | [France vs Türkiye, VNL 2025](https://www.youtube.com/watch?v=jTigaX7Xd5c) | 2700–2880 s, 720p25 | broadcast side camera; only its shots are labelled (3.6–11.6, 31.2–37.6, 55.2–75.4, 90.6–103.8, 167–176 s) |
| `backcourt.mp4` | [Turkey vs Netherlands, Paris 2024](https://www.youtube.com/watch?v=BVL7g25bP4c) | 600–780 s, 720p50 | broadcast back-court camera, high and centered |
| `club.mp4` | [Forza North 14ONE vs Madfrog 14](https://www.youtube.com/watch?v=rKahSdKGgv4) | 900–1020 s, 720p60 | phone on a low tripod behind the baseline, other courts in view |

```bash
uvx yt-dlp -f '136+140' --download-sections '*1800-1980' -o data/side_club.mp4 -- bFLVvZ09YJo
uvx yt-dlp -f '136+140' --download-sections '*2700-2880' -o data/side_vnl.mp4 -- jTigaX7Xd5c
uvx yt-dlp -f '298+140' --download-sections '*600-780' -o data/backcourt.mp4 -- BVL7g25bP4c
uvx yt-dlp -f 'bv*[height=720][ext=mp4]+ba[ext=m4a]' --download-sections '*900-1020' -o data/club.mp4 -- rKahSdKGgv4
```

## Ground truth

`ground_truth/*.csv`: `visible=1` with the ball center in pixels, or `visible=0`. Built by
reviewing zoomed crops around every candidate's proposals: a frame where no candidate proposed the
ball is labelled `visible=0`, so a ball no candidate saw is missing. A random audit of 24 such
frames per baseline clip found 0 (backcourt) and 2 (club) visible balls. Frames where the ball
position was uncertain are left out, and on the side-view clips so are frames where the ball is
not in play (held, on the floor, warm-up balls).

| Clip | Labelled frames | With the ball |
| --- | --- | --- |
| `side_club` | 119 | 71 |
| `side_vnl` | 117 | 63 |
| `backcourt` | 419 | 196 |
| `club` | 269 | 92 |

## Results

F1 at 10 px, one confidence threshold per candidate shared by the clips of a table, 95% bootstrap
interval. Speed on an M4 Pro (PyTorch on MPS, ONNX on CPU), the whole loop including video
decoding.

### Sideline, next to the net

| Candidate | Threshold | Mean F1 | side_club | side_vnl | fps |
| --- | --- | --- | --- | --- | --- |
| `wasb-step1` | 0.20 | **0.866** | **0.913** [0.86–0.96] | **0.819** [0.74–0.89] | 30 |
| `wasb` | 0.30 | 0.845 | 0.887 [0.83–0.94] | 0.803 [0.73–0.88] | 87 |
| `tracknetv2` | 0.05 | 0.803 | 0.862 [0.79–0.92] | 0.744 [0.65–0.83] | 54 |
| `vballnet-v1` | 0.85 | 0.617 | 0.900 [0.84–0.95] | 0.333 [0.21–0.45] | 83 |
| `vballnet-grid-v1b` | 0.50 | 0.589 | 0.775 [0.69–0.86] | 0.404 [0.28–0.53] | 185 |
| `vballnet-grid-v1c` | 0.55 | 0.512 | 0.741 [0.65–0.83] | 0.283 [0.18–0.39] | 270 |
| `vballnet-fast-v1` | 0.30 | 0.498 | 0.734 [0.64–0.82] | 0.262 [0.13–0.39] | 309 |
| `tracknetv3-beach` | 0.25 | 0.337 | 0.444 [0.32–0.56] | 0.230 [0.11–0.35] | 68 |
| `yolo11n` | 0.05 | 0.257 | 0.051 [0.00–0.12] | 0.463 [0.33–0.58] | 97 |
| `yolo11x` | 0.05 | 0.235 | 0.272 [0.16–0.39] | 0.197 [0.07–0.32] | 9 |

The three models trained on the side-view SFU volleyball dataset (`wasb`, `wasb-step1`,
`tracknetv2`) lead. A fallback to a second tracker when `wasb-step1` finds nothing does not help:
with thresholds tuned on one side-view clip and scored on the other, `wasb-step1` alone scores
0.803 and 0.906, and no fallback beats it by more than 0.02.

`wasb-step1` finds 63 of 71 and 61 of 63 labelled balls against 59 and 55 for `wasb`, but its F1
gain (+0.03 and +0.02; paired bootstrap 95% intervals −0.01 to +0.06 and −0.03 to +0.07) is
within noise at 3× the compute, so `ball.py` moves the window 3 frames at a time by default and
keeps the overlap behind `--stride 1`.

### Behind the baseline

| Candidate | Threshold | Mean F1 | backcourt | club | fps |
| --- | --- | --- | --- | --- | --- |
| `wasb-step1` | 0.25 | **0.668** | **0.731** [0.67–0.79] | 0.604 [0.50–0.69] | 30 |
| `wasb` | 0.15 | 0.624 | 0.689 [0.62–0.75] | 0.559 [0.46–0.65] | 87 |
| `vballnet-grid-v1b` | 0.55 | 0.578 | 0.556 [0.49–0.62] | 0.599 [0.51–0.68] | 185 |
| `tracknetv2` | 0.05 | 0.510 | 0.641 [0.58–0.71] | 0.379 [0.27–0.49] | 54 |
| `vballnet-fast-v1` | 0.35 | 0.498 | 0.294 [0.23–0.35] | **0.702** [0.61–0.78] | 309 |
| `vballnet-grid-v1c` | 0.55 | 0.497 | 0.517 [0.45–0.58] | 0.478 [0.39–0.56] | 270 |
| `yolo11x` | 0.05 | 0.467 | 0.252 [0.20–0.31] | 0.682 [0.60–0.76] | 8 |
| `tracknetv3-beach` | 0.30 | 0.433 | 0.294 [0.23–0.37] | 0.571 [0.47–0.68] | 68 |
| `vballnet-v1` | 0.85 | 0.430 | 0.630 [0.56–0.69] | 0.230 [0.13–0.33] | 83 |
| `yolo11n` | 0.10 | 0.425 | 0.484 [0.41–0.55] | 0.365 [0.25–0.47] | 97 |

YOLO11x is the only candidate finding balls at rest (on the floor, in a server's hands): the others
rely on motion.

## Candidates

| Name | Model | License |
| --- | --- | --- |
| `wasb`, `wasb-step1` | [WASB](https://github.com/nttcom/WASB-SBDT) HRNet, volleyball weights; `step1` slides its 3-frame window one frame at a time and pools the blobs | MIT |
| `tracknetv2` | TrackNetV2, volleyball weights from WASB | MIT |
| `tracknetv3-beach` | [TrackNetV3](https://github.com/qaz812345/TrackNetV3) fine-tuned on beach volleyball ([weights](https://huggingface.co/deadfast/beach-volley-vision-models)) | MIT |
| `vballnet-*` | [VballNet](https://github.com/asigatchov/vball-net-pytorch) heatmap (V1, FastV1) and grid (V1b, V1c) models | MIT |
| `yolo11n`, `yolo11x` | Ultralytics YOLO11, COCO "sports ball" class | AGPL-3.0 |
