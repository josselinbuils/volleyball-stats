"""The lighter copies of a match's video its hosted page plays, on the source's timeline, cut by the automatic zoom.

    uv run python -m volleyball_stats.video_copies VIDEO CAMERA_JSON

`light`, 1440p H.264, plays in browsers without AV1; `av1`, 1440p, plays in the others, smaller at the same quality;
`small`, 720p H.264, plays while the player is small. Each frame is cut from the source where the automatic zoom looks
then (`framing.camera`, given as `framing.camera_spans`), so a zoomed moment keeps the source's pixels: the page zoomed a
1440p copy until 16 Nov. VMAF on 20 s of the Avia match zoomed 1.9x on average, against the 4K source cut the same way,
on a 1920x1080 screen (docs/hosting.md): 88.7 against 76.9 for the 1440p copy zoomed in the browser, 88.8 against 69.8 on
a 2560x1440 one; on 20 s of the whole picture 86.8 against 86.2. The copies come from one reading of the source: ffmpeg
decodes it (on the GPU when it can), OpenCV cuts each frame at sub-pixel precision (bicubic: 2.6 points over bilinear,
the area's 2.4 under on the whole picture), ffmpeg encodes the three (NVENC when it can, else x264 and SVT-AV1). On the
RTX 5080, the three from 20 s of 4K in 12.4 s, against 5.0 for the former ones resized on the GPU. A copy only appears
once whole.
ponytail: a frame read while the last one is encoded (a thread) would save the pipe's share of the time.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode, files, framing, jobs

H264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-maxrate", "8M", "-bufsize", "16M"]
NVENC = ["-preset", "p4", "-tune", "hq", "-rc", "vbr", "-b:v", "0"]
# Every 2 s: the jumps between clips do not freeze.
KEYFRAMES = ["-g", "50"]
FPS = 25
COPIES = {
    "light": ("_1440p", 1440, H264),
    "av1": ("_av1", 1440, ["-c:v", "libsvtav1", "-preset", "6", "-crf", "40"]),
    "small": ("_720p", 720, H264),
}
# On an NVIDIA GPU: its codec and flags, at the CPU's quality.
ON_GPU = {
    "light": ("h264", ["-c:v", "h264_nvenc", *NVENC, "-cq", "33", "-maxrate", "8M", "-bufsize", "16M"]),
    "av1": ("av1", ["-c:v", "av1_nvenc", *NVENC, "-cq", "40"]),
    "small": ("h264", ["-c:v", "h264_nvenc", *NVENC, "-cq", "34", "-maxrate", "8M", "-bufsize", "16M"]),
}
TOLERANCE_S = 1.0
FOLDER = "reencoded"
# The copies' height, which the frames are cut at, the small one resized from them.
HEIGHT = 1440
# Beside a match's outputs: the camera its listed copies were cut by, which its hosted page draws on them with.
CAMERA = "copies_camera.json"


def paths(video: Path) -> dict[str, Path]:
    """Where each copy of `video` goes, in the FOLDER beside it."""
    return {key: video.parent / FOLDER / f"{video.stem}{suffix}.mp4" for key, (suffix, _, _) in COPIES.items()}


def part(path: Path) -> Path:
    return path.with_name(f"{path.stem}.part.mp4")


def encoding(key: str) -> list[str]:
    """ffmpeg's flags encoding the `key` copy: on the GPU when ffmpeg can there."""
    codec, flags = ON_GPU[key]
    return flags if decode.nvenc(codec) else COPIES[key][2]


