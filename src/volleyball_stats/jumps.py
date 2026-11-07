"""An attacker's jump and run-up: YOLO pose on the attacker around the contact; takeoff and landing where the
lower ankle leaves and finds again the floor it stands on before and after (the lower envelope of its path in
the picture); the run-up from the tracked feet. `benchmarks/jumps` scores it against hand labels."""

import json
from pathlib import Path

import numpy as np

from volleyball_stats import decode, files
from volleyball_stats.ball import default_device
from volleyball_stats.ball3d import project, projection
from volleyball_stats.court import Calibration, undistort

# The frames posed around a contact.
BEFORE_S, AFTER_S = 0.8, 0.8
# The pose crop: a square this many box heights around the attacker.
CROP = 2.0
POSE_IMGSZ, MATCH_IOU, KEYPOINT_CONF = 640, 0.3, 0.3
ANKLES, WRISTS = [15, 16], [9, 10]
# A jump: the lower ankle over LIFT_M within CONTACT_S of the contact; airborne while over FLOOR_M around it, its
# edges where the ankle's rise and fall slow under STOP of their fastest.
LIFT_M, FLOOR_M, CONTACT_S, STOP = 0.15, 0.05, 0.1, 0.2
# The ankle starts rising with the heel, before the toes leave, and stops falling once the heel is down, after the toes
# touch (`benchmarks/jumps`: 3-4 and 2 frames at 50 fps).
HEEL_UP_S, HEEL_DOWN_S = 0.06, 0.04
# Flights outside these are a foot hidden or another player's taken for it (the labelled ones: 0.42-0.72 s).
SHORTEST_S, LONGEST_S = 0.3, 0.8
# The hit: within HIT_S of the ball's contact, the frame the ball is seen nearest a wrist (`benchmarks/jumps`: within 2
# frames of the hand on the ball for 24 attacks of 27, against 20 for the contact).
HIT_S = 0.24
# Holes in the ankles or the track up to this long are bridged.
HOLE_S = 0.1
# The run-up: looked for over RUN_UP_S before takeoff, it starts where the player last came under STILL_M nearer the
# net over PAUSE_S.
RUN_UP_S, PAUSE_S, STILL_M = 2.0, 0.5, 0.1
G = 9.81

Rows = np.ndarray  # one track's rows: frame, x1, y1, x2, y2, court x, court y


def read_tracks(players: Path, tracks: set[int]) -> dict[int, Rows]:
    """players.csv's rows of `tracks`, by track, in frame order."""
    rows = np.loadtxt(players, delimiter=",", skiprows=1, usecols=(0, 1, 3, 4, 5, 6, 10, 11))
    rows = rows[np.isin(rows[:, 1], list(tracks))]
    return {t: np.delete(rows[rows[:, 1] == t], 1, axis=1) for t in tracks}


def read_ball(path: Path, frames: set[int]) -> dict[int, tuple[float, float]]:
    """ball.csv's sightings at `frames`, in the video's pixels."""
    out = {}
    with open(path) as f:
        next(f)
        for line in f:
            frame, visible, x, y = line.rstrip().split(",")
            if visible == "1" and int(frame) in frames:
                out[int(frame)] = (float(x), float(y))
    return out


def window(frame: int, fps: float) -> range:
    return range(frame - round(BEFORE_S * fps), frame + round(AFTER_S * fps) + 1)


