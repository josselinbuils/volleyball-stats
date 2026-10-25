"""Time the trackers on the first seconds of a video and project them over a 2-hour match at the
video's frame rate: as the pipeline runs them (`match.tracked`: one ffmpeg decoding pass for the
ball and the players, on the GPU when ffmpeg can, frames scaled down to the models' 1280 px before
Python), and as they ran before (OpenCV frames at full size, one decoding pass per tracker).

    uv run python benchmarks/speed.py VIDEO [--seconds 60]

Results on the M4 Pro (MPS, ffmpeg decoding on the CPU), 2 min of side_holdout upscaled to 4K
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

The teams and identity steps each decode the video once more with OpenCV, at full size for their
crops: about the "decode, OpenCV" line each, plus identity's re-identification model.
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
    decoder = "NVDEC" if decode.cuda(args.video) else "CPU"
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
    old_players = timed(players.track_frames(ball.read_frames(args.video), calibration, players.load_model(), device))
    row("players, OpenCV frames", old_players)
    old = 1 / (1 / old_ball + 1 / old_players)
    row("**before**: ball, then players", old)
    new = timed(match.tracked(args.video, calibration, True, True))
    row("**now**: both in one ffmpeg pass", new, f" ({old / new:.0%} of before)")


if __name__ == "__main__":
    main()
