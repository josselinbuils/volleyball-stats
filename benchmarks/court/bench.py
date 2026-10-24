"""Score the court calibration against hand-located landmarks.

    uv run --group bench python benchmarks/court/bench.py manual VIDEO:GROUND_TRUTH_JSON ...
    uv run --group bench python benchmarks/court/bench.py refine VIDEO:GROUND_TRUTH_JSON ... [--seeds N]
    uv run --group bench python benchmarks/court/bench.py auto

`manual` fits the homography on the ground-truth landmarks and reports each landmark's leave-one-out
reprojection error. `refine` simulates rough clicks (ground truth + 10-20 px in a random direction)
and scores them as clicked and once snapped to the lines. `auto` stores the two ground-truth courts
and matches them on the other clips, on simulated camera moves and on other courts.
"""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import LANDMARKS, UNSNAPPED, Calibration, background, calibrate, fit, match, read_frame, refine

Points = dict[str, tuple[float, float]]
GROUND_TRUTH = Path("benchmarks/court/ground_truth")


def load_ground_truth(path: Path) -> tuple[int, Points, dict[str, float]]:
    data = json.loads(path.read_text())
    return data["frame"], {k: tuple(v) for k, v in data["points"].items()}, data.get("tolerance", {})


def line_landmarks(points: Points) -> Points:
    """Posts stay out of the fits: their distance to the sideline is a guess."""
    return {n: p for n, p in points.items() if not n.startswith("post")}


def ground_truth_image(video: Path, truth_path: Path) -> np.ndarray:
    """The median frame for a fixed camera, the labelled frame otherwise."""
    data = json.loads(truth_path.read_text())
    return background(video) if data.get("background") else read_frame(video, data["frame"])


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


def rough_clicks(truth: Points, seed: int) -> Points:
    rng = np.random.default_rng(seed)
    angle, radius = rng.uniform(0, 2 * np.pi, len(truth)), rng.uniform(10, 20, len(truth))
    return {n: (x + r * math.cos(a), y + r * math.sin(a)) for (n, (x, y)), a, r in zip(truth.items(), angle, radius)}


def stats(errors: list[float]) -> str:
    e = np.array(errors)
    return f"RMS {np.sqrt(np.mean(e**2)):5.1f}  median {np.median(e):5.2f}  max {e.max():5.1f}" if len(e) else "-"


def court_error(calibration: Calibration, truth: Points) -> list[float]:
    """Meters between each ground-truth landmark mapped to the court and its model position."""
    return [residual(calibration, n, p)[1] for n, p in truth.items()]


def refine_bench(pairs: list[tuple[Path, Path]], seeds: int) -> None:
    for video, truth_path in pairs:
        truth = line_landmarks(load_ground_truth(truth_path)[1])
        image = ground_truth_image(video, truth_path)
        snappable = [n for n in truth if n not in UNSNAPPED]
        clicked, final, snapped = [], [], {n: [] for n in snappable}
        meters_clicks, meters_refined = [], []
        for seed in range(seeds):
            clicks = rough_clicks(truth, seed)
            points, _, _ = refine(image, clicks)
            for name, p in truth.items():
                clicked.append(math.dist(clicks[name], p))
                final.append(math.dist(points.get(name, clicks[name]), p))
                if name in points:
                    snapped[name].append(math.dist(points[name], p))
            meters_clicks += court_error(fit(clicks, ransac=False), truth)
            meters_refined += court_error(calibrate(image, clicks), truth)
        print(f"{video.stem}: {len(truth)} landmarks x {seeds} seeds of clicks 10-20 px off")
        print(f"{'landmark':20} {'snapped':>8}  error once snapped, px")
        for name, errors in snapped.items():
            print(f"{name:20} {len(errors):3}/{seeds:<4}  {stats(errors)}")
        every = [e for errors in snapped.values() for e in errors]
        print(f"snapped {len(every)}/{len(snappable) * seeds} of the snappable landmarks: {stats(every)}")
        print(f"points, px     clicks  {stats(clicked)}")
        print(f"               refined {stats(final)}   (clicks kept where not snapped)")
        print(f"court, m       clicks  {stats(meters_clicks)}   (least squares)")
        print(f"               refined {stats(meters_refined)}\n")


