"""Contact attribution: the player track that touched the ball at each typed contact.

The toucher is the track of the contact's side (actions.py; a block's side is the blocker's) whose
box is nearest to the ball at the contact frame, in box heights so near and far players compare.
A contact played above the head (serve, attack, block) may lie up to an arm above the box: the
detector leaves the blurred hitting arm out. A track the detector drops for a few frames around the
contact (blur, a teammate in front) stays a candidate, its box interpolated over the gap, unless its
feet stand clearly on the other side of the net then: a track that swapped players across the net.
For the same reason a track of the other side whose feet stand well inside the contact's side is a
candidate. A ball inside two boxes goes to the bigger one, the player nearer the camera. Floor and
net contacts have no player. For touches below the head, `by_wrists` then reorders the candidates
near the ball by the players' wrists (pose). Two candidates about as near the ball make the pick a
doubt, asked in the review. See benchmarks/attribution/README.md for the numbers behind the constants.

    uv run python -m volleyball_stats.attribution ACTIONS_CSV PLAYERS_CSV --fps FPS [--out DIR]
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from volleyball_stats import files
from volleyball_stats.actions import LATE_FLIGHT_S, POSE_MODEL, Typed
from volleyball_stats.players import Row

NO_PLAYER = {"floor", "net"}
ABOVE_HEAD = {"serve", "attack", "block"}
# Box heights the ball may be above an above-the-head toucher's box.
REACH = 0.5
# Seconds a track may be missing on each side of the contact frame and stay a candidate.
GAP_S = 0.17
# A candidate whose feet stand over SIDE_M meters past the net on the other side at the contact
# frame is out: its track kept the side of the player it followed first.
SIDE_M = 0.5
# A track of the other side whose feet stand over CROSS_M meters inside the contact's side at the
# contact frame is a candidate: it swapped players at the net (first ASPOM match: 4 more of the 135
# touches answered right).
CROSS_M = 1.0
# A next candidate under DOUBT box heights farther from the ball than the toucher makes a doubt.
DOUBT = 0.05
# A touch whose nearest candidate stands over FAR box heights from the ball is none: the ball
# changing course with no player at it, mostly out of the frame and back (first ASPOM match: 16 of
# the 22 touches the review said were none, none of the 116 it confirmed).
FAR = 0.5
# A touch with the ball at FEET or lower of its nearest candidate's box height is a bounce beside
# them (first ASPOM match, checked rallies: 7 false, no real one; at 0.85, 8 and 4).
FEET = 0.9
# Touches below the head (`by_wrists`): a candidate whose wrists (pose keypoints over WRIST_CONF, of
# the pose box overlapping the track's by WRIST_IOU or more, frames t-1..t+1) all stand over
# WRIST_VETO box heights from the ball goes last; among the others within WRIST_MARGIN box heights
# of the nearest, the one whose wrists come nearest to the ball wins (`wrist_order`).
BELOW_HEAD = {"pass", "set", "dig", "relance"}
WRIST_VETO, WRIST_MARGIN, WRIST_CONF, WRIST_IOU = 0.4, 0.2, 0.7, 0.5
# Metres from the ball's 3D place beyond which a candidate's distance says no more (`court_metres`).
COURT_MAX_M = 6.0
# The pose model sees a square of POSE_CROP frame heights around the ball.
POSE_CROP = 0.74

Box = tuple[float, float, float, float]
Candidate = tuple[float, float, int]


def read_players(path: Path) -> list[Row]:
    """Rows of a CSV written by players.write_csv."""
    with open(path) as f:
        return [
            Row(int(r["frame"]), int(r["track"]), tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2")), float(r["conf"]),
                (float(r["feet_x"]), float(r["feet_y"])), (float(r["court_x"]), float(r["court_y"])), r["team"])
            for r in csv.DictReader(f)
        ]


def distance(ball: tuple[float, float], box: Box, reach: float = 0.0) -> float:
    """Ball to box in box heights, 0 inside; the box reaches `reach` heights above its top."""
    x1, y1, x2, y2 = box
    h = y2 - y1
    return float(np.hypot(max(0, x1 - ball[0], ball[0] - x2), max(0, y1 - reach * h - ball[1], ball[1] - y2))) / h


def box_at(boxes: dict[int, Box], frame: int, gap: int) -> Box | None:
    """A track's box at `frame`: its own, else interpolated between its nearest boxes within `gap`
    frames, else the nearest one; None when it has none that close."""
    if frame in boxes:
        return boxes[frame]
    before = next((f for f in range(frame - 1, frame - gap - 1, -1) if f in boxes), None)
    after = next((f for f in range(frame + 1, frame + gap + 1) if f in boxes), None)
    if before is None or after is None:
        return boxes.get(before if after is None else after)
    a, b = np.array(boxes[before]), np.array(boxes[after])
    return tuple((a + (b - a) * (frame - before) / (after - before)).tolist())


def tracks(rows: list[Row]) -> dict[int, tuple[str, dict[int, Box]]]:
    """Track -> (team, frame -> box)."""
    out: dict[int, tuple[str, dict[int, Box]]] = {}
    for r in rows:
        out.setdefault(r.track, (r.team, {}))[1][r.frame] = r.box
    return out


def court_x(xs: dict[int, float], frame: int, gap: int) -> float | None:
    """A track's feet court x at `frame`, else at its nearest frame within `gap`."""
    for d in range(gap + 1):
        for f in (frame - d, frame + d):
            if f in xs:
                return xs[f]
    return None


