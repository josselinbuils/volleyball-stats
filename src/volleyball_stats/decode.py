"""Video frames for the trackers, decoded once by the ffmpeg CLI: on an NVIDIA GPU (NVDEC) when
ffmpeg can, else on the CPU, then scaled down to the models' input width before reaching Python,
rather than handed over at 4K. The conversion to BGR is OpenCV's (BT.601, bicubic): a video at that
width or smaller gets the same pixels as from cv2.VideoCapture.

ponytail: on the M4 Pro, VideoToolbox decodes 4K HEVC slower than the CPU (135 vs 145 fps), so a
Mac decodes on the CPU; add `-hwaccel videotoolbox` to `frames` if a Mac ever gains from it.
"""

import functools
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

# YOLO reads the players at 1280 px wide; WASB's 512x288 is resized from these frames.
WIDTH = 1280


def size(video: Path) -> tuple[int, int]:
    """The video's frame width and height."""
    cap = cv2.VideoCapture(str(video))
    out = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return out


def scaled(width: int, height: int, target: int = WIDTH) -> tuple[int, int]:
    """A frame size `target` pixels wide with an even height, never larger than the video's own."""
    if width <= target:
        return width, height
    return target, 2 * round(height * target / width / 2)


@functools.cache
def cuda(video: Path) -> bool:
    """Whether ffmpeg decodes `video` on an NVIDIA GPU."""
    probe = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-i", str(video), "-frames:v", "1", "-f", "null", "-"]
    return subprocess.run(probe, capture_output=True).returncode == 0


def frames(video: Path, width: int = WIDTH) -> Iterator[np.ndarray]:
    """Every BGR frame of the video in order, `scaled` to `width` pixels wide."""
    w, h = scaled(*size(video), width)
    command = [
        "ffmpeg", "-v", "error", *(["-hwaccel", "cuda"] if cuda(video) else []), "-i", str(video), "-an", "-sn", "-dn",
        "-vf", f"scale={w}:{h}:in_color_matrix=bt601:flags=bicubic", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        try:
            while process.stdout.readinto(frame := np.empty((h, w, 3), np.uint8)) == frame.nbytes:
                yield frame
            process.wait()
        finally:
            # Once ffmpeg has exited this does nothing; when the reader stops early it ends ffmpeg.
            process.kill()
            process.wait()
            process.stdout.close()
        if process.returncode:
            errors.seek(0)
            raise RuntimeError(f"ffmpeg could not decode {video}: {errors.read().decode(errors='replace').strip()}")
