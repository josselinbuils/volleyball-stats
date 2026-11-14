"""Video frames, decoded by the ffmpeg CLI: on the GPU (NVDEC, VideoToolbox) when ffmpeg can, else on
the CPU. The conversion to BGR is OpenCV's (BT.601, bicubic) and ffmpeg's GPU frames go through
yuv420p first, so that every decoder gives the same pixels as cv2.VideoCapture.

On the real footage (4K HEVC, 100 Mb/s) on the M4 Pro, VideoToolbox decodes at 133 fps against 69 for
ffmpeg on the CPU and 73 for OpenCV, and 84 against 50 and 51 with every core kept busy.

Wanted frames close together are decoded in one pass, ffmpeg's select filter dropping the others
before their conversion: on the first ASPOM match the wrists' 2517 frames took 419 s, now 198.

A frame is reached by its timestamp, the camera's being slightly irregular. OpenCV's seek guesses it
from the average frame rate: on the first ASPOM match it gives the frame before from frame 142115 on.
"""

import functools
import os
import queue
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Iterator
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

# YOLO reads the players at 1280 px wide; WASB's 512x288 is resized from these frames.
WIDTH = 1280
# ffmpeg restarts at a timestamp over gaps of more frames than this, rather than decoding through them.
SEEK = 150
# Runs of wanted frames one ffmpeg selects at most: its select filter tests each frame against them all.
SELECTED = 64
# Readers at once for scattered frames (`frames_apart`): each ffmpeg start reads the video's index and sets up its decoder,
# most of a lone frame's 0.6 s on a 2-hour 4K match; 8 at once read 40 such frames 4.8 times faster (23.1 -> 4.8 s, 13 Nov, PC).
APART = max(1, min(8, (os.cpu_count() or 2) // 2))


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
def nvenc(codec: str) -> bool:
    """Whether ffmpeg encodes `codec` ("h264", "av1") on an NVIDIA GPU here: listed is not enough, AV1 needs an RTX 40 or later."""
    probe = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1", "-frames:v", "1", "-c:v", f"{codec}_nvenc", "-f", "null", "-"]
    try:
        return subprocess.run(probe, capture_output=True).returncode == 0
    except OSError:
        return False


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


@functools.cache
def timestamps(video: Path) -> np.ndarray:
    """Each frame's time in seconds from the video's start, as ffmpeg's -ss counts it: a camera's are
    slightly irregular, so a frame's index alone does not say where it is. Kept on disk: listing them
    reads the whole file."""
    stat = video.stat()
    kept = Path(tempfile.gettempdir()) / f"volleyball_stats_times_{stat.st_size}_{stat.st_mtime_ns}.npy"
    if kept.exists():
        return np.load(kept)

    def probe(*args: str) -> str:
        return subprocess.run(["ffprobe", "-v", "error", *args, str(video)], capture_output=True, text=True).stdout.strip()

    base = probe("-select_streams", "v:0", "-show_entries", "stream=time_base", "-of", "csv=p=0")
    # Not a video: it has no frame.
    if not base:
        return np.empty(0)
    base = Fraction(base)
    start = float(probe("-show_entries", "format=start_time", "-of", "csv=p=0"))
    ticks = np.sort(np.array(probe("-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "csv=p=0").replace(",", "").split(), dtype=np.int64))
    found = ticks * float(base) - start
    # Under another name first: several readers may list them at once.
    partial = kept.with_name(f"{kept.stem}_{os.getpid()}_{threading.get_ident()}.npy")
    np.save(partial, found)
    partial.replace(kept)
    return found


def piped(video: Path, width: int, height: int, fresh: bool = True, first: int = 0, count: int | None = None, kept: list[int] | None = None, gpu: bool = True) -> Iterator[np.ndarray]:
    """The BGR frames of the video in order at this size, from index `first` (`count` of them, else to
    the end), or only those `kept` (sorted offsets from `first`): ffmpeg still decodes the others but
    neither converts nor sends them. Without `fresh` in one array, valid until the next frame. On the
    GPU when it can, else on the processor: one busy with other work may refuse another decoder."""
    flags = hardware(video) if gpu else ()
    # Half a frame early: ffmpeg drops what comes before the time asked, and no more.
    seek = ("-ss", f"{timestamps(video)[first] - 0.01:.6f}") if first else ()
    select = f"select='{'+'.join(f'between(n,{a},{b})' for a, b in spans(kept))}'," if kept else ""
    count = len(kept) if kept else count
    command = [
        "ffmpeg", "-v", "error", *flags, *seek, "-i", str(video), *(("-frames:v", str(count)) if count else ()), "-an", "-sn", "-dn",
        "-vf", f"{select}{'format=yuv420p,' if flags else ''}scale={width}:{height}:in_color_matrix=bt601:flags=bicubic", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        frame = np.empty((height, width, 3), np.uint8)
        sent = 0
        try:
            while process.stdout.readinto(frame) == frame.nbytes:
                yield frame
                sent += 1
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
            said = errors.read().decode(errors="replace").strip()
            if flags and not sent:
                yield from piped(video, width, height, fresh, first, count, kept, gpu=False)
                return
            raise RuntimeError(f"ffmpeg could not decode {video}: {said}")


def spans(sorted_: list[int]) -> list[tuple[int, int]]:
    """Sorted integers as (first, last) runs of consecutive ones."""
    out: list[tuple[int, int]] = []
    for v in sorted_:
        if out and v == out[-1][1] + 1:
            out[-1] = (out[-1][0], v)
        else:
            out.append((v, v))
    return out


def frames(video: Path, width: int = WIDTH) -> Iterator[np.ndarray]:
    """Every BGR frame of the video in order, `scaled` to `width` pixels wide."""
    return piped(video, *scaled(*size(video), width))


def frames_at(video: Path, wanted: Iterable[int]) -> Iterator[tuple[int, np.ndarray]]:
    """The video's full-size BGR frames at the `wanted` indices in order, decoded straight through
    close ones (only those wanted converted and sent) and restarting at a timestamp over gaps of more
    than SEEK frames or after SELECTED runs of consecutive frames."""
    runs: list[list[int]] = []
    selected = 0
    for frame in sorted(set(wanted)):
        follows = bool(runs) and frame == runs[-1][-1] + 1
        if runs and frame - runs[-1][-1] <= SEEK and (follows or selected < SELECTED):
            runs[-1].append(frame)
            selected += not follows
        else:
            runs.append([frame])
            selected = 1
    width, height = size(video)
    for run in runs:
        if run[0] >= len(timestamps(video)):
            return
        found, decoded = 0, piped(video, width, height, True, run[0], kept=[f - run[0] for f in run])
        try:
            for index, image in zip(run, decoded):
                yield index, image
                found += 1
        finally:
            decoded.close()
        # Past the video's end.
        if found < len(run):
            return


def frames_apart(video: Path, wanted: Iterable[int], workers: int = APART) -> Iterator[tuple[int, np.ndarray]]:
    """`frames_at` with `workers` readers at once, each on a stretch of the `wanted` frames; in no set order."""
    found = sorted(set(wanted))
    parts = [part for k in range(workers) if (part := found[k * len(found) // workers : (k + 1) * len(found) // workers])]
    if len(parts) <= 1:
        yield from frames_at(video, found)
        return
    out: queue.Queue = queue.Queue(maxsize=2 * len(parts))
    stop = threading.Event()

    def put(item) -> bool:
        while not stop.is_set():
            try:
                out.put(item, timeout=0.2)
                return True
            except queue.Full:
                pass
        return False

    def read(part: list[int]) -> None:
        frames = frames_at(video, part)
        try:
            for item in frames:
                if not put(item):
                    return
        except Exception as error:  # noqa: BLE001
            put(error)
            return
        finally:
            frames.close()
        put(None)

    threads = [threading.Thread(target=read, args=(part,), daemon=True) for part in parts]
    for thread in threads:
        thread.start()
    try:
        left = len(threads)
        while left:
            item = out.get()
            if item is None:
                left -= 1
            elif isinstance(item, Exception):
                raise item
            else:
                yield item
    finally:
        stop.set()
        for thread in threads:
            thread.join()


def frame_at(video: Path, index: int) -> np.ndarray | None:
    """The video's full-size BGR frame at this index; None past its end."""
    return next((image for _, image in frames_at(video, [index])), None)