def ranked(typed: list[Typed], rows: list[Row], fps: float) -> list[list[Candidate]]:
    """Each contact's candidates, nearest first: (distance with the reach, plain distance, track);
    none for the floor and the net. Equal distances go to the bigger box: a ball inside two boxes
    is mostly the front player's (first ASPOM match: 93 of the 135 touches answered right, against
    85 for the track number)."""
    by_track, gap = tracks(rows), round(GAP_S * fps)
    feet: dict[int, dict[int, float]] = {}
    for r in rows:
        feet.setdefault(r.track, {})[r.frame] = r.court[0]
    out = []
    # ponytail: scans every track per contact, O(tracks × contacts); index the tracks by frame if a
    # whole match is slow.
    for frame, x, y, kind, side in typed:
        reach = REACH if kind in ABOVE_HEAD else 0.0
        found = []
        # Feet court x times `inward` is positive inside the contact's side.
        inward = -1 if side == "left" else 1
        for track, (team, boxes) in by_track.items():
            box = None if kind in NO_PLAYER else box_at(boxes, frame, gap)
            if box is None:
                continue
            at = court_x(feet[track], frame, gap)
            if (at is None or at * inward >= -SIDE_M) if team == side else (at is not None and at * inward > CROSS_M):
                found.append((distance((x, y), box, reach), distance((x, y), box), box[1] - box[3], track))
        out.append([(d, plain, track) for d, plain, _, track in sorted(found)])
    return out


def iou(a: Box, b: Box) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def wrist_distance(ball: tuple[float, float], box: Box, poses: list[list[tuple[Box, np.ndarray]]]) -> float | None:
    """Box heights from the ball to the nearest confident wrist of the pose detection matching `box`
    in each of `poses`' frames (box, 17 keypoints x, y, confidence); None when none is seen."""
    found = []
    for frame in poses:
        overlaps = [iou(box, b) for b, _ in frame]
        if overlaps and max(overlaps) >= WRIST_IOU:
            points = frame[int(np.argmax(overlaps))][1][[9, 10]]
            found += [float(np.hypot(px - ball[0], py - ball[1])) for px, py, conf in points if conf >= WRIST_CONF]
    return min(found) / (box[3] - box[1]) if found else None


