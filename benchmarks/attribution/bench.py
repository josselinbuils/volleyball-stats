"""Score contact attribution against hand-labelled touchers.

    uv run --group bench python benchmarks/attribution/bench.py CLIP ... [--verbose] [--pose]

Each CLIP reads outputs/ball/CLIP_ball.csv, outputs/players/CLIP_players.csv,
benchmarks/contacts/ground_truth/CLIP.csv, benchmarks/attribution/ground_truth/CLIP.csv and, with
--pose, data/CLIP.mp4. Every method (the module's steps, from the nearest-box baseline) gets two
scores, pooled over the clips given:
- `truth`: the labelled contacts with their labelled types (sides from actions.classify_rally);
- `detected`: contacts.detect in the labelled windows typed by actions.classify_rally, matched to
  the labelled contacts within ±2 frames; a missed contact counts as wrong.
All clips run at 29.97 fps with the net at x=612, on the court of
benchmarks/court/ground_truth/side_club.json (same camera).
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats import actions, attribution, contacts, court
from volleyball_stats.players import Row

FPS = 29.97
NET_X = 612
TOLERANCE = 2
ROUNDS = 2000
TYPES = ("serve", "pass", "set", "attack", "dig", "block", "")
COURT = Path("benchmarks/court/ground_truth/side_club.json")
# Pose veto: wrists above POSE_CONF of the pose detection overlapping a candidate's box by POSE_IOU.
POSE_CONF, POSE_IOU, VETO = 0.7, 0.5, 0.4


def load_contacts(path: Path) -> list[dict]:
    """One dict per rally: start, end, contacts {frame: type}, net [frames]."""
    found: dict[str, dict] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rally = found.setdefault(row["rally"], {"contacts": {}, "net": []})
            if row["event"] in ("start", "end"):
                rally[row["event"]] = int(row["frame"])
            elif row["event"] == "contact":
                rally["contacts"][int(row["frame"])] = row["type"]
            else:
                rally["net"].append(int(row["frame"]))
    return list(found.values())


def load_touchers(path: Path) -> dict[int, dict]:
    with open(path) as f:
        return {int(r["frame"]): r for r in csv.DictReader(f)}


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def matches(box, toucher: dict) -> bool:
    """IoU >= 0.5 with the labelled box, or the labelled torso point inside the box."""
    if toucher["x1"] and iou(box, [float(toucher[k]) for k in ("x1", "y1", "x2", "y2")]) >= 0.5:
        return True
    return bool(toucher["x"]) and box[0] <= float(toucher["x"]) <= box[2] and box[1] <= float(toucher["y"]) <= box[3]


def right(track: int | None, toucher: dict, box: tuple | None) -> bool:
    """Whether the predicted track, whose box at the labelled frame is `box`, is the labelled
    toucher; None is right when no player touched."""
    if toucher["toucher"] == "none":
        return track is None
    return box is not None and matches(box, toucher)


def interval(hits: list[bool]) -> tuple[float, float]:
    """95% bootstrap interval of the share of hits."""
    rng = random.Random(0)
    scores = sorted(sum(rng.choices(hits, k=len(hits))) / len(hits) for _ in range(ROUNDS))
    return scores[int(0.025 * ROUNDS)], scores[int(0.975 * ROUNDS)]


def report(name: str, results: list[tuple[str, str, bool]]) -> None:
    """Accuracy per labelled type over (type, toucher kind, hit) rows."""
    print(f"\n{name}")
    print(f"  {'type':10} {'right':>8} {'acc':>6} {'95% interval':>14}")
    groups = [(kind or "(unclear)", [h for t, k, h in results if t == kind and k != "none"]) for kind in TYPES]
    groups.append(("players", [h for t, k, h in results if k != "none"]))
    groups.append(("typed", [h for t, k, h in results if k != "none" and t]))
    groups.append(("no player", [h for t, k, h in results if k == "none"]))
    for label, hits in groups:
        if hits:
            lo, hi = interval(hits)
            print(f"  {label:10} {sum(hits):3}/{len(hits):<4} {sum(hits) / len(hits):6.3f} {f'[{lo:.2f}-{hi:.2f}]':>14}")


def calibration() -> court.Calibration:
    """Least squares on the hand-located line landmarks; the posts' distance to the court is unknown."""
    points = json.loads(COURT.read_text())["points"]
    return court.fit({name: tuple(p) for name, p in points.items() if not name.startswith("post")}, ransac=False)