def reading(video: Path, flags: tuple[str, ...]) -> list[str]:
    """ffmpeg's command sending `video`'s frames, FPS a second, as raw YUV 4:2:0, decoded with `flags`."""
    return ["ffmpeg", "-nostdin", "-v", "error", *flags, "-i", str(video), "-an", "-sn", "-dn", "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]


def writing(video: Path, size: tuple[int, int], made: dict[str, Path]) -> list[str]:
    """ffmpeg's command encoding the cut frames (raw YUV 4:2:0 of `size`, on its input) into the copies `made`, the
    sound taken from `video`."""
    small = COPIES["small"][1]
    graph = f"[0:v]split=3[light][av1][big];[big]scale=-2:{small}:flags=lanczos[small]"
    outputs = []
    for key in COPIES:
        outputs += ["-map", f"[{key}]", "-map", "1:a:0?", *encoding(key), *KEYFRAMES, "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(part(made[key]))]
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-", "-i", str(video), "-filter_complex", graph, *outputs]


def cut(frame: np.ndarray, size: tuple[int, int], out: tuple[int, int], view: np.ndarray) -> bytes:
    """A raw YUV 4:2:0 `frame` of `size` cut where `view` ([centre x, centre y, zoom], fractions of the picture) looks,
    at `out`, bicubic at sub-pixel precision."""
    (w, h), (ow, oh) = size, out
    x, y, zoom = view
    planes = [(frame[: w * h].reshape(h, w), 1), (frame[w * h : w * h * 5 // 4].reshape(h // 2, w // 2), 2), (frame[w * h * 5 // 4 :].reshape(h // 2, w // 2), 2)]
    done = []
    for plane, down in planes:
        pw, ph = w / down, h / down
        scale = ow / down / (pw / zoom)
        left, top = x * pw - pw / zoom / 2, y * ph - ph / zoom / 2
        # Pixel centres matched: a pixel's centre at k + 0.5 on both sides.
        move = np.float32([[scale, 0, (0.5 - left) * scale - 0.5], [0, scale, (0.5 - top) * scale - 0.5]])
        done.append(cv2.warpAffine(plane, move, (ow // down, oh // down), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE))
    return b"".join(p.tobytes() for p in done)


def duration(path: Path) -> float:
    run = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)]
    return float(subprocess.run(run, capture_output=True, text=True, check=True).stdout)


def height(path: Path) -> int | None:
    """The height of `path`'s picture, None if it is no video."""
    run = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height", "-of", "csv=p=0", str(path)]
    try:
        return int(subprocess.run(run, capture_output=True, text=True, check=True).stdout)
    except (subprocess.CalledProcessError, ValueError):
        return None


def current(key: str, path: Path) -> bool:
    """Whether `path` is the `key` copy as made today: there, at its height (a copy made before 1440p is not)."""
    return path.exists() and height(path) == COPIES[key][1]


def encode(video: Path, camera: list[list[float]], made: dict[str, Path], share: jobs.Share, flags: tuple[str, ...]) -> int:
    """The copies `made` (their parts) of `video` cut by `camera`, decoded with `flags`; the frames sent. RuntimeError
    when ffmpeg fails."""
    width, high = decode.size(video)
    size = (2 * round(HEIGHT * width / high / 2), HEIGHT)
    expected = max(1, round(duration(video) * FPS))
    told = jobs.every(expected, share)
    # Every frame's view at once; a frame past the duration probed takes the last.
    views = framing.camera_at(camera, np.arange(expected + FPS) / FPS)
    with tempfile.TemporaryFile() as read_errors, tempfile.TemporaryFile() as write_errors:
        reader = subprocess.Popen(reading(video, flags), stdout=subprocess.PIPE, stderr=read_errors)
        writer = subprocess.Popen(writing(video, size, made), stdin=subprocess.PIPE, stderr=write_errors)
        frame = np.empty(width * high * 3 // 2, np.uint8)
        sent = 0
        try:
            while reader.stdout.readinto(frame) == frame.nbytes:
                writer.stdin.write(cut(frame, (width, high), size, views[min(sent, len(views) - 1)]))
                told(min(sent, expected - 1))
                sent += 1
            writer.stdin.close()
        except BrokenPipeError:
            pass
        finally:
            reader.kill()
            reader.wait()
            writer.wait()
        for process, errors in ((reader, read_errors), (writer, write_errors)):
            if process.returncode and (process is writer or not sent):
                errors.seek(0)
                said = errors.read().decode(errors="replace").strip().splitlines()
                raise RuntimeError(said[-1] if said else f"ffmpeg: exit {process.returncode}")
    return sent


def make(video: Path, camera: list[list[float]], share: jobs.Share = jobs.quiet) -> dict[str, Path]:
    """The three copies of `video` cut by `camera` (`framing.camera_spans`), the share of its frames done told as it
    goes; RuntimeError if ffmpeg fails or one comes out cut short."""
    made = paths(video)
    (video.parent / FOLDER).mkdir(exist_ok=True)
    try:
        flags = decode.hardware(video)
        try:
            encode(video, camera, made, share, flags)
        except RuntimeError:
            # The GPU busy with other work may refuse another decoder.
            if not flags:
                raise
            encode(video, camera, made, share, ())
        expected = duration(video)
        for key, path in made.items():
            if abs(duration(part(path)) - expected) > TOLERANCE_S:
                raise RuntimeError(f"{part(path).name} lasts {duration(part(path)):.1f} s instead of {expected:.1f} s")
        for path in made.values():
            part(path).replace(path)
    finally:
        for path in made.values():
            part(path).unlink(missing_ok=True)
    return made


def record(match: Path, light: Path, camera: list[list[float]]) -> None:
    """The copies of `match` whose `light` one was just made cut by `camera` (CAMERA)."""
    files.write_text(match / CAMERA, json.dumps({"light": light.name, "size": light.stat().st_size, "camera": camera}, separators=(",", ":")) + "\n")


def recorded(match: Path, light: Path) -> list[list[float]] | None:
    """The camera the copies of `match` were cut by, if `light` is the copy made with them; None for copies made before
    16 Nov (the whole picture, which the page zoomed) or another one."""
    path = match / CAMERA
    if not path.exists() or not light.exists():
        return None
    saved = json.loads(path.read_text())
    return saved["camera"] if saved.get("light") == light.name and saved.get("size") == light.stat().st_size else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the lighter copies of a match's video for its hosted page, cut by the automatic zoom.")
    parser.add_argument("video", type=Path)
    parser.add_argument("camera", type=Path, help="The camera as framing.camera_spans writes it (JSON)")
    args = parser.parse_args()
    try:
        print("\n".join(map(str, make(args.video, json.loads(args.camera.read_text())).values())))
    except (RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