def court_metres(place: np.ndarray | None, frame: int, found: list[Candidate], feet: dict[int, dict[int, tuple[float, float]]], gap: int) -> dict[int, float]:
    """Each candidate's metres on the court from the ball's `place` (`ball3d.flight_places`) over the
    nearest one's, at most COURT_MAX_M; 0 when the place or a candidate's feet are not known."""
    if place is None:
        return {c[2]: 0.0 for c in found}
    apart = {}
    for c in found:
        at = next((feet[c[2]][f] for d in range(gap + 1) for f in (frame - d, frame + d) if f in feet.get(c[2], {})), None)
        apart[c[2]] = None if at is None else float(np.hypot(at[0] - place[0], at[1] - place[1]))
    nearest = min((d for d in apart.values() if d is not None), default=0.0)
    return {k: 0.0 if d is None else min(d - nearest, COURT_MAX_M) for k, d in apart.items()}


def feet_on_court(rows: list[Row]) -> dict[int, dict[int, tuple[float, float]]]:
    """Track -> frame -> feet on the court."""
    out: dict[int, dict[int, tuple[float, float]]] = {}
    for r in rows:
        out.setdefault(r.track, {})[r.frame] = r.court
    return out


def by_wrists(
    video: Path,
    typed: list[Typed],
    candidates: list[list[Candidate]],
    rows: list[Row],
    fps: float,
    cache: Path | None = None,
    learned: dict | None = None,
    places: dict[int, np.ndarray] | None = None,
) -> list[list[Candidate]]:
    """`candidates` reordered by the wrists for touches below the head (see WRIST_VETO), or, with a
    `learned` ranker (ranker.py), every touch's by its scores, the ball's 3D `places` by frame among
    them; YOLO pose on a crop around the ball, kept in `cache` (JSON, by frame and ball place) for
    the next runs. First ASPOM match: 97 -> 104 of the 135 touches answered."""
    import cv2

    from volleyball_stats import ranker

    by_track, gap = tracks(rows), round(GAP_S * fps)
    feet = feet_on_court(rows) if places else {}
    kept = json.loads(cache.read_text()) if cache and cache.exists() else {}
    model, cap, out = None, None, []
    for (frame, x, y, kind, side), found in zip(typed, candidates):
        if len(found) < 2 or (learned is None and kind not in BELOW_HEAD):
            out.append(found)
            continue
        key = f"{frame}:{x}:{y}"
        if key not in kept:
            if model is None:
                from ultralytics import YOLO

                model, cap = YOLO(str(POSE_MODEL)), cv2.VideoCapture(str(video))
            kept[key] = poses_at(model, cap, frame, x, y)
        poses = [[(tuple(b), np.array(k)) for b, k in f] for f in kept[key]]
        boxes = {c[2]: box_at(by_track[c[2]][1], frame, gap) for c in found}
        wrists = {c[2]: wrist_distance((x, y), boxes[c[2]], poses) for c in found}
        if learned is None:
            out.append(wrist_order(found, wrists))
            continue
        tallest = max(b[3] - b[1] for b in boxes.values())
        metres = court_metres((places or {}).get(frame), frame, found, feet, gap)
        x_ = np.array([
            ranker.features((x, y), kind, c, found[0][0], k, boxes[c[2]], tallest, wrists[c[2]], by_track[c[2]][0] == side, (frame - min(by_track[c[2]][1])) / fps, metres[c[2]])
            for k, c in enumerate(found)
        ])
        out.append([found[k] for k in np.argsort(-ranker.scores(learned, x_), kind="stable")])
    if cap is not None:
        cap.release()
        if cache:
            files.write_text(cache, json.dumps(kept, separators=(",", ":")))
    return out


