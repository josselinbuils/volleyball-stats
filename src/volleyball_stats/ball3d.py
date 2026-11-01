"""The ball's 3D place at each touch, from one camera.

Between two touches the ball flies a gravity arc, so a rally's whole path follows from its touches' places and
times, and its picture is linear in those places once the depth of each sighting is known: least squares over the
ball track, the touches' floor positions and a typical height for each action, solved a few times over.
"""

from pathlib import Path

import numpy as np

from volleyball_stats.court import Calibration, undistort

G = 9.81
# The ball's centre on the floor, its radius.
BALL_R = 0.11
# A ball sighting's spread in 4K pixels, a touch's distance from the feet under it, a height's from its action's.
PIXEL_4K, FEET_M, HEIGHT_M = 6.0, 0.8, 2.0
# A floor contact is seen on the floor; a net contact's height is known roughly.
FLOOR_M, FLOOR_HEIGHT_M, NET_HEIGHT_M = 0.25, 0.03, 0.6
UNKNOWN_M = 50.0
HEIGHTS = {"serve": 2.7, "pass": 0.9, "dig": 0.7, "set": 2.4, "attack": 2.9, "relance": 1.6, "block": 2.6, "net": 2.2, "floor": BALL_R}
OTHER_HEIGHT = 1.5
# A longer flight hides a touch the pipeline missed: its sightings say nothing of its ends.
LONGEST_S = 2.2
# Sightings further than this from the path, in 4K pixels, count for less: the tracker's false balls.
ROBUST_4K = 15.0
ROUNDS = 8
# Past these the fit is wrong: the action's height and the feet stay.
HIGHEST_M, FARTHEST_X, FARTHEST_Y = 6.0, 14.0, 9.0


def projection(calibration: Calibration) -> np.ndarray | None:
    """The 3x4 matrix from court (x, y, -height, 1) to undistorted pixels, from the homography and the lens; without
    a lens, the focal length that makes the court's axes square, the optical axis through the frame's centre. None
    when no camera above the court fits."""
    H = np.asarray(calibration.homography, float)
    if calibration.lens:
        K = np.asarray(calibration.lens["K"], float)
    elif calibration.size:
        cx, cy = calibration.size[0] / 2, calibration.size[1] / 2
        centred = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], float) @ H
        denominator = centred[2, 0] * centred[2, 1]
        squared = -(centred[0, 0] * centred[0, 1] + centred[1, 0] * centred[1, 1]) / denominator if denominator else -1.0
        if squared <= 0:
            return None
        K = np.array([[squared**0.5, 0, cx], [0, squared**0.5, cy], [0, 0, 1]])
    else:
        return None
    A = np.linalg.inv(K) @ H
    A /= (np.linalg.norm(A[:, 0]) + np.linalg.norm(A[:, 1])) / 2
    if A[2, 2] < 0:
        A = -A
    U, _, Vt = np.linalg.svd(np.c_[A[:, 0], A[:, 1], np.cross(A[:, 0], A[:, 1])])
    R = U @ Vt
    if (R.T @ A[:, 2])[2] <= 0:
        return None
    return K @ np.c_[R, A[:, 2]]


def camera_place(P: np.ndarray) -> np.ndarray:
    """Where the camera stands: court x, y and height."""
    x, y, down = -np.linalg.inv(P[:, :3]) @ P[:, 3]
    return np.array([x, y, -down])


def project(P: np.ndarray, places: np.ndarray) -> np.ndarray:
    """Undistorted pixels of court places (x, y, height)."""
    q = np.c_[places[:, 0], places[:, 1], -places[:, 2], np.ones(len(places))] @ P.T
    return q[:, :2] / q[:, 2:3]


