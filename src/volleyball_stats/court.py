"""Court calibration: image pixels to court coordinates in meters and back.

Court frame, in meters on the floor: origin at the center of the court under the net, x along the
length (net at x = 0, end lines at x = ±9, positive to the right as seen from the camera), y across
the width (sidelines at y = ±4.5, positive toward the camera, so far sideline y = -4.5). The
landmarks are the painted line intersections, taken at the line centers (lines are 5 cm wide, so
the model is off by up to 2.5 cm), plus the net post bases.

A court is calibrated once from rough clicks, snapped to the painted lines of the video's median
frame (players removed) and stored by name; later videos of the same court find it on their own.

    uv run python -m volleyball_stats.court click VIDEO [--out CLICKS_JSON]
    uv run python -m volleyball_stats.court fit CLICKS_JSON VIDEO [--lens LENS_JSON] [--court NAME | --out PATH]
    uv run python -m volleyball_stats.court auto VIDEO [--courts DIR] [--out PATH]
    uv run python -m volleyball_stats.court grid VIDEO [--frame N] [--crop X,Y,W,H] [--scale S]

CLICKS_JSON maps landmark names to image pixels: {"corner_left_far": [x, y], ...}. LENS_JSON holds
OpenCV intrinsics for the video resolution: {"model": "fisheye" | "standard", "K": 3x3, "D": [...]}.
"""
# ponytail: the DJI Osmo Action 3 at its widest field of view has strong barrel distortion and no
# LENS_JSON yet: calibrate it once with a checkerboard (cv2.fisheye, settings locked) before fitting
# a match. Without it the homography is only as good as the benchmark's side_club numbers.

import argparse
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

LENGTH, WIDTH, ATTACK = 18.0, 9.0, 3.0
# FIVB: 0.5-1 m outside the sidelines; measure the gym's.
POST = 0.75
LANDMARKS: dict[str, tuple[float, float]] = {
    "corner_left_far": (-LENGTH / 2, -WIDTH / 2),
    "attack_left_far": (-ATTACK, -WIDTH / 2),
    "center_far": (0.0, -WIDTH / 2),
    "attack_right_far": (ATTACK, -WIDTH / 2),
    "corner_right_far": (LENGTH / 2, -WIDTH / 2),
    "corner_left_near": (-LENGTH / 2, WIDTH / 2),
    "attack_left_near": (-ATTACK, WIDTH / 2),
    "center_near": (0.0, WIDTH / 2),
    "attack_right_near": (ATTACK, WIDTH / 2),
    "corner_right_near": (LENGTH / 2, WIDTH / 2),
    "post_far": (0.0, -WIDTH / 2 - POST),
    "post_near": (0.0, WIDTH / 2 + POST),
}
# Painted lines as the landmarks along them, in order.
LINES = (
    ("corner_left_far", "attack_left_far", "center_far", "attack_right_far", "corner_right_far"),
    ("corner_left_near", "attack_left_near", "center_near", "attack_right_near", "corner_right_near"),
    ("corner_left_far", "corner_left_near"),
    ("attack_left_far", "attack_left_near"),
    ("center_far", "center_near"),
    ("attack_right_far", "attack_right_near"),
    ("corner_right_far", "corner_right_near"),
)
# ponytail: a camera aligned with the net sees the center line edge-on behind the near post, whose
# padding edges then pass for it: center_* keep their clicks. Snap them for other camera placements.
UNSNAPPED = {"center_far", "center_near", "post_far", "post_near"}
# RANSAC inlier threshold: snapped or hand-read landmarks are within a few pixels.
RANSAC_PX = 10.0
COURTS = Path("outputs/courts")
BACKGROUND_FRAMES = 25
# Pixel values are for 720p and scale with the frame height.
# Search half-width around the guess, then around the line found: clicks are within ±20 px.
BANDS = (30, 8)
# Lines are traced this far from the guess: straight fits stay close to curved lines without a lens model.
WINDOW = 150
# A line pixel's contrast in the lines' colour, grey levels.
LINE_MIN = 8.0
INLIER_PX = 1.5
SAMPLES = 400
# Share of a window's samples in the frame that must lie on the line.
MIN_SHARE = 0.25
# Largest angle between a line found and its projection through the guesses' homography.
MAX_ANGLE = 10.0
# A second parallel line in the first band with this share of the best one's samples makes the
# window ambiguous: the click is kept rather than snapped to the wrong line.
AMBIGUOUS = 0.5
# Line samples kept per stored court, and how far `match` slides (px) and turns (degrees, 1° steps)
# them to follow a nudged camera.
TEMPLATE = 1000
SEARCH = 90
ROLL = 3
# A stored court matches a new frame when its line samples land on the frame's lines (±2 px) and
# most of its refined landmarks are found again. Set on benchmarks/court.
MATCH_FOUND = 0.6
MATCH_LANDMARKS = 0.75