def pair(found: list[int], truth: list[int]) -> dict[int, int]:
    """Truth frame -> detected frame, one to one, nearest first, within TOLERANCE."""
    free, out = sorted(found), {}
    for t in sorted(truth):
        near = [d for d in free if abs(d - t) <= TOLERANCE]
        if near:
            out[t] = min(near, key=lambda d: abs(d - t))
            free.remove(out[t])
    return out


def nearest(typed: list[actions.Typed], rows: list[Row]) -> list[int | None]:
    """Baseline: the track of either side whose box at the contact frame is nearest to the ball."""
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r.frame].append(r)
    out = []
    for frame, x, y, kind, _ in typed:
        best = min(by_frame[frame], key=lambda r: attribution.distance((x, y), r.box), default=None)
        out.append(None if kind in attribution.NO_PLAYER or best is None else best.track)
    return out


def variant(**constants):
    """attribution.attribute with some module constants overridden."""

    def run(typed: list[actions.Typed], rows: list[Row]) -> list[int | None]:
        saved = {name: getattr(attribution, name) for name in constants}
        vars(attribution).update(constants)
        try:
            return attribution.attribute(typed, rows, FPS)
        finally:
            vars(attribution).update(saved)

    return run


OFF = float("inf")
METHODS = {
    "nearest box, either side": nearest,
    "nearest box of the contact's side": variant(GAP_S=0.0, REACH=0.0, SIDE_M=OFF),
    "+ tracks missing up to 0.17 s": variant(REACH=0.0, SIDE_M=OFF),
    "+ an arm above serves, attacks, blocks": variant(SIDE_M=OFF),
    "+ feet past the net at the contact frame out (attribute)": variant(),
}