# Library courts built from the ground truth, and the frames matched against them: VIDEO or
# VIDEO@FRAME, with the ground truth that applies when the camera is the same.
LIBRARY = {"side_club": "data/side_club.mp4", "side_vnl": "data/side_vnl.mp4@785"}
TARGETS = {
    "side_club": [
        ("data/side_club.mp4", "side_club"),
        ("data/side_long.mp4", "side_club"),
        ("data/side_holdout.mp4", "side_club"),
        ("data/side_vnl.mp4@785", None),
        ("data/side_vnl.mp4@1500", None),
        ("data/side_vnl.mp4@2500", None),
        ("data/backcourt.mp4@500", None),
        ("data/club.mp4@500", None),
    ],
    "side_vnl": [
        ("data/side_vnl.mp4@785", "side_vnl"),
        ("data/side_vnl.mp4@1500", None),
        ("data/side_vnl.mp4@2500", None),
        ("data/side_vnl.mp4@4300", None),
        ("data/side_club.mp4", None),
        ("data/backcourt.mp4@500", None),
        ("data/club.mp4@500", None),
    ],
}
# Simulated stand moves on side_long: shift x, shift y (px), roll (degrees), zoom.
MOVES = [(40, 20, 0, 1), (90, 0, 0, 1), (0, -90, 0, 1), (120, 0, 0, 1), (0, 0, 2, 1), (0, 0, 4, 1), (0, 0, 6, 1),
         (0, 0, 0, 1.06), (0, 0, 0, 1.1), (30, 15, 1.5, 1.03), (60, -30, 2.5, 1.05)]


def load_image(spec: str, cache: dict) -> np.ndarray:
    if spec not in cache:
        video, _, frame = spec.partition("@")
        cache[spec] = read_frame(Path(video), int(frame)) if frame else background(Path(video))
    return cache[spec]


def auto_row(label: str, image: np.ndarray, court: Calibration, truth: Points | None) -> None:
    calibration, found, accepted = match(image, court)
    cells = f"{found:5.2f}  {len(calibration.points)}/{len(court.points)}  {'match' if accepted else 'no   '}"
    if accepted and truth:
        points = {**calibration.clicks, **calibration.points}
        px = [math.dist(points[n], p) for n, p in truth.items()]
        cells += f"  landmarks {stats(px)} px  court median {np.median(court_error(calibration, truth)):.2f} m"
    print(f"  {label:28} {cells}")


def auto_bench() -> None:
    cache: dict = {}
    for name, spec in LIBRARY.items():
        truth = line_landmarks(load_ground_truth(GROUND_TRUTH / f"{name}.json")[1])
        court = calibrate(load_image(spec, cache), truth)
        print(f"court {name} (ground truth as clicks): {len(court.points)} landmarks snapped, {len(court.template)} line samples")
        print(f"  {'frame':28} found  snapped  verdict")
        for target, truth_name in TARGETS[name]:
            target_truth = line_landmarks(load_ground_truth(GROUND_TRUTH / f"{truth_name}.json")[1]) if truth_name else None
            auto_row(target, load_image(target, cache), court, target_truth)
        if name == "side_club":
            image = load_image("data/side_long.mp4", cache)
            for dx, dy, roll, zoom in MOVES:
                m = cv2.getRotationMatrix2D((image.shape[1] / 2, image.shape[0] / 2), roll, zoom)
                m[:, 2] += (dx, dy)
                warped = cv2.warpAffine(image, m, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REPLICATE)
                moved = {n: tuple(m @ [*p, 1.0]) for n, p in truth.items()}
                auto_row(f"side_long moved {dx},{dy} px {roll}° x{zoom}", warped, court, moved)
        print()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("manual", "refine"):
        p = sub.add_parser(command)
        p.add_argument("pairs", nargs="+", help="VIDEO:GROUND_TRUTH_JSON")
        if command == "refine":
            p.add_argument("--seeds", type=int, default=20)
    sub.add_parser("auto")
    args = parser.parse_args()
    if args.command == "auto":
        auto_bench()
        return
    pairs = [tuple(map(Path, p.split(":"))) for p in args.pairs]
    if args.command == "manual":
        manual(pairs)
    else:
        refine_bench(pairs, args.seeds)


if __name__ == "__main__":
    main()
