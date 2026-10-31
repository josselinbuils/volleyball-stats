"""Player detection and tracking on one court.

YOLO11 finds the people of each frame (COCO "person" class) and their feet (box bottom center) are
mapped to court meters with the court calibration. Detections with feet near the court are tracked
with BoT-SORT (no appearance model, no camera motion compensation). Offline, track pieces broken by
an occlusion are joined when a player could have walked the gap, and tracks that are short or stand
off the court (referees, coaches, line judges, spectators, other courts) are dropped. Team is the side of the net a track plays on. See
benchmarks/players/README.md for the numbers behind the constants.

    uv run python -m volleyball_stats.players VIDEO CALIBRATION_JSON [--out DIR] [--overlay]
"""

import argparse
import bisect
import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode
from volleyball_stats.ball import default_device, read_frames
from volleyball_stats.court import LENGTH, WIDTH, Calibration

MODEL = Path("models/yolo11m.pt")
IMGSZ = 1280
# Detections above CONF (best F1 on benchmarks/players) lead and start tracks; the tracker's second
# pass extends tracks with those down to LOW (its default).
CONF, LOW = 0.5, 0.1
TRACKER = "botsort"
# Kept detections, feet in meters beyond the lines: servers stand up to ~3 m behind the end lines,
# players chase the ball past the sidelines.
END_MARGIN, SIDE_MARGIN = 3.0, 2.0
# Kept tracks, median feet beyond the lines: a coach or line judge standing by the court, a ball
# retriever behind it stay out, a player who only runs out for a ball stays in.
TRACK_END_MARGIN, TRACK_SIDE_MARGIN = 1.0, 0.5
# Offline: tracks seen in fewer frames are noise; a track ending and another starting within
# MAX_GAP_S, no farther apart than a player runs (MAX_SPEED m/s, plus REACH for the feet point
# jumping between boxes), are one player.
MIN_FRAMES = 15
MAX_GAP_S = 2.0
MAX_SPEED, REACH = 4.0, 0.5


# ponytail: the offline pass holds every row of the match in memory (~12 per frame, 0.2 KB each:
# ~1 GB for 2 hours at 50 fps); stitch per rally if that is too much.
@dataclass(slots=True)
class Row:
    frame: int
    track: int
    box: tuple[float, float, float, float]
    conf: float
    feet: tuple[float, float]
    court: tuple[float, float]
    team: str = ""


def feet(boxes: np.ndarray) -> np.ndarray:
    """Bottom center of xyxy boxes."""
    return np.c_[(boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]]


def on_court(court: np.ndarray, end: float = END_MARGIN, side: float = SIDE_MARGIN) -> np.ndarray:
    return (np.abs(court[:, 0]) <= LENGTH / 2 + end) & (np.abs(court[:, 1]) <= WIDTH / 2 + side)


def load_model(path: Path = MODEL):
    from ultralytics import YOLO

    path.parent.mkdir(parents=True, exist_ok=True)
    return YOLO(str(path))


def detect(frame: np.ndarray, model, device: str, imgsz: int = IMGSZ, conf: float = CONF) -> np.ndarray:
    """Person boxes, N×5: x1, y1, x2, y2, confidence."""
    result = model.predict(frame, imgsz=imgsz, conf=conf, classes=[0], device=device, verbose=False)[0]
    return result.boxes.data[:, :5].cpu().numpy()


def lapjv(cost: np.ndarray, extend_cost: bool = True, cost_limit: float = np.inf):
    """`lap.lapjv` as ultralytics' trackers call it, on ultralytics' own solver: (cost, row → column,
    column → row), -1 for the unassigned and for pairs above `cost_limit`."""
    from ultralytics.utils.ops import linear_sum_assignment

    rows, cols = linear_sum_assignment(cost)
    ok = cost[rows, cols] <= cost_limit
    x, y = np.full(cost.shape[0], -1), np.full(cost.shape[1], -1)
    x[rows[ok]], y[cols[ok]] = cols[ok], rows[ok]
    return float(cost[rows[ok], cols[ok]].sum()), x, y


def make_tracker(kind: str = TRACKER, conf: float = CONF, **overrides):
    """An ultralytics tracker ("bytetrack" or "botsort") with its defaults, CONF as the high
    threshold and no camera motion compensation (fixed camera)."""
    import sys
    from types import SimpleNamespace

    try:
        import lap  # noqa: F401
    except ImportError:
        # ponytail: ultralytics' trackers need `lap`, not a dependency yet; delete this once it is.
        sys.modules["lap"] = SimpleNamespace(__version__="0", lapjv=lapjv)
    from ultralytics.trackers.track import TRACKER_MAP
    from ultralytics.utils import YAML, IterableSimpleNamespace
    from ultralytics.utils.checks import check_yaml

    config = {**YAML.load(check_yaml(f"{kind}.yaml")), "track_high_thresh": conf, "new_track_thresh": conf, "gmc_method": "none", **overrides}
    return TRACKER_MAP[kind](args=IterableSimpleNamespace(**config))


