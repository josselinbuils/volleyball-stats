"""The camera's lens, for court.py: calibrated from a video of a printed checkerboard, or a profile picked by the camera
that filmed the match.

Film the board with the match settings (same resolution, frame rate and field of view): hold it flat at 1-3 m, tilt it,
and sweep it over the whole frame, corners and edges included, where the distortion is strongest. The square size does
not matter for the intrinsics.

    uv run python -m volleyball_stats.lens pattern [--out checkerboard.png]
    uv run python -m volleyball_stats.lens calibrate VIDEO [--out lens.json | --outputs outputs]
"""

import argparse
import json
import re
import time
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode, files, jobs

# Inner corners of the board: 10 x 7 squares.
CORNERS = (9, 6)
# Views kept for the fit: more slows it down without improving it.
MAX_VIEWS = 40
# Grid over the frame used to report how much of it the corners covered.
COVERAGE_GRID = (8, 6)
# A calibration kept: the board on MIN_VIEWS frames at least, over MIN_COVERAGE of the frame, the corners within MAX_RMS
# pixels of the fit. The Osmo Action 3's (30 Oct): 0.53 px.
MIN_VIEWS, MIN_COVERAGE, MAX_RMS = 10, 0.6, 1.0
# The lenses shipped with the code, each with the `camera` it fits (`camera`).
PROFILES = Path(__file__).with_name("lenses")
# Those calibrated in the app, in the outputs folder: before the shipped ones.
OWN = "lenses"
# In a match's folder: the camera that filmed it, read from the card's files at the import (the joined video only names
# ffmpeg).
CAMERA = "camera.json"
# The one lens of the outputs folder before cameras were told apart (26 Nov), for the matches imported then.
# ponytail: no match without a camera.json left, it goes.
LEGACY = "lens.json"
# A line of `calibrate`'s output telling how it went, for the app.
RESULT = "::lens "


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


def detect_views(video: Path, step: int, tell: jobs.Share = jobs.quiet) -> tuple[list[np.ndarray], tuple[int, int]]:
    """Board corners on every `step`-th frame where the whole board is found, and the frame size; the share of the
    frames read told to `tell`."""
    cap = cv2.VideoCapture(str(video))
    size = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    seen = jobs.every(max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))), tell)
    views, index = [], 0
    while cap.grab():
        if index % step == 0:
            corners = find_corners(cap.retrieve()[1])
            if corners is not None:
                views.append(corners)
        seen(index)
        index += 1
    cap.release()
    return views, size


def camera_of(probed: dict) -> dict:
    """The camera ffprobe's `probed` (-show_format -show_streams, as JSON) names, None when its tags name none (a video
    ffmpeg wrote, a camera whose tags are not read here), with its video's frame size and rate."""
    tags = {k.lower(): str(v).strip() for k, v in (probed.get("format", {}).get("tags") or {}).items()}
    video = next((s for s in probed.get("streams", []) if s.get("codec_type") == "video" and s.get("width")), {})
    handler = str((video.get("tags") or {}).get("handler_name", ""))
    model = None
    for make, name in (("com.apple.quicktime.make", "com.apple.quicktime.model"), ("com.android.manufacturer", "com.android.model"), ("make", "model")):
        if tags.get(name):
            model = f"{tags.get(make, '')} {tags[name]}".strip()
            break
    if model is None and tags.get("encoder", "").startswith("DJI"):
        model = tags["encoder"]
    if model is None and handler.startswith("GoPro") and tags.get("firmware"):
        # Its firmware's first part names the model (H22: HERO11 Black).
        model = f"GoPro {tags['firmware'].split('.')[0]}"
    rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    top, _, bottom = rate.partition("/")
    fps = float(top) / float(bottom or 1) if float(bottom or 1) else 0.0
    return {"model": model, "size": [int(video.get("width", 0)), int(video.get("height", 0))], "fps": round(fps, 2)}


def camera(video: Path) -> dict:
    """The camera that filmed `video` (`camera_of`); CalledProcessError when ffprobe cannot read it."""
    return camera_of(json.loads(decode.probe(video, "-show_format", "-show_streams", "-of", "json", check=True)))


def fits(lens: dict, filmed: dict) -> bool:
    """Whether `lens` was calibrated on the camera, frame size and frame rate `filmed` names. The rate counts: a camera
    may crop its sensor for its fastest ones.
    ponytail: the field of view (Standard, Wide) is in none of the tags read; a profile is for the mode recording.md asks."""
    made = lens.get("camera") or {}
    return made.get("model") == filmed.get("model") and list(made.get("size") or []) == list(filmed.get("size") or []) and round(made.get("fps") or 0) == round(filmed.get("fps") or 0)


