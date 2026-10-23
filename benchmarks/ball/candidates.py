"""Ball tracker candidates.

Each candidate maps a video to one list of blobs per frame, in frame pixels: `(x, y, peak, mass)`.
Candidates keep every blob above a low floor, so scoring can sweep thresholds and compare
selection policies.
"""

import sys
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch

CACHE = Path(".cache/bench")
DEVICE = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
FLOOR = 0.1

Blob = tuple[float, float, float, float]
Candidate = Callable[[Path], list[list[Blob]]]


class AttrDict(dict):
    """WASB's HRNet reads its config both as `cfg["X"]` and as `cfg.X`."""

    def __init__(self, data: dict):
        super().__init__({k: AttrDict(v) if isinstance(v, dict) else v for k, v in data.items()})

    __getattr__ = dict.__getitem__


def read_frames(video: Path) -> Iterator[np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        yield frame
    cap.release()


def run_clips(
    video: Path, n: int, infer: Callable[[list[np.ndarray]], list[list[Blob]]], stride: int | None = None
) -> list[list[Blob]]:
    """Run `infer` on clips of `n` frames every `stride` frames, pooling the blobs of overlapping
    clips per frame. The last clip is padded with its last frame."""
    stride = stride or n
    pooled: dict[int, list[Blob]] = defaultdict(list)
    buffer: deque[np.ndarray] = deque()
    start = total = 0
    for total, frame in enumerate(read_frames(video), 1):
        buffer.append(frame)
        if len(buffer) == n:
            for k, blobs in enumerate(infer(list(buffer))):
                pooled[start + k] += blobs
            for _ in range(stride):
                buffer.popleft()
            start += stride
    if buffer:
        real = len(buffer)
        clip = list(buffer) + [buffer[-1]] * (n - real)
        for k, blobs in enumerate(infer(clip)[:real]):
            pooled[start + k] += blobs
    return [pooled[i] for i in range(total)]


def heatmap_blobs(hm: np.ndarray, scale: tuple[float, float]) -> list[Blob]:
    """One blob per connected component above FLOOR: weighted centroid, peak and mass."""
    count, labels = cv2.connectedComponents((hm >= FLOOR).astype(np.uint8))
    blobs = []
    for label in range(1, count):
        ys, xs = np.nonzero(labels == label)
        w = hm[ys, xs]
        x, y = (xs * w).sum() / w.sum(), (ys * w).sum() / w.sum()
        blobs.append((float(x * scale[0]), float(y * scale[1]), float(w.max()), float(w.sum())))
    return blobs


def onnx_session(name: str) -> ort.InferenceSession:
    return ort.InferenceSession(str(CACHE / name), providers=["CPUExecutionProvider"])


def vballnet_grid(name: str) -> Candidate:
    """VballNet grid models: 9 grayscale frames at 768x432, a 48x27 grid of (conf, dx, dy)."""

    def run(video: Path) -> list[list[Blob]]:
        session = onnx_session(name)
        model_input = session.get_inputs()[0]
        seq, height, width = model_input.shape[1:]

        def infer(clip: list[np.ndarray]) -> list[list[Blob]]:
            gray = [
                cv2.cvtColor(cv2.resize(f, (width, height), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                for f in clip
            ]
            batch = (np.stack(gray)[None] / 255.0).astype(np.float32)
            out = session.run(None, {model_input.name: batch})[0][0]
            rows, cols = out.shape[-2:]
            sx, sy = clip[0].shape[1] / cols, clip[0].shape[0] / rows
            frames = []
            for conf, dx, dy in out.reshape(seq, -1, rows, cols)[:, :3]:
                peaks = (conf >= FLOOR) & (conf == cv2.dilate(conf, np.ones((3, 3), np.uint8)))
                frames.append(
                    [((c + dx[r, c]) * sx, (r + dy[r, c]) * sy, float(conf[r, c]), float(conf[r, c])) for r, c in zip(*np.nonzero(peaks))]
                )
            return frames

        return run_clips(video, seq, infer)

    run.device = "cpu"
    return run


def vballnet_heatmap(name: str) -> Candidate:
    """VballNet V1 / FastV1: 3 RGB frames at 512x288, 3 heatmaps."""

    def run(video: Path) -> list[list[Blob]]:
        session = onnx_session(name)
        model_input = session.get_inputs()[0]

        def infer(clip: list[np.ndarray]) -> list[list[Blob]]:
            rgb = [cv2.cvtColor(cv2.resize(f, (512, 288)), cv2.COLOR_BGR2RGB) for f in clip]
            batch = (np.concatenate(rgb, axis=2).transpose(2, 0, 1)[None] / 255.0).astype(np.float32)
            hms = session.run(None, {model_input.name: batch})[0][0]
            scale = (clip[0].shape[1] / 512, clip[0].shape[0] / 288)
            return [heatmap_blobs(hm, scale) for hm in hms]

        return run_clips(video, 3, infer)

    run.device = "cpu"
    return run


def wasb(model_name: str, weights: str, stride: int = 3) -> Candidate:
    """WASB volleyball models (HRNet = WASB, TrackNetV2): 3 RGB frames at 512x288, 3 heatmaps."""

    def run(video: Path) -> list[list[Blob]]:
        sys.path.insert(0, str(CACHE / "wasb/src"))
        import yaml

        from models import build_model

        config = yaml.safe_load((CACHE / f"wasb/src/configs/model/{model_name}.yaml").read_text())
        model = build_model({"model": AttrDict(config)})
        state = torch.load(CACHE / weights, map_location="cpu", weights_only=True)["model_state_dict"]
        model.load_state_dict({k.removeprefix("module."): v for k, v in state.items()})
        model.to(DEVICE).eval()

        @torch.no_grad()
        def infer(clip: list[np.ndarray]) -> list[list[Blob]]:
            rgb = [cv2.cvtColor(cv2.resize(f, (512, 288)), cv2.COLOR_BGR2RGB) / 255.0 for f in clip]
            norm = [((f - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1) for f in rgb]
            batch = torch.from_numpy(np.concatenate(norm)[None].astype(np.float32)).to(DEVICE)
            hms = model(batch)[0].sigmoid()[0].cpu().numpy()
            scale = (clip[0].shape[1] / 512, clip[0].shape[0] / 288)
            return [heatmap_blobs(hm, scale) for hm in hms]

        return run_clips(video, 3, infer, stride)

    return run


def tracknetv3(weights: str) -> Candidate:
    """TrackNetV3: median background + 8 RGB frames at 512x288, 8 heatmaps."""

    def run(video: Path) -> list[list[Blob]]:
        sys.path.insert(0, str(CACHE / "tracknetv3"))
        from PIL import Image

        from model import TrackNet

        checkpoint = torch.load(CACHE / weights, map_location="cpu", weights_only=True)
        seq = checkpoint["param_dict"]["seq_len"]
        model = TrackNet(in_dim=(seq + 1) * 3, out_dim=seq)
        model.load_state_dict(checkpoint["model"])
        model.to(DEVICE).eval()

        def resize(rgb: np.ndarray) -> np.ndarray:
            return np.moveaxis(np.array(Image.fromarray(rgb).resize((512, 288))), -1, 0)

        # ponytail: median of 300 downscaled frames, upstream takes up to 1800 at full size.
        count = int(cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, count // 300)
        samples = [resize(f[..., ::-1].copy()) for i, f in enumerate(read_frames(video)) if i % step == 0]
        median = np.median(samples, 0).astype(np.uint8)

        @torch.no_grad()
        def infer(clip: list[np.ndarray]) -> list[list[Blob]]:
            x = np.concatenate([median] + [resize(f[..., ::-1].copy()) for f in clip])
            batch = torch.from_numpy((x[None] / 255.0).astype(np.float32)).to(DEVICE)
            hms = model(batch)[0].cpu().numpy()
            scale = (clip[0].shape[1] / 512, clip[0].shape[0] / 288)
            return [heatmap_blobs(hm, scale) for hm in hms]

        return run_clips(video, seq, infer)

    return run


def yolo(weights: str, imgsz: int) -> Candidate:
    """Generic COCO detector, every 'sports ball' box."""

    def run(video: Path) -> list[list[Blob]]:
        from ultralytics import YOLO

        model = YOLO(str(CACHE / weights))
        frames = []
        for frame in read_frames(video):
            # COCO "sports ball" scores run low on volleyballs, so this floor sits below FLOOR.
            boxes = model.predict(frame, imgsz=imgsz, classes=[32], conf=0.05, device=DEVICE, verbose=False)[0].boxes
            frames.append(
                [((x1 + x2) / 2, (y1 + y2) / 2, c, c) for (x1, y1, x2, y2), c in zip(boxes.xyxy.tolist(), boxes.conf.tolist())]
            )
        return frames

    return run


CANDIDATES: dict[str, Candidate] = {
    "vballnet-grid-v1b": vballnet_grid("vballnet_grid_v1b.onnx"),
    "vballnet-grid-v1c": vballnet_grid("vballnet_grid_v1c.onnx"),
    "vballnet-v1": vballnet_heatmap("vballnet_v1.onnx"),
    "vballnet-fast-v1": vballnet_heatmap("vballnet_fast_v1.onnx"),
    "wasb": wasb("wasb", "wasb_volleyball.pth.tar"),
    "wasb-step1": wasb("wasb", "wasb_volleyball.pth.tar", stride=1),
    "tracknetv2": wasb("tracknetv2", "tracknetv2_volleyball.pth.tar"),
    "tracknetv3-beach": tracknetv3("tracknetv3_beach.pt"),
    "yolo11n": yolo("yolo11n.pt", 1280),
    "yolo11x": yolo("yolo11x.pt", 1280),
}
