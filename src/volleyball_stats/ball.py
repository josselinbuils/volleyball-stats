"""Ball tracking with a pretrained VballNet grid model.

Model and decoding come from https://github.com/asigatchov/vball-net-pytorch (MIT, Alexander
Sigatchov). The model reads 9 consecutive grayscale frames and returns, per frame, a grid of ball
confidences with x/y offsets inside each cell.
"""

import argparse
import csv
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODEL_URL = (
    "https://raw.githubusercontent.com/asigatchov/vball-net-pytorch/"
    "307020e84ca749e7e0f56fdcac506f5f93bd7ffb/models/"
    "VballNetGridV1b_seq9_grayscale_20260319_193937.onnx"
)
MODEL_PATH = Path("models") / MODEL_URL.rsplit("/", 1)[1]


def load_model(path: Path = MODEL_PATH) -> ort.InferenceSession:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, path)
    available = ort.get_available_providers()
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
    return ort.InferenceSession(str(path), providers=providers)


def decode(output: np.ndarray, seq: int, width: int, height: int) -> list[tuple[float, float, float]]:
    """Best cell of each frame's grid, as (x, y, confidence) in model input pixels."""
    rows, cols = output.shape[-2:]
    grids = output.reshape(seq, -1, rows, cols)
    results = []
    for conf, dx, dy in grids[:, :3]:
        row, col = np.unravel_index(np.argmax(conf), conf.shape)
        x = (col + dx[row, col]) * width / cols
        y = (row + dy[row, col]) * height / rows
        results.append((float(x), float(y), float(conf[row, col])))
    return results


def track(
    video: Path, session: ort.InferenceSession, threshold: float = 0.5
) -> Iterator[tuple[np.ndarray, tuple[int, int] | None]]:
    """Yield each frame with the ball position in frame pixels, or None when not found.

    Frames are read in non-overlapping clips of `seq`; trailing frames that do not fill a clip
    are yielded without a position.
    """
    model_input = session.get_inputs()[0]
    seq, height, width = model_input.shape[1:]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open {video}")
    clip = []
    while True:
        ok, frame = cap.read()
        if ok:
            clip.append(frame)
        if clip and (len(clip) == seq or not ok):
            if len(clip) < seq:
                for frame in clip:
                    yield frame, None
                break
            # ponytail: one clip per run call, batch clips if GPU throughput matters.
            gray = [
                cv2.cvtColor(cv2.resize(f, (width, height), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                for f in clip
            ]
            batch = (np.stack(gray)[None] / 255.0).astype(np.float32)
            output = session.run(None, {model_input.name: batch})[0][0]
            frame_h, frame_w = clip[0].shape[:2]
            for frame, (x, y, conf) in zip(clip, decode(output, seq, width, height), strict=True):
                position = (round(x * frame_w / width), round(y * frame_h / height))
                yield frame, position if conf >= threshold else None
            clip = []
        if not ok:
            break
    cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Track the ball in a volleyball video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--overlay", action="store_true", help="Also write a video with the ball drawn")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    session = load_model()
    writer = None
    with open(args.out / f"{args.video.stem}_ball.csv", "w", newline="") as f:
        rows = csv.writer(f)
        rows.writerow(["frame", "visible", "x", "y"])
        for index, (frame, position) in enumerate(track(args.video, session, args.threshold)):
            rows.writerow([index, int(position is not None), *(position or ("", ""))])
            if args.overlay:
                if writer is None:
                    fps = cv2.VideoCapture(str(args.video)).get(cv2.CAP_PROP_FPS)
                    size = frame.shape[1], frame.shape[0]
                    path = str(args.out / f"{args.video.stem}_ball.mp4")
                    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
                if position:
                    cv2.circle(frame, position, 12, (0, 255, 0), 2)
                writer.write(frame)
    if writer:
        writer.release()


if __name__ == "__main__":
    main()