def track_frames(
    frames: Iterable[np.ndarray], calibration: Calibration, model, device: str, tracker=None, imgsz: int = IMGSZ, size: tuple[int, int] | None = None
) -> Iterator[list[Row]]:
    """Yield, frame by frame, the rows of the on-court detections the tracker (default
    `make_tracker()`) assigned to a track, boxes in the pixels of a frame of `size` (width, height),
    by default the frames' own."""
    from ultralytics.engine.results import Boxes

    online = tracker or make_tracker()
    for index, frame in enumerate(frames):
        boxes = detect(frame, model, device, imgsz, LOW)
        shape = frame.shape[:2]
        if size:
            boxes[:, :4] *= np.array([size[0] / shape[1], size[1] / shape[0]] * 2, np.float32)
            shape = size[1], size[0]
        court = calibration.to_court(feet(boxes)) if len(boxes) else np.empty((0, 2))
        keep = on_court(court)
        boxes, court = boxes[keep], court[keep]
        # The tracker returns a flat empty array on frames without tracks.
        tracks = online.update(Boxes(np.c_[boxes, np.zeros(len(boxes))], shape), frame).reshape(-1, 8)
        rows = []
        for track_id, i in tracks[:, [4, 7]].astype(int).tolist():
            box = tuple(boxes[i, :4].tolist())
            rows.append(Row(index, track_id, box, float(boxes[i, 4]), tuple(feet(boxes[i : i + 1])[0].tolist()), tuple(court[i].tolist())))
        yield rows


def stitch(rows: list[Row], fps: float) -> list[Row]:
    """Join a track ending to one starting within MAX_GAP_S when the feet could have moved that far,
    closest pairs first, each end and start used once."""
    by_track: dict[int, list[Row]] = {}
    for row in sorted(rows, key=lambda r: r.frame):
        by_track.setdefault(row.track, []).append(row)
    # Each end looks at the tracks starting within MAX_GAP_S after it, by bisection on the starts.
    starts = sorted((track_rows[0].frame, b) for b, track_rows in by_track.items())
    first_frames = [f for f, _ in starts]
    pairs = []
    for a, first in by_track.items():
        end = first[-1].frame
        for start, b in starts[bisect.bisect_right(first_frames, end) : bisect.bisect_right(first_frames, end + MAX_GAP_S * fps)]:
            gap = start - end
            distance = float(np.hypot(*np.subtract(first[-1].court, by_track[b][0].court)))
            if distance <= MAX_SPEED * gap / fps + REACH:
                pairs.append((distance, a, b))
    # Closest pairs first, each end and start used once.
    after, before = {}, {}
    for _, a, b in sorted(pairs):
        if a not in after and b not in before:
            after[a], before[b] = b, a
    rename = {}
    for track in by_track:
        if track not in before:
            link = track
            while link is not None:
                rename[link] = track
                link = after.get(link)
    return [Row(r.frame, rename[r.track], r.box, r.conf, r.feet, r.court) for r in rows]


def finish(rows: list[Row], fps: float) -> list[Row]:
    """Offline pass: stitch, drop short tracks and those standing off the court, name each track's
    team by its median side of the net."""
    rows = stitch(rows, fps)
    by_track: dict[int, list[Row]] = {}
    for row in rows:
        by_track.setdefault(row.track, []).append(row)
    out = []
    for track_rows in by_track.values():
        median = np.median([r.court for r in track_rows], axis=0)
        if len(track_rows) >= MIN_FRAMES and on_court(median[None], TRACK_END_MARGIN, TRACK_SIDE_MARGIN)[0]:
            team = "left" if median[0] < 0 else "right"
            out += [Row(r.frame, r.track, r.box, r.conf, r.feet, r.court, team) for r in track_rows]
    return sorted(out, key=lambda r: (r.frame, r.track))


def track(video: Path, calibration: Calibration) -> list[Row]:
    """The players' tracks of a video, offline pass done, sorted by frame then track."""
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    frames = track_frames(decode.frames(video), calibration, load_model(), default_device(), size=decode.size(video))
    return finish([row for rows in frames for row in rows], fps)


def write_csv(rows: list[Row], path: Path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "track", "team", "x1", "y1", "x2", "y2", "conf", "feet_x", "feet_y", "court_x", "court_y"])
        for r in rows:
            writer.writerow([r.frame, r.track, r.team, *(round(v, 1) for v in r.box), round(r.conf, 3), *(round(v, 1) for v in r.feet), *(round(v, 2) for v in r.court)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect and track the players of a fixed-camera volleyball video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("calibration", type=Path, help="Court calibration JSON (volleyball_stats.court)")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--overlay", action="store_true", help="Also write a video with the tracks drawn")
    args = parser.parse_args()

    calibration = Calibration.load(args.calibration)
    try:
        calibration.check(decode.size(args.video))
    except ValueError as error:
        parser.error(str(error))
    rows = track(args.video, calibration)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.out / f"{args.video.stem}_players.csv")
    if args.overlay:
        by_frame: dict[int, list[Row]] = {}
        for r in rows:
            by_frame.setdefault(r.frame, []).append(r)
        fps = cv2.VideoCapture(str(args.video)).get(cv2.CAP_PROP_FPS)
        writer = None
        for index, frame in enumerate(read_frames(args.video)):
            if writer is None:
                path = str(args.out / f"{args.video.stem}_players.mp4")
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame.shape[1], frame.shape[0]))
            for r in by_frame.get(index, []):
                colour = (255, 255, 255) if r.team == "left" else (255, 128, 0)
                cv2.rectangle(frame, tuple(map(round, r.box[:2])), tuple(map(round, r.box[2:])), colour, 1)
                cv2.putText(frame, str(r.track), (round(r.box[0]), round(r.box[1]) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)
            writer.write(frame)
        writer.release()


if __name__ == "__main__":
    main()
