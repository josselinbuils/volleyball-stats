"""The play model on this machine: its prediction and a few training steps on a minute of a match, timed, on the device the
pipeline would use (an NVIDIA card, a Mac's GPU, else the processor) and, with --cpu, on the processor alone to compare.

    uv run python benchmarks/rallies/play_device.py data/matches/MATCH/MATCH.mp4 [--start 1560] [--seconds 60] [--steps 5] [--cpu]

Needs the weights (`outputs/learned/play/`, brought by the backup). Writes only to a temporary folder.
"""

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from volleyball_stats import decode, play_training, playing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=1560.0, help="Where the excerpt starts, in seconds")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--steps", type=int, default=5, help="Training steps to time (0: none)")
    parser.add_argument("--cpu", action="store_true", help="Also on the processor alone, software decoding and all")
    parser.add_argument("--weights", type=Path, default=Path("outputs") / playing.WEIGHTS)
    args = parser.parse_args()
    if playing.stamp(args.weights) is None:
        raise SystemExit(f"No weights in {args.weights}: open the app with its backup on, or train them (play_training).")
    on = playing.device()
    print(f"device: {on}; decoding: {' '.join(decode.hardware(args.video)) or 'software'}")
    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        excerpt = scratch / "excerpt.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(args.start), "-t", str(args.seconds), "-i", str(args.video), "-c", "copy", "-an", str(excerpt)], check=True)
        start = time.perf_counter()
        playing.predict(excerpt, scratch / "device.npz", args.weights)
        took = time.perf_counter() - start
        p = np.load(scratch / "device.npz")["p"]
        live = playing.live(p, playing.STRIDE / playing.FPS)
        print(f"prediction on {on}: {took:.0f} s for {args.seconds:.0f} s of video ({took / args.seconds:.2f} times its length), {len(p)} clips, play on {live.mean():.0%} of them")
        if args.cpu and on != "cpu":
            hardware = decode.hardware
            decode.hardware = lambda video: ()
            start = time.perf_counter()
            playing.predict(excerpt, scratch / "cpu.npz", args.weights, on="cpu")
            took = time.perf_counter() - start
            decode.hardware = hardware
            q = np.load(scratch / "cpu.npz")["p"]
            differ = int((live != playing.live(q, playing.STRIDE / playing.FPS)).sum())
            print(f"prediction on the processor alone: {took:.0f} s ({took / args.seconds:.2f} times the length); against {on}: mean |dP| {np.abs(p - q).mean():.4f}, play or not differs on {differ} of {len(p)} clips")
        if args.steps:
            # The excerpt's first half called play: the steps are only timed, their weights thrown away.
            play_training.spans = lambda match: [(0.0, args.seconds / 2, args.seconds / 2)]
            each = step_seconds(scratch, excerpt, on, args.steps)
            print(f"training on {on}: {each:.1f} s a step, about {play_training.STEPS * each / 3600:.1f} h for the pipeline's {play_training.STEPS} steps")


def step_seconds(scratch: Path, excerpt: Path, on: str, steps: int) -> float:
    """Seconds a training step takes on `on`, the model's loading left out (`train` tells the time since its first step)."""
    told: list[str] = []
    play_training.train([(scratch / "excerpt", excerpt)], scratch / "outputs", steps=steps, on=on, told=told.append)
    return float(told[-1].split()[-2]) / steps


if __name__ == "__main__":
    main()
