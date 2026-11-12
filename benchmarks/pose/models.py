"""The pose models compared with YOLO11m-pose (README.md): each runs on BGR crops.

`Yolo(path).find(images, imgsz, conf)` is bottom-up: per image the (boxes, keypoints) of the people it finds.
The others are top-down: `.keypoints(image, boxes)` gives 17 COCO keypoints (x, y, confidence) per given xyxy box.
"""

from pathlib import Path

import cv2
import numpy as np

DIR = Path("models/pose_candidates")


class Yolo:
    def __init__(self, path: str, device: str = "cuda"):
        from ultralytics import YOLO

        self.model, self.device = YOLO(path), device

    def find(self, images: list[np.ndarray], imgsz: int, conf: float) -> list[tuple[np.ndarray, np.ndarray]]:
        out = []
        for r in self.model.predict(images, imgsz=imgsz, conf=conf, device=self.device, verbose=False):
            out.append((r.boxes.xyxy.cpu().numpy(), r.keypoints.data.cpu().numpy()))
        return out


def affine(box: np.ndarray, size: tuple[int, int], padding: float = 1.25) -> np.ndarray:
    """mmpose's top-down crop: the box's centre and scale (padded, to the input's aspect ratio) onto `size` (w, h)."""
    cx, cy, w, h = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, box[2] - box[0], box[3] - box[1]
    aspect = size[0] / size[1]
    if w > h * aspect:
        h = w / aspect
    else:
        w = h * aspect
    w, h = w * padding, h * padding
    src = np.float32([[cx, cy], [cx, cy - h / 2], [cx - w / 2, cy - h / 2]])
    dst = np.float32([[size[0] / 2, size[1] / 2], [size[0] / 2, 0], [0, 0]])
    return cv2.getAffineTransform(src, dst)


