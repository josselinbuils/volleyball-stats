"""Crop sheets to label attacks' jumps by eye: the attacker outlined in green, one tile per frame from 0.8 s before
the contact to 0.8 s after (two sheets, `_a` and `_b`), and every 5 frames over the 3 s before it (`_run`).

    uv run python benchmarks/jumps/sheets.py MATCH OUT_DIR [COUNT]
"""

import csv
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode, jumps

FPS = 50.0
TILE_H = 260


def region(rows: np.ndarray, frames: range) -> tuple[int, int, int, int]:
    near = rows[(rows[:, 0] >= frames[0]) & (rows[:, 0] <= frames[-1])]
    x1, y1, x2, y2 = near[:, 1].min(), near[:, 2].min(), near[:, 3].max(), near[:, 4].max()
    pad = 0.25 * (y2 - y1) / 2
    return int(max(0, x1 - pad)), int(max(0, y1 - pad)), int(x2 + pad), int(y2 + pad)


def sheet(video: Path, rows: np.ndarray, frames: range, per_row: int, out: Path) -> None:
    x1, y1, x2, y2 = region(rows, frames)
    boxes = jumps.at(rows, frames, 5)
    tiles = []
    for (index, image), box in zip(decode.frames_at(video, frames), boxes):
        crop = image[y1:y2, x1:x2].copy()
        if not np.isnan(box[0]):
            cv2.rectangle(crop, (int(box[0] - x1), int(box[1] - y1)), (int(box[2] - x1), int(box[3] - y1)), (0, 255, 0), 2)
        scale = TILE_H / crop.shape[0]
        crop = cv2.resize(crop, (round(crop.shape[1] * scale), TILE_H))
        cv2.putText(crop, str(index), (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(crop, str(index), (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        tiles.append(crop)
    blank = np.zeros_like(tiles[0])
    tiles += [blank] * (-len(tiles) % per_row)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[k : k + per_row]) for k in range(0, len(tiles), per_row)]), [cv2.IMWRITE_JPEG_QUALITY, 85])


def main(match: Path, out: Path, count: int = 20) -> None:
    video = Path(json.loads((match / "source.json").read_text())["video"])
    attacks = [(int(r["frame"]), int(float(r["track"]))) for r in csv.DictReader(open(match / "actions.csv")) if r["type"] == "attack" and r["track"]]
    picked = sorted(random.Random(0).sample(attacks, count))
    tracks = jumps.read_tracks(match / "players.csv", {t for _, t in picked})
    out.mkdir(parents=True, exist_ok=True)
    for f, t in picked:
        name = f"{match.name}_{f}_{t}"
        sheet(video, tracks[t], range(f - 40, f), 10, out / f"{name}_a.jpg")
        sheet(video, tracks[t], range(f, f + 40), 10, out / f"{name}_b.jpg")
        sheet(video, tracks[t], range(f - 150, f + 1, 5), 8, out / f"{name}_run.jpg")
        print(name)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), *(int(a) for a in sys.argv[3:]))
