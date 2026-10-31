"""Ball contacts and net crossings from a ball track.

Between two contacts the ball is in free flight: a parabola in the image, whose velocity only
changes by gravity. A contact is a frame where the velocity fitted on the frames before and the
one fitted on the frames after differ by more than gravity explains. A net crossing is a frame
where the ball passes the net's pixel x, which the court calibration module will provide.
"""

import argparse
import csv
from pathlib import Path

import numpy as np

# Seconds of track on each side of a frame fitting its incoming and outgoing velocities.
WINDOW = 0.17
# Velocity change in px/s above which a frame is a contact, the middle of the plateau found in
# benchmarks/contacts.
THRESHOLD = 360
# Minimum seconds between two contacts.
# ponytail: merges an attack and its block, 2-3 frames apart at 30 fps; a learned spotter on the
# trajectory is the fix once a few hundred contacts are labelled (85 today).
GAP = 0.20
# Pixels the ball must get past the net for a crossing to count, so a ball played at the net
# does not cross it back and forth.
MARGIN = 30
# Longest gap in seconds a net crossing is interpolated over.
MAX_GAP = 1.0
# Ball speed in px/frame under which a frame does not vote for gravity.
MOVING = 3
# The pixel constants are for the school match's court (rallies.COURT_PX long); `scale` is a video's
# court length over it.

Contact = tuple[int, int, int]


def read_track(path: Path) -> np.ndarray:
    """Ball position per frame, (frames, 2), NaN when not visible."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    track = np.full((int(rows[-1]["frame"]) + 1, 2), np.nan)
    for row in rows:
        if row["visible"] == "1":
            track[int(row["frame"])] = float(row["x"]), float(row["y"])
    return track


def gravity(track: np.ndarray, window: int, moving: float = MOVING) -> float:
    """Gravity in px/frame²: the median vertical acceleration of the moving ball, measured over
    `window` frames because integer positions quantize the one-frame one to 0."""
    y = track[:, 1]
    accel = (y[2 * window :] - 2 * y[window:-window] + y[: -2 * window]) / window**2
    speed = np.hypot(*(track[2 * window :] - track[: -2 * window]).T) / (2 * window)
    votes = accel[~np.isnan(accel) & (speed > moving)]
    return float(np.median(votes)) if len(votes) else 0.0


def fit_velocity(frames: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Least-squares velocity of the visible points and their mean frame; None under 2 points."""
    ok = ~np.isnan(points[:, 0])
    if ok.sum() < 2:
        return None
    center = frames[ok].mean()
    t = frames[ok] - center
    return (t @ points[ok]) / (t @ t), center


def velocity_change(track: np.ndarray, window: int, g: float) -> np.ndarray:
    """Per frame, |outgoing - incoming velocity| in px/frame with gravity removed, NaN when a
    side has under 2 visible frames. The frame itself belongs to both flights, so it is in neither fit."""
    frames = np.arange(len(track))
    change = np.full(len(track), np.nan)
    for t in range(window, len(track) - window):
        before = fit_velocity(frames[t - window : t], track[t - window : t])
        after = fit_velocity(frames[t + 1 : t + 1 + window], track[t + 1 : t + 1 + window])
        if before and after:
            delta = after[0] - before[0]
            delta[1] -= g * (after[1] - before[1])
            change[t] = np.hypot(*delta)
    return change


def peaks(signal: np.ndarray, threshold: float, gap: int) -> list[int]:
    """Frames above the threshold, strongest first, none within `gap` frames of a kept one."""
    kept: list[int] = []
    for t in np.argsort(-np.nan_to_num(signal, nan=-np.inf)):
        if not signal[t] >= threshold:
            break
        if all(abs(t - k) > gap for k in kept):
            kept.append(int(t))
    return sorted(kept)


def interpolate(track: np.ndarray) -> np.ndarray:
    """Track with gaps filled linearly from the nearest visible frames; left as is without any."""
    frames = np.arange(len(track))
    ok = ~np.isnan(track[:, 0])
    if not ok.any():
        return track.copy()
    return np.stack([np.interp(frames, frames[ok], track[ok, axis]) for axis in (0, 1)], axis=1)


def detect_contacts(track: np.ndarray, fps: float, threshold: float = THRESHOLD, window: float = WINDOW, gap: float = GAP, scale: float = 1.0) -> list[Contact]:
    """Contacts as (frame, x, y), the position interpolated when the ball is not visible."""
    frames = max(2, round(window * fps))
    change = velocity_change(track, frames, gravity(track, frames, MOVING * scale))
    filled = interpolate(track)
    return [(t, round(filled[t, 0]), round(filled[t, 1])) for t in peaks(change, threshold * scale / fps, round(gap * fps))]


def detect_crossings(track: np.ndarray, net_x: float, fps: float, margin: float = MARGIN) -> list[int]:
    """Frames where the ball passes the net, interpolated between visible frames."""
    crossings: list[int] = []
    side, crossed, last = 0, None, None
    for t in np.flatnonzero(~np.isnan(track[:, 0])):
        x = track[t, 0]
        if last is None or t - last[0] > MAX_GAP * fps:
            side, crossed = 0, None
        elif (x - net_x) * (last[1] - net_x) <= 0 and x != last[1]:
            crossed = last[0] + (net_x - last[1]) / (x - last[1]) * (t - last[0])
        if abs(x - net_x) > margin:
            now = 1 if x > net_x else -1
            if side and now != side and crossed is not None:
                crossings.append(round(crossed))
            side, crossed = now, None
        last = (int(t), x)
    return crossings


def detect(track: np.ndarray, fps: float, net_x: float, scale: float = 1.0) -> tuple[list[Contact], list[int]]:
    """Contacts as (frame, x, y) and net crossing frames of a track with NaN where not visible."""
    return detect_contacts(track, fps, scale=scale), detect_crossings(track, net_x, fps, MARGIN * scale)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect ball contacts and net crossings in a ball track.")
    parser.add_argument("track", type=Path, help="CSV with frame,visible,x,y, as written by ball.py")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--net-x", type=float, required=True, help="Net plane in track pixels (612 on side_club)")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.track.stem.removesuffix("_ball")
    contacts, crossings = detect(read_track(args.track), args.fps, args.net_x)
    with open(args.out / f"{stem}_contacts.csv", "w", newline="") as f:
        csv.writer(f).writerows([["frame", "x", "y"], *contacts])
    with open(args.out / f"{stem}_net.csv", "w", newline="") as f:
        csv.writer(f).writerows([["frame"], *([t] for t in crossings)])
    print(f"{len(contacts)} contacts, {len(crossings)} net crossings")


if __name__ == "__main__":
    main()
