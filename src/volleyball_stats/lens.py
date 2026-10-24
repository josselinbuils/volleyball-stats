"""Lens calibration from a video of a printed checkerboard, for court.py.

Film the board with the match settings (same resolution and field of view): hold it flat at
1-3 m, tilt it, and sweep it over the whole frame, corners and edges included, where the
distortion is strongest. The square size does not matter for the intrinsics.

    uv run python -m volleyball_stats.lens pattern [--out checkerboard.png]
    uv run python -m volleyball_stats.lens calibrate VIDEO [--out lens.json]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

# Inner corners of the board: 10 x 7 squares.
CORNERS = (9, 6)
# Views kept for the fit: more slows it down without improving it.
MAX_VIEWS = 40
# Grid over the frame used to report how much of it the corners covered.
COVERAGE_GRID = (8, 6)


def pattern(square_px: int = 300, margin_px: int = 150) -> np.ndarray:
    """A printable white-bordered checkerboard with CORNERS inner corners."""
    cols, rows = CORNERS[0] + 1, CORNERS[1] + 1
    board = (np.indices((rows, cols)).sum(axis=0) % 2 == 0).astype(np.uint8) * 255
    board = cv2.resize(board, (cols * square_px, rows * square_px), interpolation=cv2.INTER_NEAREST)
    return cv2.copyMakeBorder(board, margin_px, margin_px, margin_px, margin_px, cv2.BORDER_CONSTANT, value=255)


def find_corners(frame: np.ndarray) -> np.ndarray | None:
    """Sub-pixel board corners, (N, 2), or None when the whole board is not found."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    found, corners = cv2.findChessboardCornersSB(gray, CORNERS, flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    return corners.reshape(-1, 2) if found else None


def board_points() -> np.ndarray:
    """The board's corners in square units, in find_corners' order."""
    grid = np.mgrid[0 : CORNERS[0], 0 : CORNERS[1]].T.reshape(-1, 2)
    return np.c_[grid, np.zeros(len(grid))].astype(np.float64)


def fit_lens(views: list[np.ndarray], size: tuple[int, int]) -> dict:
    """OpenCV fisheye intrinsics from the corners of several views, with the RMS reprojection error."""
    # OpenCV 5's fisheye.calibrate only takes (1, N, 3) / (1, N, 2) float32 points.
    objects = [board_points().reshape(1, -1, 3).astype(np.float32)] * len(views)
    images = [v.reshape(1, -1, 2).astype(np.float32) for v in views]
    flags = cv2.CALIB_RECOMPUTE_EXTRINSIC | cv2.CALIB_FIX_SKEW
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-8)
    rms, k, d, _, _ = cv2.fisheye.calibrate(objects, images, size, np.eye(3), np.zeros((4, 1)), flags=flags, criteria=criteria)
    return {"model": "fisheye", "K": k.tolist(), "D": d.ravel().tolist(), "size": list(size), "rms": float(rms)}


def coverage(views: list[np.ndarray], size: tuple[int, int]) -> float:
    """Share of the COVERAGE_GRID cells holding at least one corner."""
    corners = np.concatenate(views)
    cells = np.floor(corners / size * COVERAGE_GRID).astype(int).clip(0, np.array(COVERAGE_GRID) - 1)
    return len({tuple(c) for c in cells}) / (COVERAGE_GRID[0] * COVERAGE_GRID[1])


def detect_views(video: Path, step: int) -> tuple[list[np.ndarray], tuple[int, int]]:
    """Board corners on every `step`-th frame where the whole board is found, and the frame size."""
    cap = cv2.VideoCapture(str(video))
    size = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    views, index = [], 0
    while cap.grab():
        if index % step == 0:
            corners = find_corners(cap.retrieve()[1])
            if corners is not None:
                views.append(corners)
        index += 1
    cap.release()
    return views, size


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate the camera lens from a checkerboard video.")
    sub = parser.add_subparsers(dest="command", required=True)
    pattern_parser = sub.add_parser("pattern", help="Write the checkerboard to print")
    pattern_parser.add_argument("--out", type=Path, default=Path("checkerboard.png"))
    calibrate_parser = sub.add_parser("calibrate", help="Fit the lens from a video of the printed board")
    calibrate_parser.add_argument("video", type=Path)
    calibrate_parser.add_argument("--step", type=int, default=10, help="Frames between two looks for the board")
    calibrate_parser.add_argument("--out", type=Path, default=Path("outputs/lens.json"))
    args = parser.parse_args()

    if args.command == "pattern":
        cv2.imwrite(str(args.out), pattern())
        print(f"{args.out}: print it at 100% on A4 landscape and tape it flat on cardboard")
        return
    views, size = detect_views(args.video, args.step)
    if len(views) < 10:
        raise SystemExit(f"Board found on {len(views)} frames, at least 10 are needed: film it longer, closer or better lit")
    # Evenly spread over the video, so the kept views come from the whole sweep.
    kept = [views[i] for i in np.linspace(0, len(views) - 1, min(MAX_VIEWS, len(views))).round().astype(int)]
    lens = fit_lens(kept, size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(lens, indent=2))
    print(f"board on {len(views)} frames, {len(kept)} used, RMS {lens['rms']:.2f} px, frame covered {coverage(kept, size):.0%}")
    if coverage(kept, size) < 0.6:
        print("the corners missed much of the frame: sweep the board into the corners and edges, and calibrate again")
    print(args.out)


if __name__ == "__main__":
    main()
