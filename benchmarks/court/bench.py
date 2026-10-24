"""Score the court calibration against hand-located landmarks.

    uv run --group bench python benchmarks/court/bench.py manual VIDEO:GROUND_TRUTH_JSON ...
    uv run --group bench python benchmarks/court/bench.py auto VIDEO:GROUND_TRUTH_JSON ... [--debug DIR]

`manual` fits the homography on the ground-truth landmarks and reports each landmark's leave-one-out
reprojection error. `auto` detects the court lines on the frame, names their intersections and
scores them against the same landmarks.
"""

import argparse
import itertools
import json
import math
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import LANDMARKS, Calibration, fit, read_frame

Points = dict[str, tuple[float, float]]
# Line order along the court length, each with a far and a near end.
TRANSVERSE = ["corner_left", "attack_left", "center", "attack_right", "corner_right"]
# Top-hat response of a line pixel over its surroundings; 15 keeps the low-contrast far sideline of side_vnl.
WHITE_MIN = 15


def load_ground_truth(path: Path) -> tuple[int, Points, dict[str, float]]:
    data = json.loads(path.read_text())
    return data["frame"], {k: tuple(v) for k, v in data["points"].items()}, data.get("tolerance", {})


def line_landmarks(points: Points) -> Points:
    """Posts stay out of the fits: their distance to the sideline is a guess."""
    return {n: p for n, p in points.items() if not n.startswith("post")}


def residual(calibration: Calibration, name: str, image: tuple[float, float]) -> tuple[float, float]:
    """Reprojection error in pixels and in meters of one landmark."""
    court = np.array([LANDMARKS[name]])
    px = float(np.linalg.norm(calibration.to_image(court)[0] - image))
    m = float(np.linalg.norm(calibration.to_court(np.array([image]))[0] - court[0]))
    return px, m


def leave_one_out(points: Points) -> dict[str, tuple[float, float]]:
    lines = line_landmarks(points)
    out = {}
    for name, image in points.items():
        rest = {n: p for n, p in lines.items() if n != name}
        out[name] = residual(fit(rest), name, image)
    return out


def report(rows: dict[str, tuple[float, float]], tolerance: dict[str, float]) -> None:
    print(f"{'landmark':20} {'tol':>4} {'px':>6} {'m':>6}")
    for name, (px, m) in rows.items():
        print(f"{name:20} {tolerance.get(name, 2):4g} {px:6.1f} {m:6.2f}")
    lines = [v for n, v in rows.items() if not n.startswith("post")]
    rms = math.sqrt(sum(px**2 for px, _ in lines) / len(lines))
    meters = sorted(m for _, m in lines)
    print(f"line landmarks: RMS {rms:.1f} px, median {meters[len(meters) // 2]:.2f} m, max {meters[-1]:.2f} m\n")


def manual(pairs: list[tuple[Path, Path]]) -> None:
    for video, truth_path in pairs:
        frame, points, tolerance = load_ground_truth(truth_path)
        lines = line_landmarks(points)
        print(f"{video.stem} frame {frame}: {len(lines)} line landmarks, fit on all RMS {fit(lines).error:.1f} px")
        print("leave-one-out (posts: predicted by the fit on the line landmarks)")
        report(leave_one_out(points), tolerance)


def floor_mask(frame: np.ndarray) -> np.ndarray:
    """Pixels colored like the floor in front of the camera (median hue and saturation of the bottom center)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(int)
    height, width = frame.shape[:2]
    patch = hsv[int(0.6 * height) : int(0.85 * height), int(0.3 * width) : int(0.7 * width)]
    hue, sat = np.median(patch[..., 0]), np.median(patch[..., 1])
    close = (np.abs(hsv[..., 0] - hue) < 12) & (hsv[..., 1] > 0.5 * sat) & (hsv[..., 1] < 1.7 * sat)
    return close.astype(np.uint8)


def white_segments(frame: np.ndarray) -> np.ndarray:
    """Straight pieces of bright thin lines next to floor-colored pixels, as (x1, y1, x2, y2) rows."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    # ponytail: one floor color, so a two-tone floor keeps only the lines bordering the dominant tone.
    near_floor = cv2.dilate(floor_mask(frame), np.ones((21, 21), np.uint8))
    mask = ((tophat > WHITE_MIN) & (gray > 120) & (near_floor > 0)).astype(np.uint8) * 255
    segments = cv2.HoughLinesP(mask, 1, np.pi / 360, 50, minLineLength=40, maxLineGap=8)
    return segments.reshape(-1, 4).astype(float) if segments is not None else np.empty((0, 4))


