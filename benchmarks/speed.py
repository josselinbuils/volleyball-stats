"""Time the trackers on the first seconds of a video and project them over a 2-hour match at the
video's frame rate: as the pipeline runs them (`match.tracked`: one ffmpeg decoding pass for the
ball and the players, on the GPU when ffmpeg can, frames scaled down to the models' 1280 px before
Python), and as they ran before (OpenCV frames at full size, one decoding pass per tracker).

    uv run python benchmarks/speed.py VIDEO [--seconds 60]

Results on the M4 Pro (MPS, ffmpeg then decoding on the CPU), 2 min of side_holdout upscaled to 4K
50 fps HEVC at 100 Mb/s like the DJI Osmo Action 3's, 20 s timed, other work running (±10%):

| step | fps | 2-hour match |
| --- | --- | --- |
| decode, OpenCV, full size | 188 | 0.5 h |
| decode, ffmpeg on the CPU, 1280x720 | 185 | 0.5 h |
| ball, OpenCV frames | 30.4 | 3.3 h |
| players, OpenCV frames | 19.5 | 5.1 h |
| **before**: ball, then players | 11.9 | 8.4 h |
| **now**: both in one ffmpeg pass | 12.9 | 7.8 h (92% of before) |

The models set the pace on MPS: the pass saved is a decode the CPU runs beside them. On a 720p
video the outputs are byte for byte the old ones (same pixels, same frames).

On the RTX 5080 (WSL2, NVDEC), 60 s of the second ASPOM match's 4K 50 fps footage, 8 Nov, a short upload running at the start:

| step | fps | 2-hour match |
| --- | --- | --- |
| decode, OpenCV, full size | 61.1 | 1.6 h |
| decode, ffmpeg on the NVDEC, 1280x720 | 346.0 | 0.3 h |
| ball, OpenCV frames | 47.7 | 2.1 h |
| players, OpenCV frames | 43.6 | 2.3 h |
| **before**: ball, then players | 22.8 | 4.4 h |
| **now**: both in one ffmpeg pass | 26.0 | 3.9 h (88% of before) |

(The "now" row before `side_by_side`.) Twice the M4 Pro; the pass alone gives 28.6-31.3 fps. What holds it (8 Nov, 1500 frames under cProfile, GPU sampled every
0.2 s): one Python thread runs everything in turn at 100% of a core (of 16) while the card is busy 51% of the time. Of 48 s,
the players' YOLO11m one frame per call 23.5 s (its forward 18.5 s, the tracker ~3 s), the ball's model 11.9 s (9 s running
and waiting for its heatmaps, 3.6 s preparing frames), decoding 1.3 s. Measured ways out:

| | fps | outputs |
| --- | --- | --- |
| the pass as it is | 30.4 | |
| ball and players in two threads, the same frames | 37.9 | identical (600 of 600 frames) |
| `match.side_by_side`, as the pipeline now runs it | 36.7 (one thread 29.2) | identical (1500 of 1500 frames) |
| players' YOLO alone, a frame a call (FP32) | 61 | |
| batches of 8 frames | 92 | boxes within 1 px on 141 of 160 frames |
| one frame, half precision | 81 | within 1 px on 57 of 160 |
| batches of 8, half precision | 154 | within 1 px on 59 of 160 |

The real footage decodes slower than this copy; `decode.py` has its numbers. Tracking it, 60 s:
12.6 fps with ffmpeg on the CPU, 12.6 on VideoToolbox (same tracks); 10.0 and 10.4 with every core
kept busy.

The teams and identity steps each decode the video once more at full size for their crops, frames
counted by ffmpeg, on top of identity's re-identification model.

The steps after tracking on the RTX 5080, the first ASPOM match from its tracks, their caches removed,
8 Nov (`match.py` sampled every second; outputs identical, `report.md`'s times aside). Before: the
relance check one ffmpeg a frame, the wrists one a touch, and every frame between wanted ones
converted and piped to Python; after: `decode.frames_at` lets ffmpeg's select filter drop them.

| step | before | after | GPU busy | CPU cores (median) |
| --- | --- | --- | --- | --- |
| actions | 19.8 min | 3.5 min | 9% | 0.3 |
| wrists | 11.7 min | 3.5 min | 26% | 0.5 |
| teams | 26.5 min | 8.5 min | 15% | 2.0 |
| jerseys | 64.0 min | 46.5 min | 2% | 15.1 (RapidOCR on the CPU) |
| scoreboard | 9.7 min | 6.5 min | 0% | 12.6 (RapidOCR on the CPU) |
| identity | 37.1 min | 29.9 min | 8% | 1.3 |
| jumps | 5.9 min | 5.0 min | 26% | 1.7 |
| all | 2 h 56 | 1 h 44 | | |

RapidOCR then on the GPU (onnxruntime-gpu, 8 Nov, the two steps alone): jerseys 45.1 -> 23.5 min,
the same number on 301 of 303 pieces; scoreboard 6.6 -> 3.1 min, the same scores (22 of 22).
"""

import argparse
import time
from itertools import islice
from pathlib import Path

import cv2
import numpy as np
import torch

from volleyball_stats import ball, court, decode, match, players

MATCH_H = 2.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()

    cap = cv2.VideoCapture(str(args.video))
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    count = min(total, round(args.seconds * fps))
    device = ball.default_device()
    gpu = torch.cuda.get_device_name() if device == "cuda" else device
    decoder = {"cuda": "NVDEC", "videotoolbox": "VideoToolbox"}.get(next(iter(decode.hardware(args.video)[1:]), ""), "CPU")
    print(f"{args.video.name}: {width}x{height} at {fps:.2f} fps, {total / fps / 60:.1f} min; models on {gpu}, ffmpeg decodes on the {decoder}\n")
    print("| step | fps | 2-hour match |\n| --- | --- | --- |")

    def timed(frames) -> float:
        start = time.perf_counter()
        done = sum(1 for _ in islice(frames, count))
        return done / (time.perf_counter() - start)

    def row(name: str, rate: float, note: str = "") -> None:
        print(f"| {name} | {rate:.1f} | {MATCH_H * fps / rate:.1f} h{note} |", flush=True)

    # Any calibration keeps the timing honest: the court filter only drops rows.
    calibration = court.Calibration(np.diag([width / 20, height / 10, 1.0]) @ [[1, 0, 10], [0, 1, 5], [0, 0, 1]])
    row("decode, OpenCV, full size", timed(ball.read_frames(args.video)))
    row(f"decode, ffmpeg on the {decoder}, {'x'.join(map(str, decode.scaled(width, height)))}", timed(decode.frames(args.video)))
    old_ball = timed(ball.track_frames(ball.read_frames(args.video), ball.load_model(device), device))
    row("ball, OpenCV frames", old_ball)
    old_players = timed(players.track_frames(ball.read_frames(args.video), calibration, players.load_model(), device, fps=fps))
    row("players, OpenCV frames", old_players)
    old = 1 / (1 / old_ball + 1 / old_players)
    row("**before**: ball, then players", old)
    new = timed(match.tracked(args.video, calibration, True, True, fps))
    row("**now**: both in one ffmpeg pass", new, f" ({old / new:.0%} of before)")


if __name__ == "__main__":
    main()