def pose_veto(video: Path):
    """attribute, then candidates whose confident wrists (YOLO11m-pose, frames t-1..t+1) are all
    over VETO box heights from the ball lose to the others, on sets, passes, digs and unclear touches."""
    import cv2
    from ultralytics import YOLO

    model, cap = YOLO(str(actions.POSE_MODEL)), cv2.VideoCapture(str(video))

    def poses(frame: int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, image = cap.read()
        result = model.predict(image, imgsz=1280, conf=0.1, verbose=False)[0]
        return result.boxes.xyxy.cpu().numpy(), result.keypoints.data.cpu().numpy()

    def far(ball, box, frames) -> bool:
        wrists = []
        for boxes, keypoints in frames:
            ious = [iou(box, b) for b in boxes]
            if ious and max(ious) >= POSE_IOU:
                wrists += [k for k in keypoints[int(np.argmax(ious))][[9, 10]] if k[2] >= POSE_CONF]
        return bool(wrists) and min(np.hypot(*(k[:2] - ball)) for k in wrists) / (box[3] - box[1]) > VETO

    def run(typed: list[actions.Typed], rows: list[Row]) -> list[int | None]:
        by_track, gap, out = attribution.tracks(rows), round(attribution.GAP_S * FPS), []
        for (frame, x, y, kind, side), first in zip(typed, attribution.attribute(typed, rows, FPS)):
            if first is None or kind in attribution.ABOVE_HEAD:
                out.append(first)
                continue
            frames = [poses(f) for f in (frame - 1, frame, frame + 1)]
            candidates = [(t, b) for t, (team, boxes) in by_track.items() if team == side and (b := attribution.box_at(boxes, frame, gap))]
            out.append(min(candidates, key=lambda c: (far(np.array((x, y)), c[1], frames), attribution.distance((x, y), c[1])))[0])
        return out

    return run


def score(clips: list[str], verbose: bool, pose: bool) -> None:
    cal = calibration()
    gap = round(attribution.GAP_S * FPS)
    results = defaultdict(list)
    # attribute's doubts: (doubt, right) per labelled player contact.
    doubts = defaultdict(list)
    for clip in clips:
        rows = attribution.read_players(Path(f"outputs/players/{clip}_players.csv"))
        by_track = attribution.tracks(rows)
        touchers = load_touchers(Path(f"benchmarks/attribution/ground_truth/{clip}.csv"))
        track = contacts.read_track(Path(f"outputs/ball/{clip}_ball.csv"))
        filled = contacts.interpolate(track)
        found, crossings = contacts.detect(track, FPS, NET_X)
        truth, detected, labels, matched = [], [], {}, {}
        for rally in load_contacts(Path(f"benchmarks/contacts/ground_truth/{clip}.csv")):
            start, end = rally["start"], rally["end"]
            labels |= rally["contacts"]
            given = [(f, round(filled[f, 0]), round(filled[f, 1])) for f in rally["contacts"]]
            truth += [(f, x, y, rally["contacts"][f], side) for f, x, y, _, side in actions.classify_rally(given, rally["net"], FPS, NET_X, cal)]
            inside = [c for c in found if start <= c[0] <= end]
            typed = actions.classify_rally(inside, [c for c in crossings if start <= c <= end], FPS, NET_X, cal)
            detected += typed
            matched |= pair([t[0] for t in typed], list(rally["contacts"]))
        methods = METHODS | ({"+ pose veto on sets, passes, digs": pose_veto(Path(f"data/{clip}.mp4"))} if pose else {})
        for name, method in methods.items():
            on_truth = dict(zip([t[0] for t in truth], method(truth, rows)))
            on_detected = dict(zip([t[0] for t in detected], method(detected, rows)))
            for f, kind in labels.items():

                def hit(track: int | None) -> bool:
                    return right(track, touchers[f], None if track is None else attribution.box_at(by_track[track][1], f, gap))

                results[name, "truth"].append((kind, touchers[f]["toucher"], hit(on_truth[f])))
                results[name, "detected"].append((kind, touchers[f]["toucher"], f in matched and hit(on_detected[matched[f]])))
                if verbose and name == list(METHODS)[-1]:
                    print(f"{clip} {f:6} {kind or '?':7} {touchers[f]['toucher']:8} truth: track {on_truth[f]} {'ok' if results[name, 'truth'][-1][2] else 'WRONG'}"
                          f", detected: track {on_detected.get(matched.get(f))} {'ok' if results[name, 'detected'][-1][2] else 'WRONG'}")
            if name == list(METHODS)[-1]:
                for set_name, typed, on in (("truth", truth, on_truth), ("detected", detected, on_detected)):
                    gaps = dict(zip([t[0] for t in typed], map(attribution.gap_to_next, attribution.ranked(typed, rows, FPS))))
                    for f, kind in labels.items():
                        key = f if set_name == "truth" else matched.get(f)
                        if kind and touchers[f]["toucher"] != "none" and key is not None and on[key] is not None:
                            g = gaps[key]
                            doubts[set_name].append((g is not None and g < attribution.DOUBT, results[name, set_name][-len(labels) + list(labels).index(f)][2]))
            if verbose and name == list(METHODS)[-1]:
                false = [d for d in on_detected if d not in matched.values()]
                print(f"{clip}: {len(false)} detected contacts match no label, {sum(on_detected[d] is not None for d in false)} attributed to a track")
    for (name, kind), rows_ in results.items():
        report(f"{name}, {kind}", rows_)
    for set_name, rows_ in doubts.items():
        wrong = [d for d, ok in rows_ if not ok]
        print(f"\ndoubts (next candidate under {attribution.DOUBT} box heights), {set_name}: {sum(d for d, _ in rows_)} of {len(rows_)} attributed touches,"
              f" {sum(wrong)} of their {len(wrong)} wrong picks")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", help="Clip stems, e.g. side_club")
    parser.add_argument("--verbose", action="store_true", help="List every labelled contact")
    parser.add_argument("--pose", action="store_true", help="Also score the pose veto (runs YOLO11m-pose)")
    args = parser.parse_args()
    score(args.clips, args.verbose, args.pose)


if __name__ == "__main__":
    main()
