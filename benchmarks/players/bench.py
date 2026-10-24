"""Score player detection, court filtering and tracking against hand-labelled feet.

    uv run --group bench python benchmarks/players/bench.py detect VIDEO:GROUND_TRUTH ... [--models yolo11n,...] [--sizes 640,...]
    uv run --group bench python benchmarks/players/bench.py track VIDEO:SEQUENCE ... [--trackers bytetrack,...]

`detect` runs each detector and inference size on the labelled frames, picks the confidence with
the best F1 on the first pair and scores every pair there. `track` runs `players.track_frames` and
`players.finish` over each labelled sequence and counts identity errors on its labelled frames.
Both clips share one fixed camera, calibrated from benchmarks/court/ground_truth/side_club.json.
"""

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import players
from volleyball_stats.ball import default_device
from volleyball_stats.court import fit

COURT = Path("benchmarks/court/ground_truth/side_club.json")
# A detection matches a labelled player when its feet point (box bottom center) is within this
# many pixels; see the README for why 20.
TOLERANCE = 20
CONFS = [round(0.05 * i, 2) for i in range(1, 15)]
SPEED_FRAMES = 150
TRACKERS = {
    "bytetrack": ("bytetrack", {}),
    "botsort": ("botsort", {}),
    "botsort-reid": ("botsort", {"with_reid": True, "model": "models/yolo11n-cls.pt"}),
}


def calibration():
    """Least squares on the line landmarks: the post distances are guesses."""
    points = json.loads(COURT.read_text())["points"]
    return fit({n: tuple(p) for n, p in points.items() if not n.startswith("post")}, ransac=False)


def load_truth(path: Path) -> dict[int, list[dict]]:
    by_frame: dict[int, list[dict]] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            by_frame.setdefault(int(row["frame"]), []).append({**row, "xy": (float(row["x"]), float(row["y"]))})
    return by_frame