def poses_at(model, cap, frame: int, x: int, y: int) -> list[list[tuple[list[float], list[list[float]]]]]:
    """YOLO pose on a crop around the ball (`x`, `y`) in frames `frame` - 1 to + 1: each frame's
    boxes and 17 keypoints (x, y, confidence), in the frame's pixels."""
    import cv2

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame - 1)
    poses = []
    for _ in range(3):
        ok, image = cap.read()
        if not ok:
            break
        height, width = image.shape[:2]
        side = min(round(POSE_CROP * height), width, height)
        x0, y0 = min(max(0, x - side // 2), width - side), min(max(0, y - side // 2), height - side)
        result = model.predict(image[y0:y0 + side, x0:x0 + side], imgsz=1280, conf=0.1, verbose=False)[0]
        keypoints = result.keypoints.data.cpu().numpy() + np.array([x0, y0, 0])
        boxes = result.boxes.xyxy.cpu().numpy() + np.array([x0, y0, x0, y0])
        poses.append([(np.round(b, 1).tolist(), np.round(k, 2).tolist()) for b, k in zip(boxes, keypoints)])
    return poses


def wrist_order(found: list[Candidate], wrists: dict[int, float | None]) -> list[Candidate]:
    """`found` (nearest first) with the candidates whose wrists all stand over WRIST_VETO from the
    ball last, and the others within WRIST_MARGIN of the nearest of them by their wrists' distance,
    those with none seen after; unless the ball lies inside that nearest box and its wrists are not
    seen (hands above the head, out of the box)."""
    kept = [c for c in found if wrists[c[2]] is None or wrists[c[2]] <= WRIST_VETO]
    if not kept:
        return found
    close = [c for c in kept if c[0] - kept[0][0] <= WRIST_MARGIN]
    if close[0][0] > 0 or wrists[close[0][2]] is not None:
        close.sort(key=lambda c: (wrists[c[2]] is None, wrists[c[2]] or 0.0, c[0]))
    return close + [c for c in kept if c not in close] + [c for c in found if c not in kept]


def unreached(typed: list[Typed], rows: list[Row], fps: float, crossings: list[int] | None = None) -> set[int]:
    """Frames of the contacts typed as touches with candidates, none within FAR of the ball or with
    the ball at the nearest one's feet; not a serve whose ball then crosses the net (`crossings`
    within LATE_FLIGHT_S), whose server may stand out of the frame."""
    by_track, gap = tracks(rows), round(GAP_S * fps)
    flight = LATE_FLIGHT_S * fps

    def at_feet(t: Typed, track: int) -> bool:
        box = box_at(by_track[track][1], t[0], gap)
        return box is not None and t[2] >= box[1] + FEET * (box[3] - box[1])

    def sent_over(t: Typed) -> bool:
        return t[3] == "serve" and any(t[0] < c <= t[0] + flight for c in crossings or [])

    return {t[0] for t, c in zip(typed, ranked(typed, rows, fps)) if c and not sent_over(t) and (c[0][0] > FAR or at_feet(t, c[0][2]))}


def gap_to_next(candidates: list[Candidate]) -> float | None:
    """Box heights between the toucher's distance to the ball and the next candidate's; None alone."""
    return candidates[1][0] - candidates[0][0] if len(candidates) > 1 else None


def attribute(typed: list[Typed], rows: list[Row], fps: float) -> list[int | None]:
    """The track that touched each contact, None for the floor, the net or no candidate."""
    return [c[0][2] if c else None for c in ranked(typed, rows, fps)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute each typed contact to a player track.")
    parser.add_argument("actions", type=Path, help="frame,x,y,type,side CSV from actions.py")
    parser.add_argument("players", type=Path, help="Player tracks CSV from players.py")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    with open(args.actions) as f:
        typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in csv.DictReader(f)]
    found = attribute(typed, read_players(args.players), args.fps)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.actions.stem.removesuffix('_actions')}_attribution.csv"
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([["frame", "x", "y", "type", "side", "track"], *([*t, "" if k is None else k] for t, k in zip(typed, found))])
    print(f"{sum(k is not None for k in found)}/{len(typed)} contacts attributed -> {path}")


if __name__ == "__main__":
    main()
