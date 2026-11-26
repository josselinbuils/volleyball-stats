"""Whether the camera frames the court well, and what to change: before a match ("Tester le cadrage", a few seconds
filmed from the planned spot) and at each import, on its court.

The court's four lines must lie in the picture, the far players' heads too; the camera should face the net, high enough
for the near players not to hide the far ones (recording.md: on the net's line, about 6 m back, 3.6 m high).

    uv run python -m volleyball_stats.placement test VIDEO --outputs outputs
    uv run python -m volleyball_stats.placement fit CLICKS_JSON --court NAME --outputs outputs
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import ball3d, court, files, jobs
from volleyball_stats.court import LENGTH, WIDTH, Calibration

# The test's folder in the outputs: its picture without the players, the court found or placed, the verdict, its picture.
FOLDER = "placement"
BACKGROUND, COURT, VERDICT, PICTURE = "background.png", "court.json", "verdict.json", "picture.jpg"
# The camera that filmed the test (lens.camera), for the lens a court placed by hand is fitted with.
CAMERA = "camera.json"
# A line counts as in the picture this far from its edges at least, in fractions of the frame.
EDGE = 0.01
# A player's head on the far sideline, metres: it must show under the picture's top.
HEAD_M = 2.4
# The camera off the net's line by more than this, metres: the players on one side are seen smaller, the net slanted.
ALIGN_M = 1.5
# Lower than this, metres: the near players hide the far ones.
LOW_M = 2.5
SAMPLES = 25


def lines(calibration: Calibration) -> dict[str, np.ndarray]:
    """The court's outline in the picture's pixels: its left and right end lines, its far and near sidelines."""
    s = np.linspace(-1, 1, SAMPLES)
    half_l, half_w = LENGTH / 2, WIDTH / 2
    floor = {
        "left": np.c_[np.full(SAMPLES, -half_l), s * half_w],
        "right": np.c_[np.full(SAMPLES, half_l), s * half_w],
        "far": np.c_[s * half_l, np.full(SAMPLES, -half_w)],
        "near": np.c_[s * half_l, np.full(SAMPLES, half_w)],
    }
    return {name: calibration.to_image(points) for name, points in floor.items()}


def camera_of(calibration: Calibration) -> np.ndarray | None:
    """The camera's projection, only with its lens known: one guessed (a pinhole squaring the court) puts it metres off.
    ponytail: a camera without a lens here gets no height nor heads check; calibrating it gives them."""
    if not calibration.lens or calibration.lens.get("model") == "pinhole":
        return None
    return ball3d.projection(calibration)


def heads(calibration: Calibration) -> np.ndarray | None:
    """Where the far players' heads are in the picture, along the far sideline; None without the camera's lens."""
    P = camera_of(calibration)
    if P is None:
        return None
    pixels = ball3d.project(P, np.c_[np.linspace(-LENGTH / 2, LENGTH / 2, SAMPLES), np.full(SAMPLES, -WIDTH / 2), np.full(SAMPLES, HEAD_M)])
    return court.distort(pixels, calibration.lens) if calibration.lens else pixels


def exits(points: np.ndarray, size: tuple[int, int]) -> set[str]:
    """The picture's edges ("left", "right", "top", "bottom") `points` go past, EDGE from them."""
    x, y = points[:, 0] / size[0], points[:, 1] / size[1]
    return {edge for edge, past in (("left", x < EDGE), ("right", x > 1 - EDGE), ("top", y < EDGE), ("bottom", y > 1 - EDGE)) if past.any()}


# A line leaving the picture through these edges is out; through the others only its corner is, told by the other line.
OWN_EDGES = {"left": {"left", "right"}, "right": {"left", "right"}, "far": {"top", "bottom"}, "near": {"top", "bottom"}}


