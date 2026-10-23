"""Ball tracking with the pretrained WASB volleyball model.

Model and weights come from https://github.com/nttcom/WASB-SBDT (MIT, NTT Communications). The
model reads 3 consecutive RGB frames at 512x288 and returns one ball heatmap per frame. The window
moves `stride` frames at a time: 3 sees each frame once; 1 sees it in up to 3 windows and keeps
the strongest blob, which found 6-10% more balls on the side-view clips of benchmarks/ball, at 3x
the compute and for an F1 gain within noise.
"""

import argparse
import csv
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

from volleyball_stats.vendor.wasb_hrnet import HRNet

WEIGHTS_GDRIVE_ID = "1M9y4wPJqLc0K-z-Bo5DP8Ft5XwJuLqIS"
WEIGHTS_PATH = Path("models/wasb_volleyball.pth.tar")
WIDTH, HEIGHT = 512, 288
WINDOW = 3
STRIDE = 3
# Chosen per stride on the side-view clips of benchmarks/ball.
THRESHOLD = {1: 0.2, 3: 0.3}
# Heatmap value bounding a blob.
FLOOR = 0.1
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# WASB's configs/model/wasb.yaml.
_STAGE = {"NUM_MODULES": 1, "BLOCK": "BASIC", "FUSE_METHOD": "SUM"}
MODEL_CONFIG = {
    "frames_in": WINDOW,
    "frames_out": WINDOW,
    "out_scales": [0],
    "MODEL": {
        "EXTRA": {
            "FINAL_CONV_KERNEL": 1,
            "PRETRAINED_LAYERS": ["*"],
            "STEM": {"INPLANES": 64, "STRIDES": [1, 1]},
            "STAGE1": {**_STAGE, "NUM_BRANCHES": 1, "BLOCK": "BOTTLENECK", "NUM_BLOCKS": [1], "NUM_CHANNELS": [32]},
            "STAGE2": {**_STAGE, "NUM_BRANCHES": 2, "NUM_BLOCKS": [2, 2], "NUM_CHANNELS": [16, 32]},
            "STAGE3": {**_STAGE, "NUM_BRANCHES": 3, "NUM_BLOCKS": [2, 2, 2], "NUM_CHANNELS": [16, 32, 64]},
            "STAGE4": {**_STAGE, "NUM_BRANCHES": 4, "NUM_BLOCKS": [2, 2, 2, 2], "NUM_CHANNELS": [16, 32, 64, 128]},
            "DECONV": {"NUM_DECONVS": 0, "KERNEL_SIZE": [], "NUM_BASIC_BLOCKS": 2},
        }
    },
}

Position = tuple[int, int] | None


class AttrDict(dict):
    """HRNet reads its config both as `cfg["X"]` and as `cfg.X`."""

    def __init__(self, data: dict):
        super().__init__({k: AttrDict(v) if isinstance(v, dict) else v for k, v in data.items()})

    __getattr__ = dict.__getitem__


def default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"


def load_model(device: str, path: Path = WEIGHTS_PATH) -> nn.Module:
    if not path.exists():
        import gdown

        path.parent.mkdir(parents=True, exist_ok=True)
        gdown.download(id=WEIGHTS_GDRIVE_ID, output=str(path), quiet=True)
    model = HRNet(AttrDict(MODEL_CONFIG))
    state = torch.load(path, map_location="cpu", weights_only=True)["model_state_dict"]
    model.load_state_dict({k.removeprefix("module."): v for k, v in state.items()})
    return model.to(device).eval()


def preprocess(frame: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(cv2.resize(frame, (WIDTH, HEIGHT)), cv2.COLOR_BGR2RGB) / 255.0
    return ((rgb - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1).astype(np.float32)


def best_blob(heatmap: np.ndarray) -> tuple[float, float, float] | None:
    """Weighted centroid of the blob around the heatmap peak, with the peak value."""
    row, col = np.unravel_index(np.argmax(heatmap), heatmap.shape)
    peak = float(heatmap[row, col])
    if peak < FLOOR:
        return None
    _, labels = cv2.connectedComponents((heatmap >= FLOOR).astype(np.uint8))
    ys, xs = np.nonzero(labels == labels[row, col])
    w = heatmap[ys, xs]
    return float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum()), peak


def track_frames(
    frames: Iterable[np.ndarray],
    model: nn.Module,
    device: str,
    stride: int = STRIDE,
    threshold: float | None = None,
) -> Iterator[tuple[np.ndarray, Position]]:
    """Yield each frame with the ball position in frame pixels, or None when not found."""
    if threshold is None:
        threshold = THRESHOLD[stride]
    pending: deque[tuple[int, np.ndarray, np.ndarray]] = deque()
    best: dict[int, tuple[float, float, float]] = {}

    @torch.no_grad()
    def run(window: list[tuple[int, np.ndarray, np.ndarray]], real: int) -> None:
        # ponytail: one window per forward pass, batch windows if GPU throughput matters.
        batch = torch.from_numpy(np.concatenate([inputs for _, _, inputs in window])[None]).to(device)
        heatmaps = model(batch)[0].sigmoid()[0].cpu().numpy()
        for (index, _, _), heatmap in zip(window[:real], heatmaps[:real]):
            blob = best_blob(heatmap)
            if blob and blob[2] > best.get(index, (0.0, 0.0, -1.0))[2]:
                best[index] = blob

    def position(index: int, frame: np.ndarray) -> Position:
        blob = best.pop(index, None)
        if blob is None or blob[2] < threshold:
            return None
        return round(blob[0] * frame.shape[1] / WIDTH), round(blob[1] * frame.shape[0] / HEIGHT)

    for index, frame in enumerate(frames):
        pending.append((index, frame, preprocess(frame)))
        if len(pending) == WINDOW:
            run(list(pending), WINDOW)
            # The next window starts after these frames: their last view is in.
            for _ in range(stride):
                index, frame, _ = pending.popleft()
                yield frame, position(index, frame)
    if pending:
        real = len(pending)
        run(list(pending) + [pending[-1]] * (WINDOW - real), real)
        for index, frame, _ in pending:
            yield frame, position(index, frame)


def read_frames(video: Path) -> Iterator[np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"Cannot open {video}")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        yield frame
    cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Track the ball in a volleyball video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--stride", type=int, choices=sorted(THRESHOLD), default=STRIDE, help="Frames between windows")
    parser.add_argument("--threshold", type=float, help="Defaults to the value tuned for the stride")
    parser.add_argument("--overlay", action="store_true", help="Also write a video with the ball drawn")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    device = default_device()
    model = load_model(device)
    writer = None
    with open(args.out / f"{args.video.stem}_ball.csv", "w", newline="") as f:
        rows = csv.writer(f)
        rows.writerow(["frame", "visible", "x", "y"])
        tracked = track_frames(read_frames(args.video), model, device, args.stride, args.threshold)
        for index, (frame, position) in enumerate(tracked):
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
