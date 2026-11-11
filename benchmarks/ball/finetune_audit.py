"""Contact sheets of 4K crops around pseudo-labels, to check them by eye.

Each tile is a 128x128 crop at 2x, the label at its centre, four ticks around it (not over it).
Samples: `only1024` (ball labels the 512 pick lacked), `both`, `unsure` (path positions), `off`
(pipeline picks off the path). Writes audit/MATCH_KIND_N.png (20 tiles each) and audit/MATCH_KIND.json
(tile -> unit, frame, x, y); the verdicts go in audit/MATCH_KIND_verdict.json.

    uv run python benchmarks/ball/finetune_audit.py MATCH [--seed N]
"""

import argparse
import csv
import json
import random
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode

import sys
sys.path.insert(0, str(Path(__file__).parent))
import finetune_data as data  # noqa: E402

CROP, ZOOM, RING, COLS, ROWS = 128, 2, 38, 5, 4
SAMPLES = {"only1024": 60, "both": 30, "unsure": 40, "off": 30}


def pools(folder: Path) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = {k: [] for k in SAMPLES}
    for r in csv.DictReader((folder / "labels.csv").open()):
        if r["unit"].startswith("rally") and r["kind"] == "ball":
            if r["teacher"] == "1024" and r["also512"] == "0":
                out["only1024"].append((r["unit"], int(r["frame"]), int(r["x"]), int(r["y"])))
            elif r["also512"] == "1":
                out["both"].append((r["unit"], int(r["frame"]), int(r["x"]), int(r["y"])))
        elif r["unit"].startswith("rally") and r["kind"] == "unsure":
            out["unsure"].append((r["unit"], int(r["frame"]), int(r["x"]), int(r["y"])))
    for r in csv.DictReader((folder / "offpath.csv").open()):
        out["off"].append((r["unit"], int(r["frame"]), int(r["x"]), int(r["y"])))
    return out


def tile(image: np.ndarray, x: int, y: int, number: int) -> np.ndarray:
    h, w = image.shape[:2]
    x0, y0 = min(max(0, x - CROP // 2), w - CROP), min(max(0, y - CROP // 2), h - CROP)
    t = cv2.resize(image[y0 : y0 + CROP, x0 : x0 + CROP], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_CUBIC)
    cx, cy = (x - x0) * ZOOM, (y - y0) * ZOOM
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        a, b = RING * ZOOM // 1, (RING + 12) * ZOOM // 1
        cv2.line(t, (cx + dx * a, cy + dy * a), (cx + dx * b, cy + dy * b), (0, 255, 0), 2)
    cv2.putText(t, str(number), (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return t


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--share", type=float, default=1.0, help="Scale the sample sizes (0.5 for two matches)")
    args = parser.parse_args()
    video, _ = data.match_info(args.match)
    folder = data.OUT / args.match
    audit = data.OUT / "audit"
    audit.mkdir(exist_ok=True)
    rng = random.Random(args.seed)
    chosen = {k: rng.sample(v, min(round(SAMPLES[k] * args.share), len(v))) for k, v in pools(folder).items() if k in SAMPLES}
    wanted = sorted({s[1] for v in chosen.values() for s in v})
    needs: dict[int, list[tuple[str, int]]] = {}
    for kind, items in chosen.items():
        for n, (_, f, _, _) in enumerate(items):
            needs.setdefault(f, []).append((kind, n))
    tiles: dict[tuple[str, int], np.ndarray] = {}
    for f, image in decode.frames_at(video, wanted):
        for kind, n in needs[f]:
            _, _, x, y = chosen[kind][n]
            tiles[kind, n] = tile(image, x, y, n)
    for kind, items in chosen.items():
        (audit / f"{args.match[:10]}_{kind}.json").write_text(json.dumps(items))
        per = COLS * ROWS
        for page in range(0, len(items), per):
            blank = np.zeros((CROP * ZOOM, CROP * ZOOM, 3), np.uint8)
            cells = [tiles.get((kind, n), blank) for n in range(page, min(page + per, len(items)))]
            cells += [blank] * (per - len(cells))
            sheet = np.vstack([np.hstack(cells[r * COLS : (r + 1) * COLS]) for r in range(ROWS)])
            cv2.imwrite(str(audit / f"{args.match[:10]}_{kind}_{page // per}.png"), sheet)


if __name__ == "__main__":
    main()