def fit_rally(touches: list[dict], sightings: dict[int, np.ndarray], P: np.ndarray, fps: float, width: int = 3840, hidden: frozenset[int] | set[int] = frozenset()) -> tuple[np.ndarray, np.ndarray]:
    """The place (x, y, height) of each of a rally's `touches` in frame order (`f`, `type`, `x`, `y`), from `sightings`
    of the ball (frame to undistorted pixel), and how far each sighting used stays from the path, in pixels. The feet
    of the touches at `hidden` positions are left out, to score the rest."""
    n = len(touches)
    scale = width / 3840
    frames = np.array([t["f"] for t in touches], float)
    prior = np.array([[t["x"] or 0.0, t["y"] or 0.0, HEIGHTS.get(t["type"], OTHER_HEIGHT)] for t in touches], float)
    spans, seen, pixels = [], [], []
    for k in range(n - 1):
        first, last = int(frames[k]), int(frames[k + 1])
        if last > first and (last - first) / fps <= LONGEST_S:
            for frame in range(first + 1, last):
                if frame in sightings:
                    spans.append(k)
                    seen.append(frame)
                    pixels.append(sightings[frame])
    rows, values = [], []
    for k, touch in enumerate(touches):
        feet, high = FEET_M, HEIGHT_M
        if touch["type"] == "floor":
            feet, high = FLOOR_M, FLOOR_HEIGHT_M
        elif touch["type"] == "net":
            high = NET_HEIGHT_M
        if touch["x"] is None or touch["y"] is None or k in hidden:
            feet = UNKNOWN_M
        for axis, spread in enumerate((feet, feet, high)):
            row = np.zeros(3 * n)
            row[3 * k + axis] = 1 / spread
            rows.append(row)
            values.append(prior[k, axis] / spread)
    B, b = np.array(rows), np.array(values)
    if not spans:
        return np.linalg.lstsq(B, b, rcond=None)[0].reshape(-1, 3), np.zeros(0)
    k = np.array(spans)
    f = np.array(seen, float)
    pixel = np.array(pixels, float)
    u = (f - frames[k]) / (frames[k + 1] - frames[k])
    lift = G * ((frames[k + 1] - frames[k]) / fps) ** 2 * u * (1 - u) / 2
    along = np.arange(len(k))

    def path(places: np.ndarray) -> np.ndarray:
        at = (1 - u)[:, None] * places[k] + u[:, None] * places[k + 1]
        at[:, 2] += lift
        return at

    places = prior.copy()
    weight = np.ones(len(k))
    errors = np.zeros(len(k))
    for _ in range(ROUNDS):
        at = path(places)
        depth = np.c_[at[:, 0], at[:, 1], -at[:, 2], np.ones(len(at))] @ P[2]
        scaled = weight / (np.maximum(depth, 1e-6) * PIXEL_4K * scale)
        blocks, targets = [B], [b]
        for axis in (0, 1):
            c = P[axis][None, :] - pixel[:, axis][:, None] * P[2][None, :]
            M = np.zeros((len(k), 3 * n))
            for dim, part in enumerate((c[:, 0], c[:, 1], -c[:, 2])):
                M[along, 3 * k + dim] = part * (1 - u) * scaled
                M[along, 3 * k + 3 + dim] = part * u * scaled
            blocks.append(M)
            targets.append(-(c[:, 3] - c[:, 2] * lift) * scaled)
        places = np.linalg.lstsq(np.vstack(blocks), np.concatenate(targets), rcond=None)[0].reshape(-1, 3)
        errors = np.hypot(*(project(P, path(places)) - pixel).T)
        weight = np.minimum(1.0, ROBUST_4K * scale / np.maximum(errors, 1e-6))
    return places, errors


def read_sightings(path: Path, calibration: Calibration, frames: list[tuple[int, int]]) -> dict[int, np.ndarray]:
    """The ball's undistorted pixel at each frame it is seen within the spans `frames`."""
    if not frames:
        return {}
    wanted = np.zeros(max(last for _, last in frames) + 2, bool)
    for first, last in frames:
        wanted[first : last + 1] = True
    found, pixels = [], []
    with open(path) as f:
        next(f)
        for line in f:
            frame, visible, x, y = line.strip().split(",")
            at = int(frame)
            if visible == "1" and at < len(wanted) and wanted[at]:
                found.append(at)
                pixels.append((float(x), float(y)))
    if not found:
        return {}
    points = np.array(pixels, float)
    undistorted = undistort(points, calibration.lens) if calibration.lens else points
    return dict(zip(found, undistorted))


def touch_places(contacts: list[dict], ball: Path, calibration: Calibration, fps: float) -> list[float]:
    """Each touch's 3D place as flat [index in `contacts`, x, y, height, ...], in metres to the centimetre; none without
    a camera or the ball track. A rally needs two touches."""
    P = projection(calibration)
    if P is None or not ball.exists():
        return []
    by_rally: dict[int, list[tuple[int, dict]]] = {}
    for i, c in enumerate(contacts):
        if c["type"] != "fault" and c.get("f") is not None:
            by_rally.setdefault(c["rally"], []).append((i, c))
    spans = [(min(c["f"] for _, c in cs), max(c["f"] for _, c in cs)) for cs in by_rally.values()]
    sightings = read_sightings(ball, calibration, spans)
    width = calibration.size[0] if calibration.size else 3840
    out: list[float] = []
    for touches in by_rally.values():
        touches = sorted(touches, key=lambda item: item[1]["f"])
        if len(touches) < 2:
            continue
        places, _ = fit_rally([c for _, c in touches], sightings, P, fps, width)
        for (i, c), (x, y, h) in zip(touches, places):
            if h > HIGHEST_M or abs(x) > FARTHEST_X or abs(y) > FARTHEST_Y:
                continue
            h = BALL_R if c["type"] == "floor" else max(BALL_R, h)
            out += [i, round(float(x), 2), round(float(y), 2), round(float(h), 2)]
    return out