def read(video: Path, frames: list[int]) -> dict[int, np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    out = {}
    for index in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Cannot read frame {index} of {video}")
        out[index] = frame
    cap.release()
    return out


def run(video: Path, start: int, end: int):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    for _ in range(start, end):
        ok, frame = cap.read()
        if not ok:
            break
        yield frame
    cap.release()


def match(truth: np.ndarray, found: np.ndarray, tolerance: float = TOLERANCE) -> list[tuple[int, int]]:
    """(truth, found) index pairs, closest first, each used once, within `tolerance` px."""
    if not len(truth) or not len(found):
        return []
    distance = np.linalg.norm(truth[:, None] - found[None], axis=2)
    pairs, used_t, used_f = [], set(), set()
    for t, f in zip(*np.unravel_index(np.argsort(distance, axis=None), distance.shape)):
        if distance[t, f] > tolerance:
            break
        if t not in used_t and f not in used_f:
            pairs.append((int(t), int(f)))
            used_t.add(t)
            used_f.add(f)
    return pairs


def score_detections(truth: dict[int, list[dict]], boxes: dict[int, np.ndarray], conf: float, cal) -> dict:
    tp = fp = fn = far = far_found = dropped = visible = visible_found = 0
    errors = []
    for frame, labels in truth.items():
        b = boxes[frame][boxes[frame][:, 4] >= conf]
        xy = players.feet(b)
        keep = players.on_court(cal.to_court(xy)) if len(b) else np.zeros(0, bool)
        gt = np.array([label["xy"] for label in labels])
        raw_pairs = match(gt, xy)
        pairs = match(gt, xy[keep])
        dropped += len({t for t, f in raw_pairs if not keep[f]} - {t for t, _ in pairs})
        tp += len(pairs)
        fp += int(keep.sum()) - len(pairs)
        fn += len(gt) - len(pairs)
        gt_court = cal.to_court(gt)
        far += int((gt_court[:, 1] < 0).sum())
        far_found += sum(gt_court[t, 1] < 0 for t, _ in pairs)
        visible += sum(label["note"] != "hidden" for label in labels)
        visible_found += sum(labels[t]["note"] != "hidden" for t, _ in pairs)
        found_court = cal.to_court(xy[keep]) if keep.any() else np.empty((0, 2))
        errors += [float(np.linalg.norm(gt_court[t] - found_court[f])) for t, f in pairs]
    total = tp + fn
    return {
        "P": tp / max(tp + fp, 1),
        "R": tp / max(total, 1),
        "F1": 2 * tp / max(2 * tp + fp + fn, 1),
        "R far": far_found / max(far, 1),
        "R visible": visible_found / max(visible, 1),
        "dropped": dropped,
        "false/frame": fp / len(truth),
        "err med m": float(np.median(errors)) if errors else float("nan"),
        "err p90 m": float(np.percentile(errors, 90)) if errors else float("nan"),
    }


def detect(pairs: list[tuple[Path, Path]], models: list[str], sizes: list[int]) -> None:
    cal, device = calibration(), default_device()
    truths = {video: load_truth(truth) for video, truth in pairs}
    frames = {video: read(video, sorted(truth)) for video, truth in truths.items()}
    columns = ["P", "R", "F1", "R visible", "R far", "dropped", "false/frame", "err med m", "err p90 m"]
    print(f"{'model':8} {'imgsz':>5} {'conf':>5} {'clip':14} " + " ".join(f"{c:>11}" for c in columns) + f" {'fps':>5}")
    for name in models:
        model = players.load_model(Path(f"models/{name}.pt"))
        for imgsz in sizes:
            boxes = {video: {i: players.detect(f, model, device, imgsz, CONFS[0]) for i, f in fs.items()} for video, fs in frames.items()}
            first = pairs[0][0]
            conf = max(CONFS, key=lambda c: score_detections(truths[first], boxes[first], c, cal)["F1"])
            start = time.perf_counter()
            count = sum(1 for frame in run(first, 0, SPEED_FRAMES) if players.detect(frame, model, device, imgsz, conf) is not None)
            fps = count / (time.perf_counter() - start)
            for video in truths:
                s = score_detections(truths[video], boxes[video], conf, cal)
                print(f"{name:8} {imgsz:5} {conf:5.2f} {video.stem:14} " + " ".join(f"{s[c]:11.3f}" for c in columns) + f" {fps:5.1f}")


def identity(truth: dict[int, list[dict]], rows: list[players.Row]) -> dict:
    """On the labelled frames: CLEAR-MOT ID switches, track IDs per labelled player, IDF1, team
    accuracy (players are named W* on the left, N* on the right) and tracks never matching a
    labelled player (non-players kept, or players only ever hidden in the labels)."""
    by_frame: dict[int, list[players.Row]] = {}
    for r in rows:
        by_frame.setdefault(r.frame, []).append(r)
    last: dict[str, int] = {}
    ids: dict[str, set[int]] = {}
    together: Counter = Counter()
    switches = matched = labelled = predicted = teams = 0
    present, kept = set(), set()
    for frame in sorted(truth):
        labels, found = truth[frame], by_frame.get(frame, [])
        labelled += len(labels)
        predicted += len(found)
        present |= {r.track for r in found}
        pairs = match(np.array([l["xy"] for l in labels]), np.array([r.feet for r in found]).reshape(-1, 2))
        matched += len(pairs)
        for t, f in pairs:
            player, track = labels[t]["player"], found[f].track
            teams += found[f].team == ("left" if player[0] == "W" else "right")
            if player in last and last[player] != track:
                switches += 1
            last[player] = track
            ids.setdefault(player, set()).add(track)
            together[player, track] += 1
            kept.add(track)
    # IDF1: each player paired with at most one track, the pairing that shares the most frames.
    idtp, used_p, used_t = 0, set(), set()
    for (player, track), n in together.most_common():
        if player not in used_p and track not in used_t:
            idtp += n
            used_p.add(player)
            used_t.add(track)
    return {
        "recall": matched / labelled,
        "precision": matched / max(predicted, 1),
        "ID switches": switches,
        "IDs/player": float(np.mean([len(v) for v in ids.values()])),
        "IDF1": 2 * idtp / (labelled + predicted),
        "team": teams / max(matched, 1),
        "other tracks": len(present - kept),
    }


def track(pairs: list[tuple[Path, Path]], trackers: list[str], model_name: str, imgsz: int, conf: float, buffer: int | None) -> None:
    cal, device = calibration(), default_device()
    model = players.load_model(Path(f"models/{model_name}.pt"))
    columns = ["recall", "precision", "ID switches", "IDs/player", "IDF1", "team", "other tracks"]
    print(f"{'tracker':13} {'clip':22} {'pass':7} " + " ".join(f"{c:>11}" for c in columns) + f" {'fps':>5}")
    for name in trackers:
        kind, extra = TRACKERS[name]
        if buffer:
            extra = {**extra, "track_buffer": buffer}
        for video, truth_path in pairs:
            truth = load_truth(truth_path)
            start, end = min(truth) - 30, max(truth) + 1
            fps_video = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
            tracker = players.make_tracker(kind, conf, **extra)
            t0 = time.perf_counter()
            online = [r for rows in players.track_frames(run(video, start, end), cal, model, device, tracker, imgsz) for r in rows]
            fps = (end - start) / (time.perf_counter() - t0)
            online = [players.Row(r.frame + start, r.track, r.box, r.conf, r.feet, r.court) for r in online]
            for label, rows in (("online", online), ("offline", players.finish(online, fps_video))):
                s = identity(truth, rows)
                print(f"{name:13} {truth_path.stem:22} {label:7} " + " ".join(f"{s[c]:11.3f}" for c in columns) + f" {fps:5.1f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    detect_parser = sub.add_parser("detect")
    detect_parser.add_argument("pairs", nargs="+", help="VIDEO:GROUND_TRUTH_CSV")
    detect_parser.add_argument("--models", default="yolo11n,yolo11s,yolo11m,yolo11x")
    detect_parser.add_argument("--sizes", default="640,1280,1920")
    track_parser = sub.add_parser("track")
    track_parser.add_argument("pairs", nargs="+", help="VIDEO:SEQUENCE_CSV")
    track_parser.add_argument("--trackers", default=",".join(TRACKERS))
    track_parser.add_argument("--model", default=players.MODEL.stem)
    track_parser.add_argument("--imgsz", type=int, default=players.IMGSZ)
    track_parser.add_argument("--conf", type=float, default=players.CONF)
    track_parser.add_argument("--buffer", type=int, help="Overrides the trackers' track_buffer")
    args = parser.parse_args()
    pairs = [tuple(map(Path, p.split(":"))) for p in args.pairs]
    if args.command == "detect":
        detect(pairs, args.models.split(","), [int(s) for s in args.sizes.split(",")])
    else:
        track(pairs, args.trackers.split(","), args.model, args.imgsz, args.conf, args.buffer)


if __name__ == "__main__":
    main()