def merge_segments(segments: np.ndarray, angle_tol: float = 2.5, dist_tol: float = 5.0) -> list[dict]:
    """Group colinear segments; each group is {"point", "dir", "length"} fitted on its endpoints."""
    groups: list[dict] = []
    for x1, y1, x2, y2 in sorted(segments, key=lambda s: -math.hypot(s[2] - s[0], s[3] - s[1])):
        direction = np.array([x2 - x1, y2 - y1])
        length = float(np.linalg.norm(direction))
        direction /= length
        for g in groups:
            cos = abs(float(direction @ g["dir"]))
            normal = np.array([-g["dir"][1], g["dir"][0]])
            off = [abs(float((np.array(p) - g["point"]) @ normal)) for p in ((x1, y1), (x2, y2))]
            if cos > math.cos(math.radians(angle_tol)) and max(off) < dist_tol:
                g["ends"].extend([(x1, y1), (x2, y2)])
                g["length"] += length
                vx, vy, x0, y0 = cv2.fitLine(np.array(g["ends"], np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
                g["point"], g["dir"] = np.array([x0, y0]), np.array([vx, vy])
                break
        else:
            groups.append({"point": np.array([x1, y1]), "dir": direction, "length": length, "ends": [(x1, y1), (x2, y2)]})
    return groups


def line_y(g: dict, x: float) -> float:
    return float(g["point"][1] + (x - g["point"][0]) * g["dir"][1] / g["dir"][0])


def cross(a: dict, b: dict) -> tuple[float, float] | None:
    m = np.array([a["dir"], -b["dir"]]).T
    if abs(np.linalg.det(m)) < 1e-6:
        return None
    t = np.linalg.solve(m, b["point"] - a["point"])
    return tuple((a["point"] + t[0] * a["dir"]).tolist())


def detect_landmarks(frame: np.ndarray, debug: Path | None = None) -> Points | None:
    """Name the court line intersections: the two longest near-horizontal lines are the sidelines, the
    lines crossing them are assigned to TRANSVERSE names by the homography that fits them best."""
    lines = merge_segments(white_segments(frame))
    horizontal = [g for g in lines if abs(g["dir"][1]) < math.sin(math.radians(25)) and g["length"] > 150]
    horizontal.sort(key=lambda g: -g["length"])
    floor = floor_mask(frame)
    sidelines = None
    for a, b in itertools.combinations(horizontal, 2):
        # Sidelines are at least 60 px apart with floor between them.
        xs = np.linspace(0.2 * frame.shape[1], 0.8 * frame.shape[1], 50)
        ys = [(line_y(a, x) + line_y(b, x)) / 2 for x in xs]
        between = [floor[int(y), int(x)] for x, y in zip(xs, ys) if 0 <= y < frame.shape[0]]
        if abs(a["point"][1] - b["point"][1]) > 60 and between and np.mean(between) > 0.6:
            sidelines = sorted((a, b), key=lambda g: g["point"][1])
            break
    if sidelines is None:
        return None
    far, near = sidelines
    transverse = []
    for g in lines:
        if abs(g["dir"][1]) < math.sin(math.radians(25)) or g["length"] < 60:
            continue
        ends = cross(g, far), cross(g, near)
        if None in ends:
            continue
        # The near end must be below the far end and the line must reach between the sidelines.
        ys = [y for _, y in g["ends"]]
        if min(ys) > near["point"][1] - 20 or max(ys) < far["point"][1] + 20:
            continue
        transverse.append((ends[1][0], ends, g["length"]))
    # ponytail: the 8 longest keep the hypothesis search small.
    transverse = sorted(sorted(transverse, key=lambda t: -t[2])[:8])
    transverse = [(x, ends) for x, ends, _ in transverse]
    if debug:
        canvas = frame.copy()
        for g in lines:
            p, d = g["point"], g["dir"]
            cv2.line(canvas, tuple(map(int, p - 2000 * d)), tuple(map(int, p + 2000 * d)), (0, 0, 255), 1)
        for _, (f, n) in transverse:
            cv2.circle(canvas, tuple(map(int, f)), 5, (0, 255, 0), 2)
            cv2.circle(canvas, tuple(map(int, n)), 5, (0, 255, 0), 2)
        cv2.imwrite(str(debug), canvas)
    best = None
    for k in range(min(len(transverse), 5), 2, -1):
        for chosen in itertools.combinations(transverse, k):
            for names in itertools.combinations(TRANSVERSE, k):
                points = {}
                for name, (_, (f, n)) in zip(names, chosen):
                    points[f"{name}_far"], points[f"{name}_near"] = f, n
                try:
                    error = fit(points).error
                except ValueError:
                    continue
                if best is None or error < best[0]:
                    best = (error, points)
        if best and best[0] < 3.0:
            break
    return best[1] if best else None


def auto(pairs: list[tuple[Path, Path]], debug: Path | None) -> None:
    for video, truth_path in pairs:
        frame, truth, tolerance = load_ground_truth(truth_path)
        image = read_frame(video, frame)
        detected = detect_landmarks(image, debug / f"{video.stem}_{frame}_lines.png" if debug else None)
        if not detected:
            print(f"{video.stem} frame {frame}: no court found\n")
            continue
        common = sorted(set(detected) & set(truth))
        print(f"{video.stem} frame {frame}: {len(detected)} landmarks detected, {len(common)} in the ground truth")
        print(f"{'landmark':20} {'detected':>16} {'truth':>16} {'px':>6}")
        for name in sorted(detected):
            d = detected[name]
            if name in truth:
                px = math.dist(d, truth[name])
                print(f"{name:20} {d[0]:8.1f}{d[1]:8.1f} {truth[name][0]:8.1f}{truth[name][1]:8.1f} {px:6.1f}")
            else:
                print(f"{name:20} {d[0]:8.1f}{d[1]:8.1f} {'not labelled':>16}")
        calibration = fit(detected)
        print(f"fit on the detected landmarks RMS {calibration.error:.1f} px; error on the ground truth:")
        report({name: residual(calibration, name, image) for name, image in truth.items()}, tolerance)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("manual", "auto"):
        p = sub.add_parser(command)
        p.add_argument("pairs", nargs="+", help="VIDEO:GROUND_TRUTH_JSON")
        if command == "auto":
            p.add_argument("--debug", type=Path, help="Folder for the detected-lines images")
    args = parser.parse_args()
    pairs = [tuple(map(Path, p.split(":"))) for p in args.pairs]
    if args.command == "manual":
        manual(pairs)
    else:
        if args.debug:
            args.debug.mkdir(parents=True, exist_ok=True)
        auto(pairs, args.debug)


if __name__ == "__main__":
    main()