def at(rows: Rows, frames: range, hole: int) -> np.ndarray:
    """The track's columns at each frame, interpolated across holes up to `hole` frames, NaN further."""
    out = np.full((len(frames), rows.shape[1] - 1), np.nan)
    if len(rows) == 0:
        return out
    f = np.asarray(frames, float)
    i = np.searchsorted(rows[:, 0], f)
    after, before = rows[np.minimum(i, len(rows) - 1), 0], rows[np.maximum(i - 1, 0), 0]
    ok = (after == f) | ((i > 0) & (i < len(rows)) & (after - before <= hole + 1))
    for k in range(1, rows.shape[1]):
        out[ok, k - 1] = np.interp(f[ok], rows[:, 0], rows[:, k])
    return out


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU of box `a` with each of boxes `b` (xyxy)."""
    w = np.clip(np.minimum(a[2], b[:, 2]) - np.maximum(a[0], b[:, 0]), 0, None)
    h = np.clip(np.minimum(a[3], b[:, 3]) - np.maximum(a[1], b[:, 1]), 0, None)
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter)


def pose_all(video: Path, attacks: list[tuple[int, int]], tracks: dict[int, Rows], fps: float, cache: Path | None = None) -> dict[str, list]:
    """Each attack's (frame, track) keypoints over its `window`: per frame the 17 (x, y, confidence) in the video's pixels
    of the pose matching the track's box, None when none does; kept in `cache` (JSON, by "frame:track")."""
    kept = json.loads(cache.read_text()) if cache and cache.exists() else {}
    todo = [(f, t) for f, t in attacks if f"{f}:{t}" not in kept]
    if not todo:
        return kept
    from ultralytics import YOLO

    from volleyball_stats.actions import POSE_MODEL

    model, device, hole = YOLO(str(POSE_MODEL)), default_device(), round(HOLE_S * fps)
    boxes = {(f, t): at(tracks[t], window(f, fps), hole)[:, :4] for f, t in todo}
    wanted: dict[int, list[tuple[int, int, int]]] = {}
    for (f, t), b in boxes.items():
        for k, frame in enumerate(window(f, fps)):
            if not np.isnan(b[k, 0]):
                wanted.setdefault(frame, []).append((f, t, k))
    out = {f"{f}:{t}": [None] * len(window(f, fps)) for f, t in todo}
    for frame, image in decode.frames_at(video, wanted):
        height, width = image.shape[:2]
        crops, origins, whose = [], [], []
        for f, t, k in wanted[frame]:
            x1, y1, x2, y2 = boxes[(f, t)][k]
            side = min(round(CROP * (y2 - y1)), width, height)
            x0 = int(min(max(0, (x1 + x2) / 2 - side / 2), width - side))
            y0 = int(min(max(0, (y1 + y2) / 2 - side / 2), height - side))
            crops.append(image[y0 : y0 + side, x0 : x0 + side])
            origins.append((x0, y0))
            whose.append((f, t, k))
        for result, (x0, y0), (f, t, k) in zip(model.predict(crops, imgsz=POSE_IMGSZ, conf=0.1, device=device, verbose=False), origins, whose):
            found = result.boxes.xyxy.cpu().numpy() + np.array([x0, y0, x0, y0])
            if len(found) == 0:
                continue
            overlap = iou(boxes[(f, t)][k], found)
            if overlap.max() >= MATCH_IOU:
                points = result.keypoints.data.cpu().numpy()[int(overlap.argmax())] + np.array([x0, y0, 0])
                out[f"{f}:{t}"][k] = np.round(points, 1).tolist()
    kept.update(out)
    if cache:
        files.write_text(cache, json.dumps(kept, separators=(",", ":")))
    return kept


def lower_hull(t: np.ndarray, v: np.ndarray) -> np.ndarray:
    """The lower convex envelope of the points (t, v), sorted by t, at each t."""
    hull: list[int] = []
    for k in range(len(t)):
        while len(hull) >= 2:
            a, b = hull[-2], hull[-1]
            if (t[b] - t[a]) * (v[k] - v[a]) - (v[b] - v[a]) * (t[k] - t[a]) > 0:
                break
            hull.pop()
        hull.append(k)
    return np.interp(t, t[hull], v[hull])


def ankle_path(keypoints: list, calibration: Calibration, hole: int) -> np.ndarray:
    """The lower confident ankle's undistorted picture y at each frame, across holes up to `hole` frames, NaN further."""
    y = np.full(len(keypoints), np.nan)
    for k, points in enumerate(keypoints):
        if points is None:
            continue
        ankles = np.array(points)[ANKLES]
        ankles = ankles[ankles[:, 2] >= KEYPOINT_CONF]
        if len(ankles):
            y[k] = (undistort(ankles[:, :2], calibration.lens) if calibration.lens else ankles[:, :2])[:, 1].max()
    seen = np.flatnonzero(~np.isnan(y))
    return at(np.c_[seen, y[seen]], range(len(y)), hole)[:, 0]


def lift(y: np.ndarray, metres_px: float) -> np.ndarray:
    """The ankle's height in metres over the lower envelope of its path (`ankle_path`): the floor where it stands."""
    seen = np.flatnonzero(~np.isnan(y))
    out = np.full(len(y), np.nan)
    if len(seen) >= 2:
        v = -y[seen]
        out[seen] = (v - lower_hull(seen.astype(float), v)) / metres_px
    return out


