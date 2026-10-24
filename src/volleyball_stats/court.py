"""Court calibration: image pixels to court coordinates in meters and back.

Court frame, in meters on the floor: origin at the center of the court under the net, x along the
length (net at x = 0, end lines at x = ±9, positive to the right as seen from the camera), y across
the width (sidelines at y = ±4.5, positive toward the camera, so far sideline y = -4.5). The
landmarks are the painted line intersections, taken at the line centers (lines are 5 cm wide, so
the model is off by up to 2.5 cm), plus the net post bases.

    uv run python -m volleyball_stats.court grid VIDEO [--frame N] [--crop X,Y,W,H] [--scale S]
    uv run python -m volleyball_stats.court fit POINTS_JSON [--lens LENS_JSON] [--out PATH]

POINTS_JSON maps landmark names to image pixels: {"corner_left_far": [x, y], ...}. LENS_JSON holds
OpenCV intrinsics for the video resolution: {"model": "fisheye" | "standard", "K": 3x3, "D": [...]}.
"""
# ponytail: the DJI Osmo Action 3 at its widest field of view has strong barrel distortion and no
# LENS_JSON yet: calibrate it once with a checkerboard (cv2.fisheye, settings locked) before fitting
# a match. Without it the homography is only as good as the benchmark's side_club numbers.

import argparse
import json
from dataclasses import dataclass
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
# RANSAC inlier threshold: hand-located landmarks are within a few pixels.
RANSAC_PX = 10.0

Lens = dict


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
    """`homography` maps court meters to undistorted pixels; `error` is the fit's RMS residual in px."""

    homography: np.ndarray
    lens: Lens | None = None
    error: float = 0.0

    def to_image(self, points: np.ndarray) -> np.ndarray:
        pixels = apply_homography(self.homography, points)
        return distort(pixels, self.lens) if self.lens else pixels

    def to_court(self, points: np.ndarray) -> np.ndarray:
        pixels = undistort(points, self.lens) if self.lens else np.asarray(points, float).reshape(-1, 2)
        return apply_homography(np.linalg.inv(self.homography), pixels)

    def save(self, path: Path) -> None:
        data = {"homography": self.homography.tolist(), "lens": self.lens, "error": self.error}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        data = json.loads(path.read_text())
        return cls(np.array(data["homography"]), data["lens"], data["error"])


def fit(image_points: dict[str, tuple[float, float]], lens: Lens | None = None) -> Calibration:
    """Homography from named landmarks located in the image, RANSAC over the named points."""
    unknown = set(image_points) - set(LANDMARKS)
    if unknown:
        raise ValueError(f"Unknown landmarks: {sorted(unknown)}")
    if len(image_points) < 4:
        raise ValueError("At least 4 landmarks are needed")
    court = np.array([LANDMARKS[name] for name in image_points])
    image = np.array(list(image_points.values()), float)
    if lens:
        image = undistort(image, lens)
    homography, _ = cv2.findHomography(court, image, cv2.RANSAC, RANSAC_PX)
    if homography is None:
        raise ValueError("No homography fits the landmarks")
    error = float(np.sqrt(np.mean(np.sum((apply_homography(homography, court) - image) ** 2, axis=1))))
    return Calibration(homography, lens, error)


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
    parser = argparse.ArgumentParser(description="Calibrate the court from one video frame.")
    sub = parser.add_subparsers(dest="command", required=True)
    grid_parser = sub.add_parser("grid", help="Write a frame with a labelled pixel grid")
    grid_parser.add_argument("video", type=Path)
    grid_parser.add_argument("--frame", type=int, default=0)
    grid_parser.add_argument("--crop", help="X,Y,W,H in pixels, with a finer grid")
    grid_parser.add_argument("--scale", type=int, default=1, help="Enlargement factor")
    grid_parser.add_argument("--out", type=Path, default=Path("outputs/court"))
    fit_parser = sub.add_parser("fit", help="Fit and save a calibration from named image points")
    fit_parser.add_argument("points", type=Path)
    fit_parser.add_argument("--lens", type=Path)
    fit_parser.add_argument("--out", type=Path, default=Path("outputs/court/calibration.json"))
    args = parser.parse_args()

    if args.command == "grid":
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
    else:
        points = json.loads(args.points.read_text())
        lens = json.loads(args.lens.read_text()) if args.lens else None
        calibration = fit(points, lens)
        reprojected = calibration.to_image(np.array([LANDMARKS[name] for name in points]))
        for name, image, back in zip(points, points.values(), reprojected):
            print(f"{name:20} {np.hypot(*(back - image)):6.1f} px")
        print(f"RMS {calibration.error:.1f} px")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        calibration.save(args.out)
        print(args.out)


if __name__ == "__main__":
    main()
