# Ball tracking benchmark

Pretrained open-source ball trackers, scored on hand-labelled frames of two public matches filmed
from behind the baseline. The project films from the sideline, so side-view clips are still to be
added.

## Run

```bash
./benchmarks/ball/setup.sh   # weights and third-party model code, into .cache/bench
uv run --group bench python benchmarks/ball/bench.py run data/backcourt.mp4
uv run --group bench python benchmarks/ball/bench.py compare \
  data/backcourt.mp4:benchmarks/ball/ground_truth/backcourt.csv \
  data/club.mp4:benchmarks/ball/ground_truth/club.csv
```

`bench.py` imports `candidates.py` from its own folder: run it with `PYTHONPATH=benchmarks/ball`.

## Videos

| Clip | Source | Segment | Setup |
| --- | --- | --- | --- |
| `backcourt.mp4` | [Turkey vs Netherlands, Paris 2024](https://www.youtube.com/watch?v=BVL7g25bP4c) | 600–780 s, 720p50 | broadcast back-court camera, high and centered |
| `club.mp4` | [Forza North 14ONE vs Madfrog 14](https://www.youtube.com/watch?v=rKahSdKGgv4) | 900–1020 s, 720p60 | phone on a low tripod behind the baseline, other courts in view |

```bash
uvx yt-dlp -f '298+140' --download-sections '*600-780' -o data/backcourt.mp4 'https://www.youtube.com/watch?v=BVL7g25bP4c'
uvx yt-dlp -f 'bv*[height=720][ext=mp4]+ba[ext=m4a]' --download-sections '*900-1020' -o data/club.mp4 'https://www.youtube.com/watch?v=rKahSdKGgv4'
```

## Ground truth

`ground_truth/*.csv`: one frame every 20 (backcourt) or 24 (club) frames, `visible=1` with the ball
center in pixels, or `visible=0`. Built by reviewing zoomed crops around every candidate's
proposals: a frame where no candidate proposed the ball is labelled `visible=0`. A random audit of
24 such frames per clip found 0 (backcourt) and 2 (club, both balls held by players between
rallies) visible balls. Frames where the ball position was uncertain are left out.

## Results

F1 at 10 px, one confidence threshold per candidate shared by both clips, 95% bootstrap interval.
Speed on an M4 Pro (PyTorch on MPS, ONNX on CPU).

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

Only `wasb-step1` is near the top on both clips. YOLO11x is the only candidate finding balls at
rest (on the floor, in a server's hands): the others rely on motion.

Combining two trackers (the first one's pick, else the second's), thresholds tuned on one clip and
scored on the other:

| Combination | Tuned on backcourt → club | Tuned on club → backcourt |
| --- | --- | --- |
| `wasb-step1` alone | 0.589 | 0.714 |
| `wasb-step1`, else `tracknetv3-beach` | 0.699 | 0.728 |
| `wasb-step1`, else `vballnet-fast-v1` | 0.662 | 0.554 |

## Candidates

| Name | Model | License |
| --- | --- | --- |
| `wasb`, `wasb-step1` | [WASB](https://github.com/nttcom/WASB-SBDT) HRNet, volleyball weights; `step1` slides its 3-frame window one frame at a time and pools the blobs | MIT |
| `tracknetv2` | TrackNetV2, volleyball weights from WASB | MIT |
| `tracknetv3-beach` | [TrackNetV3](https://github.com/qaz812345/TrackNetV3) fine-tuned on beach volleyball ([weights](https://huggingface.co/deadfast/beach-volley-vision-models)) | MIT |
| `vballnet-*` | [VballNet](https://github.com/asigatchov/vball-net-pytorch) heatmap (V1, FastV1) and grid (V1b, V1c) models | MIT |
| `yolo11n`, `yolo11x` | Ultralytics YOLO11, COCO "sports ball" class | AGPL-3.0 |
