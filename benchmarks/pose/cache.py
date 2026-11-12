"""Cuts once the pixels every pose call of the pipeline sees, so each model gets the same ones: the crops around the
touches' balls (wrists.json), the crops around the labelled attackers (jumps.json), as raw arrays under
outputs/benchmarks/pose/MATCH/ (gitignored).

    python benchmarks/pose/cache.py MATCH [jumps-only]
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

from volleyball_stats import attribution, decode, jumps

ROOT = Path("outputs/benchmarks/pose")
LABELS = Path(__file__).parents[1] / "jumps" / "ground_truth"
FPS = 50.0


def labelled(match: str) -> list[tuple[int, int]]:
    """The labelled attacks of the jumps benchmark (both draws) of `match`."""
    out = []
    for name in ("labels.csv", "heldout.csv"):
        out += [(int(r["frame"]), int(r["track"])) for r in csv.DictReader(open(LABELS / name)) if r["match"] == match]
    return sorted(set(out))


def wrist_crop(image: np.ndarray, x: int, y: int) -> tuple[np.ndarray, int, int]:
    height, width = image.shape[:2]
    side = min(round(attribution.POSE_CROP * height), width, height)
    x0, y0 = min(max(0, x - side // 2), width - side), min(max(0, y - side // 2), height - side)
    return image[y0 : y0 + side, x0 : x0 + side], x0, y0


def main() -> None:
    match = sys.argv[1]
    folder = Path("outputs/matches") / match
    video = Path(json.loads((folder / "source.json").read_text())["video"])
    out = ROOT / match
    (out / "wrists").mkdir(parents=True, exist_ok=True)
    (out / "jumps").mkdir(exist_ok=True)
    keys = list(json.loads((folder / "wrists.json").read_text()))
    done = {"_".join(p.name.split("_")[:4]) for p in (out / "wrists").glob("*.npy")}
    wanted = {}
    for key in keys:
        frame, x, y = map(int, key.split(":"))
        for f in range(max(0, frame - 1), frame + 2):
            if f"{frame}_{x}_{y}_{f}" not in done:
                wanted.setdefault(f, []).append((key, x, y))
    for index, image in decode.frames_at(video, wanted if "jumps-only" not in sys.argv else []):
        for key, x, y in wanted[index]:
            crop, x0, y0 = wrist_crop(image, x, y)
            np.save(out / "wrists" / f"{key.replace(':', '_')}_{index}_{x0}_{y0}.npy", crop)
    print("wrists", len(keys), flush=True)
    attacks = labelled(match)
    rows = jumps.attack_rows(folder / "players.csv", attacks, FPS, folder / "jumps_rows.npz")
    hole = round(jumps.HOLE_S * FPS)
    boxes = {a: jumps.at(rows[a], jumps.window(a[0], FPS), hole)[:, :4] for a in attacks}
    wanted = {}
    for (f, t), b in boxes.items():
        for k, frame in enumerate(jumps.window(f, FPS)):
            if not np.isnan(b[k, 0]):
                wanted.setdefault(frame, []).append((f, t, k))
    for index, image in decode.frames_at(video, wanted):
        height, width = image.shape[:2]
        for f, t, k in wanted[index]:
            x1, y1, x2, y2 = boxes[(f, t)][k]
            side = min(round(jumps.CROP * (y2 - y1)), width, height)
            x0 = int(min(max(0, (x1 + x2) / 2 - side / 2), width - side))
            y0 = int(min(max(0, (y1 + y2) / 2 - side / 2), height - side))
            np.save(out / "jumps" / f"{f}_{t}_{k}_{x0}_{y0}.npy", image[y0 : y0 + side, x0 : x0 + side])
    print("jumps", len(attacks), flush=True)


if __name__ == "__main__":
    main()