def lenses(outputs: Path) -> list[tuple[Path, dict]]:
    """Every lens known here: those calibrated in the app, the latest first, then the shipped ones."""
    found = []
    for folder in (outputs / OWN, PROFILES):
        for path in sorted(folder.glob("*.json")):
            try:
                lens = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(lens, dict) and lens.get("camera"):
                found.append((path, lens))
    own = len([p for p, _ in found if p.parent == outputs / OWN])
    return sorted(found[:own], key=lambda f: f[1].get("made", ""), reverse=True) + found[own:]


def for_camera(outputs: Path, filmed: dict) -> Path | None:
    """The lens of the camera `filmed` names, None for one unknown here. One that names none takes only a lens
    calibrated here on a video naming none, of its frame size and rate."""
    return next((p for p, lens in lenses(outputs) if fits(lens, filmed)), None)


def for_match(outputs: Path, folder: Path) -> Path | None:
    """The lens of the camera that filmed the match in `folder` (its CAMERA), else for one imported before cameras were
    told apart, the outputs folder's one lens."""
    filmed = files.read_json(folder / CAMERA, None)
    if isinstance(filmed, dict):
        return for_camera(outputs, filmed)
    return outputs / LEGACY if (outputs / LEGACY).exists() else None


def slug(filmed: dict) -> str:
    """A file name for the lens of the camera `filmed` names."""
    name = re.sub(r"[^a-z0-9]+", "_", (filmed.get("model") or "camera").lower()).strip("_") or "camera"
    w, h = filmed.get("size") or (0, 0)
    return f"{name}_{w}x{h}_{round(filmed.get('fps') or 0)}"


def calibrate(video: Path, step: int, tell: jobs.Share = jobs.quiet) -> dict:
    """The lens from a video of the board, the camera that filmed it, and how it went: the board's `views`, its
    `coverage` of the frame, the fit's `rms`, `kept` when good enough to use (else `why`: "views", "coverage" or "rms")."""
    filmed = camera(video)
    views, size = detect_views(video, step, tell)
    result = {"camera": filmed, "views": len(views)}
    if len(views) < MIN_VIEWS:
        return {**result, "kept": False, "why": "views"}
    # Evenly spread over the video, so the kept views come from the whole sweep.
    kept = [views[i] for i in np.linspace(0, len(views) - 1, min(MAX_VIEWS, len(views))).round().astype(int)]
    lens = fit_lens(kept, size)
    covered = coverage(kept, size)
    result |= {"coverage": round(covered, 3), "rms": round(lens["rms"], 3), "lens": lens}
    why = "coverage" if covered < MIN_COVERAGE else "rms" if lens["rms"] > MAX_RMS else None
    return {**result, "kept": why is None, **({"why": why} if why else {})}


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate the camera lens from a checkerboard video.")
    sub = parser.add_subparsers(dest="command", required=True)
    pattern_parser = sub.add_parser("pattern", help="Write the checkerboard to print")
    pattern_parser.add_argument("--out", type=Path, default=Path("docs/checkerboard.png"))
    calibrate_parser = sub.add_parser("calibrate", help="Fit the lens from a video of the printed board")
    calibrate_parser.add_argument("video", type=Path)
    calibrate_parser.add_argument("--step", type=int, default=10, help="Frames between two looks for the board")
    where = calibrate_parser.add_mutually_exclusive_group()
    where.add_argument("--out", type=Path, help="Where to write it, kept or not")
    where.add_argument("--outputs", type=Path, help="Kept among the outputs folder's lenses, for its camera (the app's)")
    args = parser.parse_args()

    if args.command == "pattern":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.out), pattern())
        print(f"{args.out}: print it on A4 landscape, fit to page, and tape it flat on cardboard")
        return
    result = calibrate(args.video, args.step, jobs.tell)
    print(f"board on {result['views']} frames" + (f", RMS {result['rms']:.2f} px, frame covered {result['coverage']:.0%}" if "rms" in result else ""))
    lens = result.pop("lens", None)
    if lens and (args.out or result["kept"]):
        out = args.out or args.outputs / OWN / f"{slug(result['camera'])}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        files.write_text(out, json.dumps({"camera": result["camera"], **lens, "coverage": result["coverage"], "views": result["views"], "made": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2) + "\n")
        print(out)
    if not result["kept"]:
        print({"views": "board found on too few frames: film it longer, closer or better lit", "coverage": "the corners missed much of the frame: sweep the board into the corners and edges", "rms": "the corners fit badly: keep the board flat and still"}[result["why"]])
    print(RESULT + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
