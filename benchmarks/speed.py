"""Time the slow steps on the first seconds of a video and project them over the whole video.

    uv run python benchmarks/speed.py VIDEO [--seconds 60]
"""

import argparse
import time
from itertools import islice
from pathlib import Path

import cv2
import numpy as np
import torch

from volleyball_stats import ball, court, players


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
    print(f"{args.video.name}: {width}x{height} at {fps:.2f} fps, {total / fps / 60:.1f} min; device {gpu}")

    def timed(name: str, frames) -> None:
        start = time.perf_counter()
        done = sum(1 for _ in islice(frames, count))
        elapsed = time.perf_counter() - start
        print(f"{name:8} {done / elapsed:6.1f} fps -> {total / (done / elapsed) / 3600:.1f} h for the whole video")

    timed("decode", ball.read_frames(args.video))
    timed("ball", ball.track_frames(ball.read_frames(args.video), ball.load_model(device), device))
    # Any calibration keeps the timing honest: the court filter only drops rows.
    calibration = court.Calibration(np.diag([width / 20, height / 10, 1.0]) @ [[1, 0, 10], [0, 1, 5], [0, 0, 1]])
    timed("players", players.track_frames(ball.read_frames(args.video), calibration, players.load_model(), device))


if __name__ == "__main__":
    main()
