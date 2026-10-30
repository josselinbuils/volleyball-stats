"""Jersey numbers read on the players' boxes of 4K footage, for the identity step: per piece of
track, the torso of a few clear boxes is read by RapidOCR (PaddleOCR's models on onnxruntime), and
a number kept when READINGS_AGREE readings or more agree and none disagrees: a wrong number would
join two players for good. Written to jerseys.csv, which identity.run reads.

    uv run --group jerseys python -m volleyball_stats.jerseys outputs/VIDEO --video VIDEO
"""

import argparse
import csv
import time
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import identity
from volleyball_stats.attribution import read_players

FILE = "jerseys.csv"
# Boxes read per piece of track, pieces shorter than MIN_S skipped (a few frames of a crowd).
READS, MIN_S = 4, 2.0
# The number sits on the chest or the back: the box's rows between these shares of its height,
# upscaled SCALE times for the reader. Readings under CONFIDENCE, or not 1-2 digits, are dropped.
TORSO, SCALE, CONFIDENCE = (0.12, 0.62), 2, 0.9
READINGS_AGREE = 2


def torso(image: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    x1, y1, x2, y2 = box
    h = y2 - y1
    part = image[max(0, int(y1 + TORSO[0] * h)) : int(y1 + TORSO[1] * h), max(0, int(x1)) : int(x2)]
    return cv2.resize(part, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC) if part.size else part


def number(found: list | None) -> int | None:
    """The jersey number among a reader's findings: 1-2 digits read with CONFIDENCE or more."""
    digits = [text for _, text, score in found or [] if float(score) >= CONFIDENCE and text.isdigit() and len(text) <= 2]
    return int(digits[0]) if len(digits) == 1 else None


def agreed(readings: list[int]) -> int | None:
    """The number of a piece: read READINGS_AGREE times or more, and nothing else read."""
    return readings[0] if len(readings) >= READINGS_AGREE and len(set(readings)) == 1 else None


def read(match: Path, video: Path) -> list[tuple[int, int, int]]:
    """(frame, track, number) of the boxes read on pieces whose number is agreed."""
    from rapidocr_onnxruntime import RapidOCR

    reader = RapidOCR()
    rows = read_players(match / "players.csv")
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    cover = identity.covers(rows)
    boxes = {(r.frame, r.track): r.box for r in rows}
    wanted: dict[int, list[tuple[int, int]]] = {}
    for k, s in enumerate(identity.split(rows, cover)):
        if len(s.frames) >= MIN_S * fps:
            frames = identity.picks(s, cover)
            for i in np.linspace(0, len(frames) - 1, min(READS, len(frames))).astype(int):
                wanted.setdefault(frames[i], []).append((k, s.track))
    readings: dict[int, list[tuple[int, int, int]]] = {}
    for frame, image in identity.frames_at(video, wanted):
        for k, track in wanted[frame]:
            n = number(reader(torso(image, boxes[frame, track]))[0])
            if n is not None:
                readings.setdefault(k, []).append((frame, track, n))
    return [r for found in readings.values() if agreed([n for _, _, n in found]) is not None for r in found]


def write(path: Path, found: list[tuple[int, int, int]]) -> None:
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([["frame", "track", "number"], *sorted(found)])


def load(match: Path) -> dict[tuple[int, int], int] | None:
    """jerseys.csv's numbers by (frame, track), None without the file."""
    path = match / FILE
    if not path.exists():
        return None
    with open(path) as f:
        return {(int(r["frame"]), int(r["track"])): int(r["number"]) for r in csv.DictReader(f)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the jersey numbers of a match's player tracks (4K footage).")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO), run with --players")
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    found = read(args.match, args.video)
    write(args.match / FILE, found)
    print(f"{len({(t, n) for _, t, n in found})} track numbers from {len(found)} readings -> {args.match / FILE} ({(time.perf_counter() - start) / 60:.1f} min)")


if __name__ == "__main__":
    main()