def flight(y: np.ndarray, up: np.ndarray, contact: int, fps: float) -> tuple[int, int] | None:
    """The jump around index `contact`: its first airborne index and the first back on the floor, from the ankle's
    path `y` and its `lift`; None without one, or when it runs off the frames seen. The flight is where the ankle
    stands over FLOOR_M; its edges then move to where the ankle's fastest rise and fall start and end (under STOP of
    their speed): past landing, a player moving away from the camera lifts the envelope's floor."""
    over = np.nan_to_num(up, nan=-1.0)
    near = round(CONTACT_S * fps)
    hits = [k for k in range(max(0, contact - near), min(len(y), contact + near + 1)) if over[k] > LIFT_M]
    if not hits:
        return None
    first = after = min(hits, key=lambda k: abs(k - contact))
    while first > 0 and over[first - 1] > FLOOR_M:
        first -= 1
    while after < len(y) and over[after] > FLOOR_M:
        after += 1
    if first == 0 or after >= len(y) or np.isnan(up[first - 1]) or np.isnan(up[after]):
        return None
    top = first + int(np.nanargmax(up[first:after]))
    smooth = np.convolve(y, np.ones(3) / 3, mode="same")
    smooth[[0, -1]] = np.nan
    speed = np.diff(smooth)  # px per frame, + falling
    rise = first - 1 + int(np.nanargmin(speed[first - 1 : top])) if top > first else None
    fall = top + int(np.nanargmax(speed[top:after])) if after > top else None
    if rise is not None:
        k = rise
        while k > 0 and speed[k - 1] < STOP * speed[rise]:
            k -= 1
        first = k + 1
    if fall is not None:
        k = fall
        while k + 1 < len(speed) and speed[k] > STOP * speed[fall]:
            k += 1
        after = k
    return first, after


def run_up(rows: Rows, takeoff: int, fps: float) -> int | None:
    """The frame the run-up to `takeoff` starts: going back from it, where the player had come under STILL_M nearer
    the net over the PAUSE_S before (standing, or backing off); None untracked at takeoff."""
    frames = range(takeoff - round(RUN_UP_S * fps), takeoff)
    distance = np.abs(at(rows, frames, round(HOLE_S * fps))[:, 4])
    if np.isnan(distance[-1]):
        return None
    pause, k = round(PAUSE_S * fps), len(distance) - 1
    while k - pause >= 0 and distance[k - pause] - distance[k] >= STILL_M and not np.isnan(distance[k - 1]):
        k -= 1
    return frames[k]


def hit(frame: int, keypoints: list, ball: dict[int, tuple[float, float]], fps: float) -> int:
    """The frame the attacker hits the ball, `frame` its contact: the ball seen nearest a wrist within HIT_S of it, else
    `frame`."""
    best, nearest = frame, np.inf
    for f, points in zip(window(frame, fps), keypoints):
        if abs(f - frame) > round(HIT_S * fps) or points is None or f not in ball:
            continue
        wrists = np.array(points)[WRISTS]
        wrists = wrists[wrists[:, 2] >= KEYPOINT_CONF]
        if len(wrists) and np.hypot(*(wrists[:, :2] - ball[f]).T).min() < nearest:
            best, nearest = f, np.hypot(*(wrists[:, :2] - ball[f]).T).min()
    return best


def measure(frame: int, rows: Rows, keypoints: list, calibration: Calibration, fps: float, ball: dict[int, tuple[float, float]] | None = None) -> dict | None:
    """One attack's jump: `takeoff` (first frame airborne), `landing` (first back on the floor), `hit` (the frame of
    the hand on the ball, from the `ball`'s sightings), `late` (ms from the flight's top to it, negative before), `height`
    (m, from the flight time), the distances to the net in metres at takeoff (`takeoff_m`), at the run-up's start
    (`start_m`, with its frame `start`) and how far the jump carried towards it (`drift_m`); None without a jump."""
    frames = window(frame, fps)
    hole = round(HOLE_S * fps)
    track = at(rows, frames, hole)
    P = projection(calibration)
    spot = np.nanmedian(track[:, 4:6], axis=0)
    if P is None or np.isnan(spot).any():
        return None
    foot, head = project(P, np.array([[*spot, 0.0], [*spot, 1.0]]))
    y = ankle_path(keypoints, calibration, hole)
    jump = flight(y, lift(y, float(np.linalg.norm(head - foot))), frame - frames[0], fps)
    if jump is None:
        return None
    first, after = jump
    first, after = first + round(HEEL_UP_S * fps), after - round(HEEL_DOWN_S * fps)
    if not SHORTEST_S <= (after - first) / fps <= LONGEST_S:
        return None
    takeoff, landing = frames[first], frames[after]
    near = np.abs(track[:, 4])
    struck = hit(frame, keypoints, ball or {}, fps)
    out = {
        "takeoff": takeoff,
        "landing": landing,
        "hit": struck,
        "late": round((struck - (takeoff + landing - 1) / 2) / fps * 1000),
        "height": round(G * ((landing - takeoff) / fps) ** 2 / 8, 2),
        "takeoff_m": None if np.isnan(near[first - 1]) else round(float(near[first - 1]), 2),
        "drift_m": None if np.isnan(near[first - 1]) or np.isnan(near[after]) else round(float(near[first - 1] - near[after]), 2),
    }
    start = run_up(rows, takeoff, fps)
    if start is not None:
        out["start"] = start
        out["start_m"] = round(float(abs(at(rows, range(start, start + 1), hole)[0, 4])), 2)
    return out
