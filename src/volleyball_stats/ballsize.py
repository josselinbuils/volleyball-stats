"""The ball's width in the picture around each touch: how far from the camera it is.

The camera does not move, so the pixels that differ from both an earlier and a later frame in which
the ball is elsewhere are the ball. The short side of that blob's smallest rectangle is its width:
motion blur only stretches the long side. A ball of BALL_M at a player's feet would be `expected`
pixels wide: `misfits` tells apart two players in line with the camera, one behind the other
(benchmarks/attribution/README.md, "The ball's width").
"""

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import ball3d, decode, files
from volleyball_stats.court import Calibration, undistort

FILE = "ball_widths.json"
BALL_M = 0.21
# The ball is measured within REACH_S of the touch, not within SKIP_S: hands hide it.
REACH_S, SKIP_S = 0.12, 0.04
# The frames compared with are the nearest ones, within AWAY_S, where the ball is SEP pixels (4K) away.
AWAY_S, SEP = 0.28, 60
# Half the square looked at around the ball (4K pixels), and the difference that makes a pixel the ball's.
HALF, THRESHOLD = 72, 22
# A blob is the ball's from AREA pixels (4K), its centre within CENTRE of the tracked ball, filling SOLID of its hull.
AREA, CENTRE, SOLID = 80, 14, 0.75
# A touch's width is the median of at least LEAST frames'.
LEAST = 2


def blob(now: np.ndarray, before: np.ndarray, after: np.ndarray, scale: float = 1.0) -> tuple[float, float] | None:
    """(short side, solidity) of the blob at the centre of `now` that differs from both other crops; None
    when there is none or it leaves the crop."""
    d = np.minimum(cv2.absdiff(now, before).max(2), cv2.absdiff(now, after).max(2))
    d = cv2.GaussianBlur(d, (3, 3), 0)
    mask = (d >= max(THRESHOLD, 4 * float(np.median(d)))).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, centres = cv2.connectedComponentsWithStats(mask, connectivity=8)
    middle = np.array(mask.shape[::-1]) / 2
    near = [k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] >= AREA * scale**2 and np.hypot(*(centres[k] - middle)) <= CENTRE * scale]
    if not near:
        return None
    k = max(near, key=lambda k: stats[k, cv2.CC_STAT_AREA])
    x, y, w, h, area = stats[k]
    if x <= 0 or y <= 0 or x + w >= mask.shape[1] or y + h >= mask.shape[0]:
        return None
    hull = cv2.convexHull(cv2.findNonZero((labels == k).astype(np.uint8)))
    _, (a, b), _ = cv2.minAreaRect(hull)
    return float(min(a, b)), float(area / max(cv2.contourArea(hull), 1.0))


def read_ball(path: Path) -> dict[int, tuple[int, int]]:
    """The ball's pixel by frame, where it is seen."""
    with open(path) as f:
        return {int(r["frame"]): (round(float(r["x"])), round(float(r["y"]))) for r in csv.DictReader(f) if r["visible"] == "1"}


def plan(frame: int, ball: dict[int, tuple[int, int]], fps: float, scale: float) -> list[tuple[int, int, int]]:
    """(frame to measure, frame before, frame after) around the touch at `frame`."""
    reach, skip, away, sep = round(REACH_S * fps), round(SKIP_S * fps), round(AWAY_S * fps), SEP * scale

    def apart(a: int, b: int) -> bool:
        return float(np.hypot(ball[a][0] - ball[b][0], ball[a][1] - ball[b][1])) >= sep

    def other(g: int, step: int) -> int | None:
        return next((g + step * k for k in range(2, away + 1) if g + step * k in ball and apart(g, g + step * k)), None)

    out = []
    for g in range(frame - reach, frame + reach + 1):
        if g in ball and abs(g - frame) >= skip:
            a, b = other(g, -1), other(g, 1)
            if a is not None and b is not None and apart(a, b):
                out.append((g, a, b))
    return out