Lens = dict
Points = dict[str, tuple[float, float]]


def zone(x: float, y: float) -> int:
    """Volleyball zone of (x, y) in its half, seen from that half's end line: front row 4-3-2 and
    back row 5-6-1 from left to right. A point off the court takes the nearest zone."""
    # Thirds of the width from the far sideline: the left half's players face the net, their
    # left hand toward the far sideline; the right half's toward the near one.
    third = min(2, max(0, int((y + WIDTH / 2) // (WIDTH / 3))))
    if x > 0:
        third = 2 - third
    return (4, 3, 2)[third] if abs(x) < ATTACK else (5, 6, 1)[third]


def undistort(points: np.ndarray, lens: Lens) -> np.ndarray:
    """Distorted pixels to pinhole pixels of the same intrinsics."""
    k, d = np.array(lens["K"], float), np.array(lens["D"], float)
    src = np.asarray(points, float).reshape(-1, 1, 2)
    if lens["model"] == "fisheye":
        return cv2.fisheye.undistortPoints(src, k, d, P=k).reshape(-1, 2)
    return cv2.undistortPoints(src, k, d, P=k).reshape(-1, 2)


def distort(points: np.ndarray, lens: Lens) -> np.ndarray:
    """Pinhole pixels back to the distorted image."""
    k, d = np.array(lens["K"], float), np.array(lens["D"], float)
    normalized = (np.asarray(points, float).reshape(-1, 2) - k[:2, 2]) / np.diag(k)[:2]
    if lens["model"] == "fisheye":
        return cv2.fisheye.distortPoints(normalized.reshape(-1, 1, 2), k, d).reshape(-1, 2)
    rays = np.c_[normalized, np.ones(len(normalized))]
    return cv2.projectPoints(rays, np.zeros(3), np.zeros(3), k, d)[0].reshape(-1, 2)


def apply_homography(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = cv2.convertPointsToHomogeneous(np.asarray(points, float).reshape(-1, 2)).reshape(-1, 3) @ h.T
    return homogeneous[:, :2] / homogeneous[:, 2:]


@dataclass
class Calibration:
    """`homography` maps court meters to undistorted pixels; `error` is the fit's RMS residual in px.

    A calibration made from a video also keeps how it was made, for `match`: the rough clicks, the
    refined landmarks, the lines' unit BGR contrast, image points on the lines found, and the frame
    size.
    """

    homography: np.ndarray
    lens: Lens | None = None
    error: float = 0.0
    clicks: dict[str, list[float]] = field(default_factory=dict)
    points: dict[str, list[float]] = field(default_factory=dict)
    colour: list[float] | None = None
    template: list[list[float]] = field(default_factory=list)
    size: list[int] | None = None

    def to_image(self, points: np.ndarray) -> np.ndarray:
        pixels = apply_homography(self.homography, points)
        return distort(pixels, self.lens) if self.lens else pixels

    def to_court(self, points: np.ndarray) -> np.ndarray:
        pixels = undistort(points, self.lens) if self.lens else np.asarray(points, float).reshape(-1, 2)
        return apply_homography(np.linalg.inv(self.homography), pixels)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**vars(self), "homography": self.homography.tolist()}, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        data = json.loads(path.read_text())
        return cls(**{**data, "homography": np.array(data["homography"])})


def fit(image_points: Points, lens: Lens | None = None, ransac: bool = True) -> Calibration:
    """Homography from named landmarks located in the image, RANSAC over the named points unless
    `ransac` is False (least squares, for rough clicks)."""
    unknown = set(image_points) - set(LANDMARKS)
    if unknown:
        raise ValueError(f"Unknown landmarks: {sorted(unknown)}")
    if len(image_points) < 4:
        raise ValueError("At least 4 landmarks are needed")
    court = np.array([LANDMARKS[name] for name in image_points])
    image = np.array(list(image_points.values()), float)
    if lens:
        image = undistort(image, lens)
    homography, _ = cv2.findHomography(court, image, cv2.RANSAC if ransac else 0, RANSAC_PX)
    if homography is None:
        raise ValueError("No homography fits the landmarks")
    error = float(np.sqrt(np.mean(np.sum((apply_homography(homography, court) - image) ** 2, axis=1))))
    return Calibration(homography, lens, error)


def background(video: Path, frames: int = BACKGROUND_FRAMES) -> np.ndarray:
    """Median of frames spread over the video: players and the ball vanish, a fixed camera's court stays."""
    cap = cv2.VideoCapture(str(video))
    stack = []
    for index in np.linspace(0, cap.get(cv2.CAP_PROP_FRAME_COUNT) - 2, frames).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = cap.read()
        if ok:
            stack.append(frame)
    cap.release()
    if not stack:
        raise ValueError(f"Cannot read {video}")
    return np.median(np.stack(stack), axis=0).astype(np.uint8)


def contrast(image: np.ndarray) -> np.ndarray:
    """Each pixel's colour minus its neighbourhood median: thin lines of any colour stand out, the
    floor and wide shapes (glare, aprons, shadows) cancel, edges between two areas mostly too."""
    size = int(image.shape[0] / 48) | 1
    return image.astype(np.float32) - cv2.medianBlur(image, size).astype(np.float32)


def line_response(diff: np.ndarray, colour) -> np.ndarray:
    """Contrast (from `contrast`) along the lines' BGR colour, floored at 0."""
    unit = np.asarray(colour, np.float32) / np.linalg.norm(colour)
    return np.ascontiguousarray(np.maximum(diff @ unit, 0))


def trace(response: np.ndarray, path: np.ndarray, band: int) -> np.ndarray:
    """Position of the strongest `response` along the normal of `path` (N×2 image points) within
    ±band px of each point: the centroid of the run above half its peak, unbiased for any line
    width. NaN where weaker than LINE_MIN."""
    tangent = np.gradient(path, axis=0)
    normal = np.c_[-tangent[:, 1], tangent[:, 0]] / np.linalg.norm(tangent, axis=1, keepdims=True)
    offsets = np.arange(-band, band + 1, dtype=np.float32)
    xy = (path[:, None, :] + offsets[None, :, None] * normal[:, None, :]).astype(np.float32)
    profile = cv2.remap(response, xy[..., 0], xy[..., 1], cv2.INTER_LINEAR, borderValue=0)
    peak, index = profile.argmax(axis=1)[:, None], np.arange(len(offsets))
    below = profile < 0.5 * profile.max(axis=1, keepdims=True)
    right = np.where(below & (index > peak), index, len(offsets)).min(axis=1, keepdims=True)
    left = np.where(below & (index < peak), index, -1).max(axis=1, keepdims=True)
    weights = np.where((index > left) & (index < right), profile, 0)
    shift = (weights * offsets).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-6)
    found = path + shift[:, None] * normal
    found[profile.max(axis=1) < LINE_MIN] = np.nan
    return found


def fit_line(points: np.ndarray, tolerance: float, rng: np.random.Generator, expected: np.ndarray):
    """Robust straight line through points (N×2, NaN rows ignored) within MAX_ANGLE of the unit
    direction `expected`: (point, direction, inlier mask), or None."""
    valid = np.flatnonzero(~np.isnan(points[:, 0]))
    if len(valid) < 2:
        return None
    cos = np.cos(np.radians(MAX_ANGLE))
    best = np.zeros(len(points), bool)
    for _ in range(100):
        p, q = points[rng.choice(valid, 2, replace=False)]
        d = q - p
        if not d.any() or abs(d @ expected) < cos * np.linalg.norm(d):
            continue
        inliers = np.abs((points - p) @ (np.array([-d[1], d[0]]) / np.linalg.norm(d))) < tolerance
        if inliers.sum() > best.sum():
            best = inliers
    if best.sum() < 2:
        return None
    vx, vy, x0, y0 = cv2.fitLine(points[best].astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    return np.array([x0, y0]), np.array([vx, vy]), best


def windows(name: str) -> list[np.ndarray]:
    """Court samples of the lines through a landmark, out to the neighbouring landmarks."""
    out = []
    for line in LINES:
        if name in line:
            i = line.index(name)
            ends = LANDMARKS[line[max(i - 1, 0)]], LANDMARKS[line[min(i + 1, len(line) - 1)]]
            out.append(np.linspace(*ends, SAMPLES))
    return out


def snap_line(response: np.ndarray, path: np.ndarray, lens: Lens | None, scale: float, rng: np.random.Generator):
    """Straight fit to the painted line near `path`, traced within the first band, then within the
    second around the first fit: (point, direction, image points on the line); the line is in
    undistorted pixels with a lens."""
    flat = (lambda p: undistort(p, lens)) if lens else (lambda p: p)
    expected = flat(path[[0, -1]])
    expected = (expected[1] - expected[0]) / np.linalg.norm(expected[1] - expected[0])
    line = None
    for band in BANDS:
        if line:
            p, d = line[:2]
            onto = p + ((flat(path) - p) @ d)[:, None] * d
            path = distort(onto, lens) if lens else onto
        image_points = trace(response, path, round(band * scale))
        traced = image_points.copy()
        ok = ~np.isnan(traced[:, 0])
        traced[ok] = flat(traced[ok])
        first = line is None
        line = fit_line(traced, INLIER_PX * scale, rng, expected)
        if line is None:
            return None
        if first:
            traced[line[2]] = np.nan
            other = fit_line(traced, INLIER_PX * scale, rng, expected)
            if other and other[2].sum() >= AMBIGUOUS * line[2].sum():
                return None
    p, d, inliers = line
    return (p, d, image_points[inliers]) if inliers.sum() >= MIN_SHARE * len(path) else None


def refine(image: np.ndarray, guesses: Points, lens: Lens | None = None, colour=None) -> tuple[Points, np.ndarray, np.ndarray]:
    """Snap rough landmark guesses to the painted lines of `image`.

    Each line landmark becomes the intersection of straight fits to its two lines, traced within
    WINDOW px of the guess along the court lines projected through the guesses' homography and
    shifted onto the guess. The lines are told apart from the floor's other lines by their colour,
    learnt near the guesses unless given. Returns the refined landmarks (those whose two lines were
    found), the lines' unit BGR contrast and the image points found on the lines.
    """
    scale = image.shape[0] / 720
    height, width = image.shape[:2]
    diff = contrast(image)
    rng = np.random.default_rng(0)
    calibration = fit(guesses, lens, ransac=False)
    paths = {}
    for name, guess in guesses.items():
        if name in UNSNAPPED:
            continue
        shift = np.array(guess) - calibration.to_image(np.array([LANDMARKS[name]]))[0]
        two = []
        for court in windows(name):
            path = calibration.to_image(court) + shift
            path = path[np.linalg.norm(path - guess, axis=1) <= WINDOW * scale]
            two.append(path[(path[:, 0] >= 0) & (path[:, 0] < width) & (path[:, 1] >= 0) & (path[:, 1] < height)])
        if len(two) == 2 and min(map(len, two)) >= 2:
            paths[name] = two

    def support(response: np.ndarray) -> int:
        """Samples on straight lines along the expected directions."""
        total = 0
        for path in (p for two in paths.values() for p in two):
            expected = (path[-1] - path[0]) / np.linalg.norm(path[-1] - path[0])
            line = fit_line(trace(response, path, round(BANDS[0] * scale)), INLIER_PX * scale, rng, expected)
            total += line[2].sum() if line else 0
        return total

    if colour is None:
        # The floor's other lines (other sports, wood grain) also peak near the guesses: group the
        # peaks by colour and keep the colour whose lines run along the court.
        strength = np.linalg.norm(diff, axis=2)
        peaks = np.concatenate([trace(strength, p, round(BANDS[0] * scale)) for two in paths.values() for p in two])
        peaks = peaks[~np.isnan(peaks[:, 0])].astype(np.float32)
        colours = cv2.remap(diff, peaks[:, :1], peaks[:, 1:], cv2.INTER_LINEAR)[:, 0]
        units = colours / np.linalg.norm(colours, axis=1, keepdims=True)
        cv2.setRNGSeed(0)
        _, labels, _ = cv2.kmeans(units, 3, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.01), 3, cv2.KMEANS_PP_CENTERS)
        groups = [np.median(colours[labels.ravel() == k], axis=0) for k in range(3) if np.any(labels == k)]
        colour = max(groups, key=lambda c: support(line_response(diff, c)))
    colour = np.asarray(colour, np.float32) / np.linalg.norm(colour)
    response = line_response(diff, colour)

    refined, on_lines = {}, [np.empty((0, 2))]
    for name, two in paths.items():
        lines = [snap_line(response, path, lens, scale, rng) for path in two]
        on_lines += [line[2] for line in lines if line]
        if all(lines):
            (p, d), (q, e) = [line[:2] for line in lines]
            point = p + np.linalg.solve(np.c_[d, -e], q - p)[0] * d
            point = distort(point, lens)[0] if lens else point
            if np.linalg.norm(point - guesses[name]) <= BANDS[0] * scale:
                refined[name] = (float(point[0]), float(point[1]))
    return refined, colour, np.concatenate(on_lines)


def calibrate(image: np.ndarray, clicks: Points, lens: Lens | None = None, colour=None) -> Calibration:
    """Refine rough clicks on `image` and fit the court: on the snapped landmarks alone when there are
    4, else by least squares on them and the other clicks (RANSAC picks bad subsets of ±20 px
    clicks). The calibration keeps both."""
    points, colour, on_lines = refine(image, clicks, lens, colour)
    calibration = fit(points, lens) if len(points) >= 4 else fit({**clicks, **points}, lens, ransac=False)
    calibration.clicks = {n: [float(v) for v in p] for n, p in clicks.items()}
    calibration.points = {n: list(p) for n, p in points.items()}
    calibration.colour = colour.tolist()
    step = max(1, len(on_lines) // TEMPLATE)
    calibration.template = np.round(on_lines[::step], 1).tolist()
    calibration.size = [image.shape[1], image.shape[0]]
    return calibration


def match(image: np.ndarray, court: Calibration) -> tuple[Calibration | None, float, bool]:
    """Find a stored court on a frame of a new video, the camera possibly nudged.

    The court's line samples turn (±ROLL°) and slide (±SEARCH px) over the frame's lines to where
    most land on a line; its landmarks, moved alike, are refined, and those that do not snap follow
    the similarity fitted on those that do. Returns the new calibration, the share of line samples
    found, and whether the court matches (MATCH_*).
    """
    height, width = image.shape[:2]
    if court.size != [width, height] or not court.template:
        return None, 0.0, False
    scale = height / 720
    near = cv2.dilate((line_response(contrast(image), court.colour) >= LINE_MIN).astype(np.uint8), np.ones((5, 5), np.uint8))
    steps = np.arange(-SEARCH, SEARCH + 1, 3) * scale
    shifts = np.stack(np.meshgrid(steps, steps), axis=-1).reshape(-1, 2)
    centre = np.array([width, height]) / 2
    found, turn, shift = -1.0, None, None
    # ponytail: an exhaustive grid, about 0.5 s at 720p; coarse-to-fine if the ranges grow.
    for angle in np.radians(np.arange(-ROLL, ROLL + 1)):
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        turned = (np.array(court.template) - centre) @ rotation.T + centre
        xy = np.round(turned[None] + shifts[:, None]).astype(int)
        inside = (xy[..., 0] >= 0) & (xy[..., 0] < width) & (xy[..., 1] >= 0) & (xy[..., 1] < height)
        share = (inside & (near[xy[..., 1].clip(0, height - 1), xy[..., 0].clip(0, width - 1)] > 0)).mean(axis=1)
        if share.max() > found:
            found, turn, shift = float(share.max()), rotation, shifts[share.argmax()]
    stored = {n: np.array(p, float) for n, p in {**court.clicks, **court.points}.items()}
    seeds = {n: tuple((p - centre) @ turn.T + centre + shift) for n, p in stored.items()}
    points, _, _ = refine(image, seeds, court.lens, court.colour)
    common = [n for n in points if n in court.points]
    if len(common) >= 2:
        moved, _ = cv2.estimateAffinePartial2D(np.float32([court.points[n] for n in common]), np.float32([points[n] for n in common]))
        if moved is not None:
            seeds = {n: tuple(moved @ [*p, 1.0]) for n, p in stored.items()}
    calibration = calibrate(image, seeds, court.lens, court.colour)
    accepted = found >= MATCH_FOUND and len(calibration.points) >= max(1, MATCH_LANDMARKS * len(court.points))
    return calibration, found, accepted


class Clicks:
    """Landmarks named one by one: a click places the current one, skip and undo move along."""

    def __init__(self, names: list[str] = list(LANDMARKS)):
        self.names, self.points, self.index = names, {}, 0

    @property
    def current(self) -> str | None:
        return self.names[self.index] if self.index < len(self.names) else None

    def click(self, x: float, y: float) -> None:
        if self.current:
            self.points[self.current] = (x, y)
            self.index += 1

    def skip(self) -> None:
        self.index = min(self.index + 1, len(self.names))

    def undo(self) -> None:
        if self.index:
            self.index -= 1
            self.points.pop(self.names[self.index], None)


def magnifier(image: np.ndarray, center: tuple[float, float], radius: int = 25, zoom: int = 5) -> np.ndarray:
    """Zoomed view of `image` around `center`, with a cross through the center pixel."""
    height, width = image.shape[:2]
    x, y = min(max(round(center[0]), 0), width - 1), min(max(round(center[1]), 0), height - 1)
    padded = cv2.copyMakeBorder(image, radius, radius, radius, radius, cv2.BORDER_CONSTANT)
    patch = padded[y : y + 2 * radius + 1, x : x + 2 * radius + 1]
    inset = cv2.resize(patch, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    middle = radius * zoom + zoom // 2
    cv2.line(inset, (middle, 0), (middle, inset.shape[0]), (0, 0, 255), 1)
    cv2.line(inset, (0, middle), (inset.shape[1], middle), (0, 0, 255), 1)
    return inset


def draw_clicks(image: np.ndarray, clicks: Clicks, scale: float) -> np.ndarray:
    """The frame with the placed landmarks, the one to click and where it is on a court sketch."""
    out = image.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    for name, (x, y) in clicks.points.items():
        p = round(x * scale), round(y * scale)
        cv2.drawMarker(out, p, (0, 255, 0), cv2.MARKER_CROSS, 14, 1)
        cv2.putText(out, name, (p[0] + 6, p[1] - 6), font, 0.4, (0, 255, 0), 1)

    def sketch(x: float, y: float) -> tuple[int, int]:
        return round(20 + (x + 10.5) * 10), round(40 + (y + 6) * 10)

    cv2.rectangle(out, (10, 30), (240, 170), (0, 0, 0), -1)
    for line in LINES:
        cv2.line(out, sketch(*LANDMARKS[line[0]]), sketch(*LANDMARKS[line[-1]]), (255, 255, 255), 1)
    cv2.line(out, sketch(*LANDMARKS["post_far"]), sketch(*LANDMARKS["post_near"]), (128, 128, 128), 1)
    if clicks.current:
        cv2.circle(out, sketch(*LANDMARKS[clicks.current]), 5, (0, 0, 255), -1)
        text = f"click {clicks.current}   s: skip (hidden)   u: undo   Enter: save"
    else:
        text = "all named   u: undo   Enter: save"
    cv2.putText(out, text, (10, 20), font, 0.55, (0, 0, 255), 2)
    return out


def click_landmarks(image: np.ndarray) -> Points:
    """Let the user click the landmarks in a window with a cross cursor and a zoomed view following
    it, cut from the full-resolution frame; Enter, q or Esc ends.

    Tk rather than an OpenCV window: OpenCV's macOS window cannot change the cursor and reports
    clicks offset from the arrow's tip.
    """
    import tkinter

    root = tkinter.Tk()
    root.title("court")
    height, width = image.shape[:2]
    scale = min(1.0, (root.winfo_screenwidth() - 100) / width, (root.winfo_screenheight() - 150) / height)
    shown = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    canvas = tkinter.Canvas(root, width=shown.shape[1], height=shown.shape[0], cursor="crosshair", highlightthickness=0)
    canvas.pack()
    frame_item = canvas.create_image(0, 0, anchor="nw")
    zoom_item = canvas.create_image(0, 0, anchor="nw")
    # Tk only shows the images Python still references.
    photos: dict[int, tkinter.PhotoImage] = {}
    clicks = Clicks()

    def show(item: int, array: np.ndarray) -> None:
        png = cv2.imencode(".png", array, [cv2.IMWRITE_PNG_COMPRESSION, 0])[1]
        photos[item] = tkinter.PhotoImage(data=base64.b64encode(png.tobytes()).decode())
        canvas.itemconfigure(item, image=photos[item])

    def redraw() -> None:
        show(frame_item, draw_clicks(shown, clicks, scale))

    def on_motion(event: tkinter.Event) -> None:
        inset = magnifier(image, (event.x / scale, event.y / scale))
        size = inset.shape[0]
        # Beside the cursor, flipped near the right and bottom edges so it never hides the target.
        x = event.x + 30 if event.x + 30 + size < shown.shape[1] else event.x - 30 - size
        y = event.y + 30 if event.y + 30 + size < shown.shape[0] else event.y - 30 - size
        canvas.coords(zoom_item, x, y)
        show(zoom_item, inset)

    def on_click(event: tkinter.Event) -> None:
        clicks.click(event.x / scale, event.y / scale)
        redraw()

    def on_key(action) -> None:
        action()
        redraw()

    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Button-1>", on_click)
    root.bind("s", lambda _: on_key(clicks.skip))
    root.bind("u", lambda _: on_key(clicks.undo))
    for key in ("<Return>", "<Escape>", "q"):
        root.bind(key, lambda _: root.destroy())
    redraw()
    root.mainloop()
    return clicks.points


def read_frame(video: Path, index: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"Cannot read frame {index} of {video}")
    return frame


def draw_grid(frame: np.ndarray, origin: tuple[int, int] = (0, 0), scale: int = 1, step: int = 50) -> np.ndarray:
    """Enlarge `frame` and draw pixel lines every `step` source pixels, labelled in source pixels."""
    out = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    height, width = frame.shape[:2]
    for x in range(-origin[0] % step, width, step):
        cv2.line(out, (x * scale, 0), (x * scale, height * scale), (0, 255, 255), 1)
        cv2.putText(out, str(x + origin[0]), (x * scale + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    for y in range(-origin[1] % step, height, step):
        cv2.line(out, (0, y * scale), (width * scale, y * scale), (0, 255, 255), 1)
        cv2.putText(out, str(y + origin[1]), (2, y * scale - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate the court of a fixed-camera video.")
    sub = parser.add_subparsers(dest="command", required=True)
    click_parser = sub.add_parser("click", help="Click rough landmark positions on the video's median frame")
    click_parser.add_argument("video", type=Path)
    click_parser.add_argument("--out", type=Path, help="Defaults to outputs/court/VIDEO_clicks.json")
    fit_parser = sub.add_parser("fit", help="Refine the clicks on the video, fit and store the court")
    fit_parser.add_argument("clicks", type=Path)
    fit_parser.add_argument("video", type=Path)
    fit_parser.add_argument("--lens", type=Path)
    fit_parser.add_argument("--court", help="Name in the court library, defaults to the video name")
    fit_parser.add_argument("--courts", type=Path, default=COURTS)
    fit_parser.add_argument("--out", type=Path, help="Instead of the court library")
    auto_parser = sub.add_parser("auto", help="Calibrate a video from the stored courts")
    auto_parser.add_argument("video", type=Path)
    auto_parser.add_argument("--courts", type=Path, default=COURTS)
    auto_parser.add_argument("--out", type=Path, help="Defaults to outputs/court/VIDEO.json")
    grid_parser = sub.add_parser("grid", help="Write a frame with a labelled pixel grid")
    grid_parser.add_argument("video", type=Path)
    grid_parser.add_argument("--frame", type=int, default=0)
    grid_parser.add_argument("--crop", help="X,Y,W,H in pixels, with a finer grid")
    grid_parser.add_argument("--scale", type=int, default=1, help="Enlargement factor")
    grid_parser.add_argument("--out", type=Path, default=Path("outputs/court"))
    args = parser.parse_args()

    if args.command == "click":
        points = click_landmarks(background(args.video))
        out = args.out or Path("outputs/court") / f"{args.video.stem}_clicks.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(points, indent=2))
        print(f"{len(points)} landmarks -> {out}")
    elif args.command == "fit":
        clicks = {n: tuple(p) for n, p in json.loads(args.clicks.read_text()).items()}
        lens = json.loads(args.lens.read_text()) if args.lens else None
        calibration = calibrate(background(args.video), clicks, lens)
        reprojected = calibration.to_image(np.array([LANDMARKS[name] for name in clicks]))
        print(f"{'landmark':20} {'snapped':>7} {'residual':>8}")
        for (name, click), back in zip(clicks.items(), reprojected):
            point = calibration.points.get(name)
            moved = f"{np.hypot(*np.subtract(point, click)):5.1f}px" if point else "   kept"
            print(f"{name:20} {moved} {np.hypot(*(back - (point or click))):8.1f}")
        print(f"{len(calibration.points)}/{len(clicks)} snapped to the lines, RMS {calibration.error:.1f} px")
        out = args.out or args.courts / f"{args.court or args.video.stem}.json"
        calibration.save(out)
        print(out)
    elif args.command == "auto":
        image = background(args.video)
        best, best_found = None, 0.0
        for path in sorted(args.courts.glob("*.json")):
            court = Calibration.load(path)
            calibration, found, accepted = match(image, court)
            if calibration is None:
                print(f"{path.stem}: other frame size")
                continue
            print(
                f"{path.stem}: line samples on lines {found:.0%}, {len(calibration.points)} landmarks snapped "
                f"({len(court.points)} when calibrated), RMS {calibration.error:.1f} px -> {'match' if accepted else 'no match'}"
            )
            if accepted and found > best_found:
                best, best_found = calibration, found
        if best is None:
            raise SystemExit(f"No stored court matches {args.video}: run `click` then `fit`.")
        out = args.out or Path("outputs/court") / f"{args.video.stem}.json"
        best.save(out)
        print(out)
    else:
        frame = read_frame(args.video, args.frame)
        origin, step = (0, 0), 50
        if args.crop:
            x, y, w, h = map(int, args.crop.split(","))
            frame, origin, step = frame[y : y + h, x : x + w], (x, y), 10
        args.out.mkdir(parents=True, exist_ok=True)
        suffix = f"_{args.crop.replace(',', '_')}" if args.crop else ""
        path = args.out / f"{args.video.stem}_{args.frame}{suffix}_grid.png"
        cv2.imwrite(str(path), draw_grid(frame, origin, args.scale, step))
        print(path)


if __name__ == "__main__":
    main()
