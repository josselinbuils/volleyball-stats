"""Video frames, decoded by the ffmpeg CLI: on the GPU (NVDEC, VideoToolbox) when ffmpeg can, else on
the CPU. The conversion to BGR is OpenCV's (BT.601, bicubic) and ffmpeg's GPU frames go through
yuv420p first, so that every decoder gives the same pixels as cv2.VideoCapture.

On the real footage (4K HEVC, 100 Mb/s) on the M4 Pro, VideoToolbox decodes at 133 fps against 69 for
ffmpeg on the CPU and 73 for OpenCV, and 84 against 50 and 51 with every core kept busy.
"""

import functools
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np

# YOLO reads the players at 1280 px wide; WASB's 512x288 is resized from these frames.
WIDTH = 1280
# OpenCV seeks over gaps of more frames than this, rather than decoding through them.
SEEK = 150


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


@functools.cache
def hardware(video: Path) -> tuple[str, ...]:
    """ffmpeg's flags decoding `video` on the GPU; none when it cannot."""
    if cuda(video):
        return "-hwaccel", "cuda"
    if sys.platform == "darwin":
        probe = ["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-i", str(video), "-frames:v", "1", "-f", "null", "-"]
        if subprocess.run(probe, capture_output=True).returncode == 0:
            return "-hwaccel", "videotoolbox"
    return ()


def piped(video: Path, width: int, height: int, fresh: bool = True) -> Iterator[np.ndarray]:
    """Every BGR frame of the video in order at this size; without `fresh` in one array, valid until the next frame."""
    flags = hardware(video)
    command = [
        "ffmpeg", "-v", "error", *flags, "-i", str(video), "-an", "-sn", "-dn",
        "-vf", f"{'format=yuv420p,' if flags else ''}scale={width}:{height}:in_color_matrix=bt601:flags=bicubic", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        frame = np.empty((height, width, 3), np.uint8)
        try:
            while process.stdout.readinto(frame) == frame.nbytes:
                yield frame
                if fresh:
                    frame = np.empty((height, width, 3), np.uint8)
            process.wait()
        finally:
            # Once ffmpeg has exited this does nothing; when the reader stops early it ends ffmpeg.
            process.kill()
            process.wait()
            process.stdout.close()
        if process.returncode:
            errors.seek(0)
            raise RuntimeError(f"ffmpeg could not decode {video}: {errors.read().decode(errors='replace').strip()}")


def frames(video: Path, width: int = WIDTH) -> Iterator[np.ndarray]:
    """Every BGR frame of the video in order, `scaled` to `width` pixels wide."""
    return piped(video, *scaled(*size(video), width))


def seeking(video: Path, wanted: list[int]) -> Iterator[tuple[int, np.ndarray]]:
    """The frames at the sorted `wanted` indices, OpenCV seeking over the long gaps."""
    cap, position = cv2.VideoCapture(str(video)), 0
    for frame in wanted:
        if frame - position > SEEK:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
            position = frame
        while position < frame:
            cap.grab()
            position += 1
        ok, image = cap.read()
        position += 1
        if not ok:
            break
        yield frame, image
    cap.release()


def frames_at(video: Path, wanted: Iterable[int]) -> Iterator[tuple[int, np.ndarray]]:
    """The video's full-size BGR frames at the `wanted` indices in order.

    Decoded from the start by ffmpeg, frames counted; OpenCV seeks when that would skip most of the
    video, exact too: same pixels on 73 frames over a whole match, around each irregular timestamp."""
    ordered = sorted(set(wanted))
    if not ordered:
        return
    gaps = np.diff([0, *ordered])
    if 2 * gaps[gaps <= SEEK].sum() < ordered[-1]:
        yield from seeking(video, ordered)
        return
    remaining = iter(ordered)
    target = next(remaining)
    for index, image in enumerate(piped(video, *size(video), fresh=False)):
        if index == target:
            yield index, image.copy()
            target = next(remaining, None)
            if target is None:
                return