def crops(image: np.ndarray, boxes: np.ndarray, size: tuple[int, int], mean, std) -> tuple[np.ndarray, list[np.ndarray]]:
    """Normalised RGB crops (n, 3, h, w) of the boxes and each one's inverse affine."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    out, inverse = [], []
    for box in boxes:
        m = affine(box, size)
        patch = cv2.warpAffine(rgb, m, size, flags=cv2.INTER_LINEAR).astype(np.float32)
        out.append(((patch - mean) / std).transpose(2, 0, 1))
        inverse.append(cv2.invertAffineTransform(m))
    return np.stack(out) if out else np.zeros((0, 3, size[1], size[0]), np.float32), inverse


class Rtm:
    """RTMPose / RTMW through onnxruntime (SimCC heads, 384x288 input); a whole-body model's first 17 keypoints are COCO's."""

    def __init__(self, folder: str):
        import onnxruntime as ort

        path = next((DIR / folder).rglob("end2end.onnx"))
        self.session = ort.InferenceSession(str(path), providers=[("CUDAExecutionProvider", {"gpu_mem_limit": 2 << 30}), "CPUExecutionProvider"])
        self.size = (288, 384)
        self.mean, self.std = np.array([123.675, 116.28, 103.53], np.float32), np.array([58.395, 57.12, 57.375], np.float32)

    def keypoints(self, image: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        if not len(boxes):
            return np.zeros((0, 17, 3))
        x, inverse = crops(image, boxes, self.size, self.mean, self.std)
        sx, sy = self.session.run(None, {"input": x})
        sx, sy = sx[:, :17], sy[:, :17]
        px, py = sx.argmax(-1), sy.argmax(-1)
        score = np.minimum(sx.max(-1), sy.max(-1))
        out = np.zeros((len(boxes), 17, 3))
        for i, m in enumerate(inverse):
            pts = np.stack([px[i] / 2.0, py[i] / 2.0], -1)
            out[i, :, :2] = pts @ m[:, :2].T + m[:, 2]
            out[i, :, 2] = score[i]
        return out


class VitPose:
    """ViTPose through transformers (heatmaps, 256x192 input)."""

    def __init__(self, folder: str, device: str = "cuda"):
        import torch
        from transformers import AutoProcessor, VitPoseForPoseEstimation

        self.torch, self.device = torch, device
        self.processor = AutoProcessor.from_pretrained(str(DIR / folder))
        self.model = VitPoseForPoseEstimation.from_pretrained(str(DIR / folder), torch_dtype=torch.float16).to(device).eval()
        self.plus = "plus" in folder

    def keypoints(self, image: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        if not len(boxes):
            return np.zeros((0, 17, 3))
        torch = self.torch
        x, inverse = crops(image, boxes, (192, 256), np.array([123.675, 116.28, 103.53], np.float32), np.array([58.395, 57.12, 57.375], np.float32))
        extra = {"dataset_index": torch.zeros(len(boxes), dtype=torch.long, device=self.device)} if self.plus else {}
        with torch.no_grad():
            heat = self.model(pixel_values=torch.from_numpy(x).to(self.device, torch.float16), **extra).heatmaps.float()
        return decode_heatmaps(heat, inverse, (192, 256))


def decode_heatmaps(heat, inverse: list[np.ndarray], size: tuple[int, int]) -> np.ndarray:
    """Heatmaps (n, 17, h, w) to keypoints in the image: the maximum, a quarter pixel towards its higher neighbours, the
    input's affine undone."""
    n, k, h, w = heat.shape
    score, index = heat.reshape(n, k, -1).max(-1)
    ys, xs = (index // w).cpu().numpy(), (index % w).cpu().numpy()
    heat = heat.cpu().numpy()
    out = np.zeros((n, k, 3))
    for i, m in enumerate(inverse):
        for j in range(k):
            x, y = float(xs[i, j]), float(ys[i, j])
            if 0 < xs[i, j] < w - 1:
                x += 0.25 * np.sign(heat[i, j, ys[i, j], xs[i, j] + 1] - heat[i, j, ys[i, j], xs[i, j] - 1])
            if 0 < ys[i, j] < h - 1:
                y += 0.25 * np.sign(heat[i, j, ys[i, j] + 1, xs[i, j]] - heat[i, j, ys[i, j] - 1, xs[i, j]])
            out[i, j, :2] = m[:, :2] @ np.array([(x + 0.5) * size[0] / w, (y + 0.5) * size[1] / h]) + m[:, 2]
        out[i, :, 2] = score[i].cpu().numpy()
    return out


class Sapiens:
    """Sapiens pose (Meta, torchscript, 1024x768 input, 308 Goliath keypoints); COCO's 17 picked from them."""

    # COCO index -> Goliath index (the wrists are not among its first 17).
    PICK = [0, 1, 2, 3, 4, 5, 6, 7, 8, 62, 41, 9, 10, 11, 12, 13, 14]

    def __init__(self, folder: str, device: str = "cuda"):
        import torch

        self.torch, self.device = torch, device
        self.model = torch.jit.load(str(next((DIR / folder).glob("*.pt2"))), map_location=device).eval().half()
        self.size = (768, 1024)
        self.mean, self.std = np.array([123.5, 116.5, 103.5], np.float32), np.array([58.5, 57.0, 57.5], np.float32)

    def keypoints(self, image: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        if not len(boxes):
            return np.zeros((0, 17, 3))
        torch = self.torch
        x, inverse = crops(image, boxes, self.size, self.mean, self.std)
        with torch.no_grad():
            heat = self.model(torch.from_numpy(x).to(self.device).half())[:, self.PICK].float()
        return decode_heatmaps(heat, inverse, self.size)


def load(name: str):
    """A candidate by name."""
    if name.startswith("yolo"):
        return Yolo(str(DIR / f"{name}.pt") if name != "yolo11m-pose" else "models/yolo11m-pose.pt")
    if name.startswith("rtm"):
        return Rtm(name)
    if name.startswith("vitpose"):
        return VitPose(name)
    if name.startswith("sapiens"):
        return Sapiens(name)
    raise SystemExit(f"unknown model {name}")
