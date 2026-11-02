"""The ball's 3D place at each touch, from one camera.

Between two touches the ball flies a gravity arc, so a rally's whole path follows from its touches' places and
times, and its picture is linear in those places once the depth of each sighting is known: least squares over the
ball track, the touches' floor positions and a typical height for each action, solved a few times over.
"""

from pathlib import Path
from typing import NamedTuple

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
# A serve's speed is read in mid-flight: the contacts' frames are a flight's least sure part and the strike is often
# hidden. `benchmarks/ball3d/measures.py` scores these limits. No radar checked them: one would say how far a mid-flight
# speed stands from a speed at the strike.
SERVE_TRIM_S, SERVE_SHORTEST_S, SERVE_SEEN, SERVE_LEAST_SEEN = 0.2, 0.4, 0.6, 12
SERVE_AWAY_X, SERVE_FARTHEST_Y, SERVE_SHORTEST_M, SERVE_WORST_4K = 3.0, 7.0, 3.0, 12.0
AFTER_SERVE = {"pass", "dig", "relance", "set", "attack", "block"}
# One attack's height swings with its contact's frame: the page only shows a player's median over several.
ATTACK_LOWEST_M, ATTACK_HIGHEST_M, ATTACK_AROUND_S, ATTACK_SEEN = 1.8, 3.8, 0.3, 0.65


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
        wanted[max(first, 0) : last + 1] = True
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


def flight_places(typed: list[tuple], windows: list[tuple[int, int]], lead: int, ball: Path, calibration: Calibration, fps: float) -> dict[int, np.ndarray]:
    """Each contact's 3D place by frame, from the ball's flights alone: no player's feet in it, so
    it can tell who touched the ball; none without a camera, the ball track or a rally of 2 contacts."""
    P = projection(calibration)
    if P is None or not ball.exists():
        return {}
    sightings = read_sightings(ball, calibration, [(start - lead, end) for start, end in windows])
    width = calibration.size[0] if calibration.size else 3840
    out: dict[int, np.ndarray] = {}
    for start, end in windows:
        inside = [t for t in typed if start - lead <= t[0] <= end]
        if len(inside) >= 2:
            touches = [{"f": t[0], "type": t[3], "x": None, "y": None} for t in inside]
            places, _ = fit_rally(touches, sightings, P, fps, width)
            out.update({t[0]: place for t, place in zip(inside, places) if place[2] <= HIGHEST_M and abs(place[0]) <= FARTHEST_X and abs(place[1]) <= FARTHEST_Y})
    return out


class Fitted(NamedTuple):
    """Each rally's touches (index in the contacts, contact) in frame order and their places, with what fitted them."""

    P: np.ndarray | None
    sightings: dict[int, np.ndarray]
    width: int
    rallies: list[tuple[list[tuple[int, dict]], np.ndarray]]


def fit_touches(contacts: list[dict], ball: Path, calibration: Calibration, fps: float) -> Fitted:
    """The rallies of `contacts` fitted; none without a camera or the ball track. A rally needs two touches."""
    P = projection(calibration)
    width = calibration.size[0] if calibration.size else 3840
    if P is None or not ball.exists():
        return Fitted(P, {}, width, [])
    by_rally: dict[int, list[tuple[int, dict]]] = {}
    for i, c in enumerate(contacts):
        if c["type"] != "fault" and c.get("f") is not None:
            by_rally.setdefault(c["rally"], []).append((i, c))
    margin = round(ATTACK_AROUND_S * fps)
    spans = [(min(c["f"] for _, c in cs) - margin, max(c["f"] for _, c in cs) + margin) for cs in by_rally.values()]
    sightings = read_sightings(ball, calibration, spans)
    rallies = []
    for touches in by_rally.values():
        touches = sorted(touches, key=lambda item: item[1]["f"])
        if len(touches) >= 2:
            rallies.append((touches, fit_rally([c for _, c in touches], sightings, P, fps, width)[0]))
    return Fitted(P, sightings, width, rallies)


def touch_places(fitted: Fitted) -> list[float]:
    """Each touch's 3D place as flat [index in the contacts, x, y, height, ...], in metres to the centimetre."""
    out: list[float] = []
    for touches, places in fitted.rallies:
        for (i, c), (x, y, h) in zip(touches, places):
            if h > HIGHEST_M or abs(x) > FARTHEST_X or abs(y) > FARTHEST_Y:
                continue
            h = BALL_R if c["type"] == "floor" else max(BALL_R, h)
            out += [i, round(float(x), 2), round(float(y), 2), round(float(h), 2)]
    return out


def serve_speed(serve: dict, after: dict, sightings: dict[int, np.ndarray], P: np.ndarray, fps: float, width: int = 3840) -> float | None:
    """A serve's mean speed over the middle of its flight to the touch `after`, in km/h; None if that flight is too
    short, too little seen or out of place."""
    trim = round(SERVE_TRIM_S * fps)
    first, last = serve["f"] + trim, after["f"] - trim
    flight = (last - first) / fps
    if after["type"] not in AFTER_SERVE or not SERVE_SHORTEST_S <= flight <= LONGEST_S or serve["x"] is None or after["x"] is None:
        return None
    seen = {f: sightings[f] for f in range(first, last + 1) if f in sightings}
    if len(seen) < max(SERVE_LEAST_SEEN, SERVE_SEEN * (last - first)):
        return None
    # The feet say where the flight starts and ends: the ball has left them by these frames.
    share = trim / (after["f"] - serve["f"])
    dx, dy = after["x"] - serve["x"], after["y"] - serve["y"]
    ends = [
        {"f": first, "type": "flight", "x": serve["x"] + share * dx, "y": serve["y"] + share * dy},
        {"f": last, "type": "flight", "x": after["x"] - share * dx, "y": after["y"] - share * dy},
    ]
    (a, b), errors = fit_rally(ends, seen, P, fps, width)
    far = np.hypot(*(b[:2] - a[:2]))
    if far < SERVE_SHORTEST_M or a[0] * b[0] >= 0 or abs(a[0]) < SERVE_AWAY_X or max(abs(a[1]), abs(b[1])) > SERVE_FARTHEST_Y or np.median(errors) > SERVE_WORST_4K * width / 3840:
        return None
    return float(far / flight * 3.6)


def attack_height(attack: dict, place: np.ndarray, sightings: dict[int, np.ndarray], fps: float) -> float | None:
    """An attack's fitted height (`place`), None if out of reach or its ball little seen around the contact."""
    around = round(ATTACK_AROUND_S * fps)
    seen = sum(f in sightings for f in range(attack["f"] - around, attack["f"] + around + 1))
    return float(place[2]) if ATTACK_LOWEST_M <= place[2] <= ATTACK_HIGHEST_M and seen >= ATTACK_SEEN * (2 * around + 1) else None


def measure(fitted: Fitted, fps: float) -> None:
    """Writes on the contacts each serve's `speed` in km/h and each attack's `reach` in metres, where they hold up."""
    for touches, places in fitted.rallies:
        for k, (_, c) in enumerate(touches):
            if c["type"] == "serve" and k + 1 < len(touches):
                speed = serve_speed(c, touches[k + 1][1], fitted.sightings, fitted.P, fps, fitted.width)
                if speed is not None:
                    c["speed"] = round(speed)
            elif c["type"] == "attack":
                reach = attack_height(c, places[k], fitted.sightings, fps)
                if reach is not None:
                    c["reach"] = round(reach, 2)
