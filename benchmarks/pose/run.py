"""Runs a pose model on the cached crops (cache.py), writing the pipeline's own cache formats under
outputs/benchmarks/pose/runs/MODEL/MATCH/ (wrists.json, jumps.json, relances.json, speed.json).

    python benchmarks/pose/run.py MODEL MATCH [--only wrists jumps relances] [--full-jumps]

Top-down models are given the boxes YOLO11m-pose found (the matched wrists.json's) for the wrists, the tracks' boxes for the
jumps; their relances are YOLO11m-pose's (boxes only, which they do not make).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import cache  # noqa: E402
import models  # noqa: E402

from volleyball_stats import actions, attribution, decode, jumps, web  # noqa: E402

FPS = 50.0
ROOT = cache.ROOT


def candidate_boxes(folder: Path, keys: list[str]) -> dict[str, list[np.ndarray]]:
    """Each touch's candidates' boxes, as by_wrists sees them."""
    by_frame = {int(r["frame"]): r for r in web.read_csv(folder / "actions.csv")}
    typed = []
    for key in keys:
        frame = int(key.split(":")[0])
        r = by_frame.get(frame)
        if r is not None:
            typed.append((frame, int(r["x"]), int(r["y"]), r["type"], r["side"]))
    rows = attribution.read_players(folder / "players.csv")
    found = attribution.ranked(typed, rows, FPS)
    by_track, gap = attribution.tracks(rows), round(attribution.GAP_S * FPS)
    return {f"{t[0]}:{t[1]}:{t[2]}": [np.array(attribution.box_at(by_track[c[2]][1], t[0], gap)) for c in c_] for t, c_ in zip(typed, found)}


def wrists(model, name: str, match: str, folder: Path) -> dict:
    files = defaultdict(list)
    for p in (ROOT / match / "wrists").glob("*.npy"):
        frame, x, y, index, x0, y0 = map(int, p.stem.split("_"))
        files[f"{frame}:{x}:{y}"].append((index, x0, y0, p))
    reference = json.loads((folder / "wrists.json").read_text())
    top_down = not isinstance(model, models.Yolo)
    boxes = candidate_boxes(folder, list(files)) if top_down else {}
    out, count, start = {}, 0, time.perf_counter()
    for k, (key, items) in enumerate(sorted(files.items())):
        items.sort()
        entries = []
        for n, (index, x0, y0, path) in enumerate(items):
            image = np.load(path)
            if top_down:
                seen = np.array([b for b, _ in reference[key][n]]).reshape(-1, 4) - np.array([x0, y0, x0, y0])
                wanted = boxes.get(key)
                if wanted:
                    ref = np.array(wanted) - np.array([x0, y0, x0, y0])
                    keep = [any(attribution.iou(tuple(b), tuple(r)) >= 0.3 for r in ref) for b in seen]
                    seen = seen[keep]
                points = model.keypoints(image, seen)
                found = (seen, points)
            else:
                found = model.find([image], 1280, 0.1)[0]
            count += len(found[0]) if top_down else 1
            shift = np.array([x0, y0, 0])
            entries.append([[np.round(b + np.array([x0, y0, x0, y0]), 1).tolist(), np.round(kp + shift, 2).tolist()] for b, kp in zip(*found)])
        out[key] = entries
        if k % 100 == 0:
            print(k, len(files), f"{time.perf_counter() - start:.0f} s", flush=True)
    seconds = time.perf_counter() - start
    return {"cache": out, "seconds": seconds, "calls": sum(len(v) for v in files.values()), "persons": count}


def jump_poses(model, match: str, folder: Path) -> dict:
    attacks = cache.labelled(match)
    rows = jumps.attack_rows(folder / "players.csv", attacks, FPS, folder / "jumps_rows.npz")
    hole = round(jumps.HOLE_S * FPS)
    files = defaultdict(dict)
    for p in (ROOT / match / "jumps" / "..").resolve().joinpath("jumps").glob("*.npy"):
        f, t, k, x0, y0 = map(int, p.stem.split("_"))
        files[(f, t)][k] = (x0, y0, p)
    out, start, calls = {}, time.perf_counter(), 0
    for f, t in attacks:
        boxes = jumps.at(rows[(f, t)], jumps.window(f, FPS), hole)[:, :4]
        result = [None] * len(boxes)
        ks = sorted(files[(f, t)])
        images = [np.load(files[(f, t)][k][2]) for k in ks]
        calls += len(ks)
        if isinstance(model, models.Yolo):
            for k, found, (x0, y0) in zip(ks, model.find(images, jumps.POSE_IMGSZ, 0.1), (files[(f, t)][k][:2] for k in ks)):
                b, kp = found
                if len(b) == 0:
                    continue
                overlap = jumps.iou(boxes[k], b + np.array([x0, y0, x0, y0]))
                if overlap.max() >= jumps.MATCH_IOU:
                    result[k] = np.round(kp[int(overlap.argmax())] + np.array([x0, y0, 0]), 1).tolist()
        else:
            for k, image in zip(ks, images):
                x0, y0 = files[(f, t)][k][:2]
                kp = model.keypoints(image, (boxes[k] - np.array([x0, y0, x0, y0]))[None])[0]
                result[k] = np.round(kp + np.array([x0, y0, 0]), 1).tolist()
        out[f"{f}:{t}"] = result
    return {"cache": out, "seconds": time.perf_counter() - start, "calls": calls}


def relance_boxes(model, folder: Path) -> dict:
    kept = json.loads((folder / "relances.json").read_text())
    video = Path(json.loads((folder / "source.json").read_text())["video"])
    out, start = {}, time.perf_counter()
    frames = sorted(int(k) for k in kept)
    for k, (index, image) in enumerate(decode.frames_at(video, frames)):
        out[str(index)] = np.round(model.find([image], 1280, 0.25)[0][0], 1).tolist()
        if k % 200 == 0:
            print(k, len(frames), flush=True)
    return {"cache": out, "seconds": time.perf_counter() - start, "calls": len(frames)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("match")
    parser.add_argument("--only", nargs="*", default=["wrists", "jumps", "relances"])
    args = parser.parse_args()
    folder = Path("outputs/matches") / args.match
    target = ROOT / "runs" / args.model / args.match
    target.mkdir(parents=True, exist_ok=True)
    model = models.load(args.model)
    speed = json.loads((target / "speed.json").read_text()) if (target / "speed.json").exists() else {}
    for part in args.only:
        if part == "relances" and not isinstance(model, models.Yolo):
            continue
        print(args.model, args.match, part, flush=True)
        got = {"wrists": lambda: wrists(model, args.model, args.match, folder), "jumps": lambda: jump_poses(model, args.match, folder), "relances": lambda: relance_boxes(model, folder)}[part]()
        (target / f"{part}.json").write_text(json.dumps(got["cache"], separators=(",", ":")))
        speed[part] = {k: v for k, v in got.items() if k != "cache"}
        (target / "speed.json").write_text(json.dumps(speed, indent=1))
        print(part, speed[part], flush=True)


if __name__ == "__main__":
    main()