def widths(video: Path, typed: list[tuple], ball_path: Path, fps: float, cache: Path | None = None) -> dict[int, float]:
    """The ball's width in pixels around each touch of `typed` it could be measured at, by frame; kept
    in `cache` (JSON, by frame and ball place) for the next runs. The video decoded in one pass."""
    kept = json.loads(cache.read_text()) if cache and cache.exists() else {}
    keys = {t[0]: f"{t[0]}:{t[1]}:{t[2]}" for t in typed if t[3] not in ("floor", "net")}
    missing = sorted(f for f, key in keys.items() if key not in kept)
    if missing:
        ball = read_ball(ball_path)
        width, height = decode.size(video)
        scale = width / 3840
        half = round(HALF * scale)
        plans = {f: plan(f, ball, fps, scale) for f in missing}
        last = sorted((max((max(t) for t in p), default=f), f) for f, p in plans.items())
        first = sorted((min((min(t) for t in p), default=f), f) for f, p in plans.items())
        images: dict[int, np.ndarray] = {}
        done: set[int] = set()

        def crop(image: np.ndarray, x: int, y: int) -> np.ndarray:
            x0, y0 = min(max(0, x - half), width - 2 * half), min(max(0, y - half), height - 2 * half)
            return image[y0 : y0 + 2 * half, x0 : x0 + 2 * half]

        def finish(f: int) -> None:
            found = []
            for g, a, b in plans[f]:
                x, y = ball[g]
                if all(h in images for h in (g, a, b)) and half <= x < width - half and half <= y < height - half:
                    got = blob(crop(images[g], x, y), crop(images[a], x, y), crop(images[b], x, y), scale)
                    if got and got[1] >= SOLID:
                        found.append(got[0])
            kept[keys[f]] = round(float(np.median(found)), 1) if len(found) >= LEAST else None
            done.add(f)

        for index, image in decode.frames_at(video, {h for p in plans.values() for t in p for h in t}):
            images[index] = image
            while last and last[0][0] <= index:
                finish(last.pop(0)[1])
            while first and first[0][1] in done:
                first.pop(0)
            for h in [h for h in images if h < (first[0][0] if first else index + 1)]:
                del images[h]
        # Past the video's end, and the touches with no frame to measure: what there is.
        for _, f in last:
            finish(f)
        if cache:
            files.write_text(cache, json.dumps(kept, separators=(",", ":")))
    return {f: kept[key] for f, key in keys.items() if kept.get(key) is not None}


class Depth:
    """What the ball's width says of each candidate: `misfits` of a touch's width to the candidates' places."""

    def __init__(self, calibration: Calibration, feet: dict[int, dict[int, tuple[float, float]]], gap: int):
        self.lens, self.P = calibration.lens, ball3d.projection(calibration)
        self.focal = float(np.asarray(calibration.lens["K"])[0][0]) if calibration.lens else None
        self.feet, self.gap = feet, gap

    def flat(self, x: float, y: float) -> float:
        """Undistorted pixels a picture's pixel spans at (x, y)."""
        p = undistort(np.array([[x - 5, y], [x + 5, y], [x, y - 5], [x, y + 5]], float), self.lens)
        return float(np.hypot(*(p[1] - p[0])) + np.hypot(*(p[3] - p[2]))) / 20

    def expected(self, track: int, frame: int, kind: str) -> float | None:
        """The ball's width in undistorted pixels were it over `track`'s feet (at `frame`, else its nearest
        frame within the gap) at its action's usual height."""
        feet = self.feet.get(track, {})
        at = next((feet[f] for d in range(self.gap + 1) for f in (frame - d, frame + d) if f in feet), None)
        if at is None:
            return None
        depth = float(np.array([*at, -ball3d.HEIGHTS.get(kind, ball3d.OTHER_HEIGHT), 1.0]) @ self.P[2])
        return self.focal * BALL_M / depth if depth > 0 else None

    def misfits(self, width: float | None, x: float, y: float, frame: int, kind: str, tracks: list[int]) -> dict[int, float] | None:
        """How far the ball's `width` at (x, y) stands from what it would be at each of `tracks`, over
        the nearest one's (log of the ratio; 0 for a track with no place); None with no width or camera."""
        if width is None or self.P is None or self.focal is None:
            return None
        seen = width * self.flat(x, y)
        off = {t: None if (e := self.expected(t, frame, kind)) is None else abs(float(np.log(seen / e))) for t in tracks}
        known = [v for v in off.values() if v is not None]
        return {t: 0.0 if v is None else v - min(known) for t, v in off.items()} if known else None
