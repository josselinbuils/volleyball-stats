"""A ball.csv built from the pipeline's own track and a fine-tuned one, the second used only inside the rally windows.

    uv run python benchmarks/ball/finetune_hybrid.py OLD.csv NEW.csv RALLIES.csv OUT.csv --mode fill|in [--lead 1.0] [--tail 0.0] [--fps 50]

Window = from `lead` s before a rally's start to `tail` s after its end (rallies.csv of the run that found them).
fill: where OLD has no ball, NEW's position. in: where NEW has a ball, NEW's position (OLD's kept elsewhere).
Outside the windows OLD is untouched.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np


def read(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open()))
    seen = np.array([r["visible"] == "1" for r in rows])
    xy = np.array([[float(r["x"]), float(r["y"])] if r["x"] else [np.nan, np.nan] for r in rows])
    return seen, xy


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("old", "new", "rallies", "out"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--mode", choices=("fill", "in"), required=True)
    parser.add_argument("--lead", type=float, default=1.0)
    parser.add_argument("--tail", type=float, default=0.0)
    parser.add_argument("--fps", type=float, default=50.0)
    args = parser.parse_args()
    (so, xo), (sn, xn) = read(args.old), read(args.new)
    inside = np.zeros(len(so), bool)
    for r in csv.DictReader(args.rallies.open()):
        inside[max(0, int(r["start_frame"]) - round(args.lead * args.fps)) : int(r["end_frame"]) + round(args.tail * args.fps) + 1] = True
    take = inside & sn & (~so if args.mode == "fill" else True)
    seen, xy = np.where(take, sn, so), np.where(take[:, None], xn, xo)
    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "visible", "x", "y"])
        for i in range(len(seen)):
            w.writerow([i, int(seen[i]), *(int(v) for v in xy[i])] if seen[i] else [i, 0, "", ""])
    print(f"{args.out}: {int(take.sum())} frames from NEW, {int(inside.sum())} in windows, visible {int(seen.sum())} (OLD {int(so.sum())})")


if __name__ == "__main__":
    sys.exit(main())