def judge(calibration: Calibration, size: tuple[int, int]) -> dict:
    """How `calibration`'s court sits in a picture of `size`: the lines `out` of it ("left", "right", "far", "near",
    "heads" for the far players'), where the camera stands (`camera`: metres along the court from the net, positive to
    the right as seen from it, back from the near sideline, high; only with the camera's lens known, a guessed one
    being too rough), the `advice` (codes, the most useful first) and `ok`."""
    out, past = [], set()
    for name, points in lines(calibration).items():
        edges = exits(points, size)
        past |= edges
        if edges & OWN_EDGES[name]:
            out.append(name)
    top = heads(calibration)
    if top is not None and "top" in exits(top, size):
        out.append("heads")
        past.add("top")
    P = camera_of(calibration)
    camera = None if P is None else [round(float(v), 1) for v in ball3d.camera_place(P) - [0, WIDTH / 2, 0]]
    advice = []
    if {"left", "right"} <= past or {"top", "bottom"} <= past:
        advice.append("back")
    if camera and abs(camera[0]) > ALIGN_M:
        # On the right of the net's line, it moves left to face it.
        advice.append("align_left" if camera[0] > 0 else "align_right")
    if camera and camera[2] < LOW_M:
        advice.append("higher")
    if "back" not in advice:
        if not any(a.startswith("align") for a in advice):
            # One end out, the other with room: turned toward it. A camera off the net's line moves first.
            advice += [f"turn_{edge}" for edge in ("left", "right") if edge in past]
        advice += [f"tilt_{way}" for edge, way in (("top", "up"), ("bottom", "down")) if edge in past]
    return {"ok": not out and not advice, "out": out, "advice": advice, "camera": camera, "size": list(size)}


def judge_file(path: Path, size: tuple[int, int] | None = None) -> dict | None:
    """`judge` on a court stored at `path`, on its own frame size unless `size`; None when it cannot be read."""
    try:
        calibration = Calibration.load(path)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    size = size or tuple(calibration.size or ())
    return judge(calibration, size) if len(size) == 2 else None


def test(video: Path, outputs: Path, tell: jobs.Share = jobs.quiet) -> dict:
    """The framing of a few seconds filmed from the planned spot: its picture without the players, then the court
    found among those stored (court.find) and judged; `{"found": False}` when none is, for its points to be clicked."""
    from volleyball_stats import lens

    folder = outputs / FOLDER
    for name in (BACKGROUND, COURT, VERDICT, PICTURE, CAMERA):
        (folder / name).unlink(missing_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        filmed = lens.camera(video)
    except Exception:  # noqa: BLE001 - a file ffprobe cannot read: the court is placed without a lens
        filmed = None
    files.write_text(folder / CAMERA, json.dumps(filmed))
    image = court.background(video, tell=tell)
    cv2.imwrite(str(folder / BACKGROUND), image)
    found = court.find(image, outputs / "courts")
    if found is None:
        return {"found": False}
    return verdict(folder, image, found)


def fit(clicks: dict, name: str, outputs: Path) -> dict:
    """The court of the test placed from rough `clicks` on its picture, fitted with its camera's lens, stored as `name`
    in the courts (the match filmed there finds it alone) and judged."""
    from volleyball_stats import lens

    folder = outputs / FOLDER
    image = cv2.imread(str(folder / BACKGROUND))
    if image is None:
        raise FileNotFoundError(folder / BACKGROUND)
    filmed = files.read_json(folder / CAMERA, None)
    found = lens.for_camera(outputs, filmed) if isinstance(filmed, dict) else None
    known = json.loads(found.read_text()) if found else None
    if known and list(known["camera"]["size"]) != [image.shape[1], image.shape[0]]:
        known = None
    calibration = court.calibrate(image, {n: tuple(p) for n, p in clicks.items()}, known)
    calibration.save(outputs / "courts" / f"{name}.json")
    return verdict(folder, image, calibration)


def verdict(folder: Path, image: np.ndarray, calibration: Calibration) -> dict:
    calibration.save(folder / COURT)
    cv2.imwrite(str(folder / PICTURE), court.check_image(image, calibration))
    result = {"found": True, **judge(calibration, (image.shape[1], image.shape[0]))}
    files.write_text(folder / VERDICT, json.dumps(result) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the camera's framing of the court.")
    sub = parser.add_subparsers(dest="command", required=True)
    test_parser = sub.add_parser("test", help="Find the court on a few seconds filmed from the planned spot and judge it")
    test_parser.add_argument("video", type=Path)
    test_parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    fit_parser = sub.add_parser("fit", help="Place the test's court from rough clicks, store it and judge it")
    fit_parser.add_argument("clicks", type=Path)
    fit_parser.add_argument("--court", required=True, help="The gym's name in the courts")
    fit_parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    judge_parser = sub.add_parser("judge", help="Judge a stored court")
    judge_parser.add_argument("court", type=Path)
    args = parser.parse_args()
    if args.command == "test":
        result = test(args.video, args.outputs, jobs.tell)
    elif args.command == "fit":
        result = fit(json.loads(args.clicks.read_text()), args.court, args.outputs)
    else:
        result = judge_file(args.court)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
