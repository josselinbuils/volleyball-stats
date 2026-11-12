"""The training set of the touch-type model: one example per pipeline contact of the owner's checked rallies.

    uv run python benchmarks/actions/learned/dataset.py MATCH [RUN]

Reads the frozen truth and the reference run of `benchmarks/corrections` and writes, under outputs/benchmarks/act/MATCH/:
`table.json` (the contact, its rules' type and features, the reviewed type or "none"), `clips.npy` (N x 16 x 320 x 320 x 3,
the crop around the credited player and the ball, 16 frames every 3 from 21 before the contact) and `pose.npz` (the toucher's
17 keypoints over the clip, crop-relative).
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import actions, ball3d, decode, learn
from volleyball_stats.court import Calibration

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/benchmarks/corrections"
# ACT_DIR: another folder for a set built on another reference run.
OUT = ROOT / "outputs/benchmarks" / os.environ.get("ACT_DIR", "act")
OFFSETS = [-21 + 3 * k for k in range(16)]
SIZE = 320
LABELS = ["serve", "pass", "dig", "set", "attack", "block", "relance", "floor", "net", "none"]


def rows(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def pair(truth: dict, auto_rows: list[dict]) -> list[dict]:
    """The pipeline contacts of each checked rally, labelled as `bench.py score` pairs them."""
    fps = truth["fps"]
    lead, within = round(actions.LEAD_S * fps), round(learn.SAME_S * fps)
    out, seen = [], set()
    for r in truth["rallies"]:
        auto = [x for x in auto_rows if r["start_frame"] - lead <= int(x["frame"]) <= r["end_frame"]]
        frames = [int(x["frame"]) for x in auto]
        label = {}
        for c in r["touches"]:
            f = learn.near(c["frame"], frames, within)
            if f is not None and (f not in label or abs(c["frame"] - f) < label[f][1]):
                label[f] = (c["type"], abs(c["frame"] - f), c["team"])
        for x in auto:
            f = int(x["frame"])
            if f in seen:
                continue
            seen.add(f)
            kind = label.get(f, ("none", 0, None))
            out.append({"rally": r["key"], "frame": f, "x": int(x["x"]), "y": int(x["y"]), "rules": x["type"], "side": x["side"], "track": x["track"], "team": x["team"],
                        "label": kind[0] if kind[0] in LABELS else "other:" + kind[0], "truth_team": kind[2], "rally_start": r["start_frame"], "rally_end": r["end_frame"]})
    return out


def features(table: list[dict], run: Path, calibration: Calibration, fps: float) -> None:
    """The non-visual features of each contact, from its rally's other contacts and the ball's 3D flight."""
    windows = [(int(w["start_frame"]), int(w["end_frame"])) for w in rows(run / "rallies.csv")]
    typed = [(int(x["frame"]), int(x["x"]), int(x["y"]), x["type"], x["side"]) for x in rows(run / "actions.csv")]
    places = ball3d.flight_places(typed, windows, round(actions.LEAD_S * fps), run / "ball.csv", calibration, fps) if calibration.lens else {}
    by_rally: dict[int, list[dict]] = {}
    for t in table:
        by_rally.setdefault(t["rally"], []).append(t)
    for group in by_rally.values():
        group.sort(key=lambda t: t["frame"])
        for k, t in enumerate(group):
            prev, nxt = group[k - 1] if k else None, group[k + 1] if k + 1 < len(group) else None
            t["index"], t["count"] = k, len(group)
            t["prev_s"] = (t["frame"] - prev["frame"]) / fps if prev else -1.0
            t["next_s"] = (nxt["frame"] - t["frame"]) / fps if nxt else -1.0
            t["prev_type"], t["next_type"] = (prev["rules"] if prev else "start"), (nxt["rules"] if nxt else "end")
            t["prev_side"], t["next_side"] = (prev["side"] if prev else ""), (nxt["side"] if nxt else "")
            n = 0
            for u in reversed(group[: k + 1]):
                if u["side"] != t["side"]:
                    break
                n += u["rules"] not in ("floor", "block", "net")
            t["side_run"] = n
            cx, cy = calibration.to_court(np.array([[t["x"], t["y"]]]))[0]
            t["court_x"], t["court_y"] = float(cx), float(cy)
            p = places.get(t["frame"])
            q = places.get(nxt["frame"]) if nxt else None
            t["place"] = None if p is None else [float(v) for v in p]
            if p is not None and q is not None and t["next_s"] > 0:
                s = t["next_s"]
                t["rise"] = float((q[2] - p[2] + 9.81 * s * s / 2) / s)
                t["speed"] = float(np.hypot(*(q[:2] - p[:2])) / s)
            else:
                t["rise"] = t["speed"] = None


def crop_boxes(table: list[dict], players: dict[int, dict[str, np.ndarray]], width: int, height: int) -> None:
    """Each contact's square crop (x0, y0, side): the credited track's box, else the nearest box to the ball, with the ball."""
    for t in table:
        f = t["frame"]
        boxes = players.get(f) or players.get(f - 1) or players.get(f + 1) or {}
        box = boxes.get(str(t["track"])) if t["track"] != "" else None
        if box is None and boxes:
            cx, cy = t["x"], t["y"]
            box = min(boxes.values(), key=lambda b: np.hypot((b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy))
        t["has_box"] = box is not None
        x1, y1, x2, y2 = box if box is not None else [t["x"] - 150, t["y"] - 300, t["x"] + 150, t["y"] + 300]
        x1, y1, x2, y2 = min(x1, t["x"]), min(y1, t["y"]), max(x2, t["x"]), max(y2, t["y"])
        side = int(min(1000, max(360, 1.3 * max(x2 - x1, y2 - y1))))
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        t["crop"] = [int(min(max(cx - side / 2, 0), width - side)), int(min(max(cy - side / 2, 0), height - side)), side]


def build_clips(match: str, table: list[dict], video: Path) -> None:
    out = OUT / match
    if (out / "clips.done").exists():
        return
    path, progress = out / "clips.npy", out / "clips.progress"
    resume = path.exists() and progress.exists()
    clips = np.lib.format.open_memmap(path, mode="r+" if resume else "w+", dtype=np.uint8, shape=(len(table), 16, SIZE, SIZE, 3))
    first = int(progress.read_text()) if resume else 0
    order = sorted(range(len(table)), key=lambda i: table[i]["frame"])
    for start in range(first, len(order), 60):
        chunk = order[start : start + 60]
        need: dict[int, list[tuple[int, int]]] = {}
        for i in chunk:
            for k, o in enumerate(OFFSETS):
                need.setdefault(max(table[i]["frame"] + o, 0), []).append((i, k))
        for attempt in range(8):
            try:
                for f, image in decode.frames_at(video, need):
                    for i, k in need[f]:
                        x0, y0, s = table[i]["crop"]
                        clips[i, k] = cv2.resize(image[y0 : y0 + s, x0 : x0 + s], (SIZE, SIZE), interpolation=cv2.INTER_AREA)
                break
            except RuntimeError as error:
                # The GPU decoder fails to start when the card is busy: wait, then decode on the CPU.
                print("decode failed, retry", attempt, str(error)[-80:].replace("\n", " "), flush=True)
                if attempt >= 3:
                    decode.hardware = lambda video: ()
                time.sleep(10)
        else:
            raise RuntimeError("decoding failed")
        progress.write_text(str(start + 60))
        print("clips", min(start + 60, len(order)), "/", len(order), flush=True)
    clips.flush()
    (out / "clips.done").write_text("ok")


def build_pose(match: str, table: list[dict]) -> None:
    from ultralytics import YOLO

    out = OUT / match
    clips = np.load(out / "clips.npy", mmap_mode="r")
    model = YOLO(str(ROOT / actions.POSE_MODEL))
    keys = np.zeros((len(table), 16, 17, 3), np.float32)
    boxes = np.zeros((len(table), 16, 4), np.float32)
    ref = np.array([0.25, 0.1, 0.75, 0.9]) * SIZE
    for i in range(len(table)):
        found = model.predict([np.ascontiguousarray(clips[i, k]) for k in range(16)], imgsz=SIZE, conf=0.2, verbose=False)
        picks = [(r.boxes.xyxy.cpu().numpy(), r.keypoints.data.cpu().numpy()) for r in found]
        for k, before in [(7, None), *[(k, k - 1) for k in range(8, 16)], *[(k, k + 1) for k in range(6, -1, -1)]]:
            b, kp = picks[k]
            if not len(b):
                continue
            target = ref if before is None else (boxes[i, before] if boxes[i, before].any() else boxes[i, 7] if boxes[i, 7].any() else ref)
            j = int(np.argmax(actions.overlap(target, b)))
            boxes[i, k], keys[i, k] = b[j], kp[j]
        if i % 200 == 0:
            print("pose", i, flush=True)
    np.savez(out / "pose.npz", keys=keys / np.array([SIZE, SIZE, 1.0], np.float32), boxes=boxes / SIZE)


def main() -> None:
    match = next(m for m in sorted(p.name for p in BASE.iterdir()) if m.startswith(sys.argv[1]))
    run = BASE / match / "runs" / (sys.argv[2] if len(sys.argv) > 2 else "players-near") / match
    src = json.loads((ROOT / "outputs/matches" / match / "source.json").read_text())
    video, calibration = ROOT / src["video"], Calibration.load(ROOT / src["court"])
    truth = json.loads((BASE / match / "truth.json").read_text())
    fps = truth["fps"]
    out = OUT / match
    out.mkdir(parents=True, exist_ok=True)
    table = pair(truth, rows(run / "actions.csv"))
    features(table, run, calibration, fps)
    players: dict[int, dict[str, np.ndarray]] = {}
    for r in rows(run / "players.csv"):
        players.setdefault(int(r["frame"]), {})[r["track"]] = np.array([float(r[k]) for k in ("x1", "y1", "x2", "y2")])
    width, height = decode.size(video)
    crop_boxes(table, players, width, height)
    (out / "table.json").write_text(json.dumps({"match": match, "fps": fps, "offsets": OFFSETS, "contacts": table}))
    print(match, len(table), "contacts;", {k: sum(t["label"] == k for t in table) for k in sorted({t["label"] for t in table})}, flush=True)
    build_clips(match, table, video)
    print("clips done", flush=True)
    if not (out / "pose.npz").exists():
        build_pose(match, table)
    print("pose done", flush=True)


if __name__ == "__main__":
    main()
