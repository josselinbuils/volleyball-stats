"""The lighter copies of a match's video its hosted page plays, on the source's timeline.

    uv run python -m volleyball_stats.video_copies VIDEO

`light`, 1440p H.264, plays in browsers without AV1; `av1`, 1440p, plays in the others, smaller at the
same quality; `small`, 720p H.264, plays while the player is small. 1440p for the automatic zoom, which enlarges the
picture 1.4x: VMAF zoomed 89.6 against 85.8 at 1080p for AV1, 86.8 against 82.1 for H.264 (docs/hosting.md). Makes
those missing or at another height, in `reencoded/` beside the source, from one reading of it: decoding 4K costs more
than the encoders' share. A copy only appears once whole.

Encoded on an NVIDIA GPU when ffmpeg can (NVENC), else on the CPU. On 18 s of the Avia match, VMAF whole / zoomed 1.37x /
1.8x (docs/hosting.md): H.264 1440p 90.9 / 88.2 / 83.3 at 3.0 Mb/s against x264's 90.3 / 86.8 / 80.9 at 3.3; 720p 80.1 /
71.9 / 59.2 at 0.73 against 79.7 / 71.0 / 57.4 at 0.74; AV1 92.1 / 89.6 / 85.1 at 2.8 against SVT-AV1's 92.0 / 89.6 /
84.9 at 1.55 (1.8 times larger). The three from a minute of 4K on the RTX 5080: 29 s against 123.
ponytail: the resize stays on the CPU (scale_cuda's lanczos lost 0.5-1.7 points, 18 s a minute); VideoToolbox not tried.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from volleyball_stats import decode

H264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-maxrate", "8M", "-bufsize", "16M"]
NVENC = ["-preset", "p7", "-tune", "hq", "-multipass", "fullres", "-rc", "vbr", "-b:v", "0"]
# Every 2 s: the jumps between clips do not freeze.
KEYFRAMES = ["-g", "50"]
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


def paths(video: Path) -> dict[str, Path]:
    """Where each copy of `video` goes, in the FOLDER beside it."""
    return {key: video.parent / FOLDER / f"{video.stem}{suffix}.mp4" for key, (suffix, _, _) in COPIES.items()}


def part(path: Path) -> Path:
    return path.with_name(f"{path.stem}.part.mp4")


def encoding(key: str) -> list[str]:
    """ffmpeg's flags encoding the `key` copy: on the GPU when ffmpeg can there."""
    codec, flags = ON_GPU[key]
    return flags if decode.nvenc(codec) else COPIES[key][2]


def command(video: Path, keys: list[str], flags: tuple[str, ...] = ()) -> list[str]:
    """ffmpeg's command writing the `keys` copies of `video` from one decoding."""
    labels = [f"[c{k}]" for k in range(len(keys))]
    scaled = ";".join(f"{label}scale=-2:{COPIES[key][1]}:flags=lanczos[v{k}]" for k, (key, label) in enumerate(zip(keys, labels)))
    outputs = []
    for k, key in enumerate(keys):
        outputs += ["-map", f"[v{k}]", "-map", "0:a:0?", *encoding(key), *KEYFRAMES, "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(part(paths(video)[key]))]
    return ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *flags, "-i", str(video), "-filter_complex", f"[0:v]fps=25,format=yuv420p,split={len(keys)}{''.join(labels)};{scaled}", *outputs]


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


def make(video: Path, kept: dict[str, Path] | None = None) -> dict[str, Path]:
    """The copies of `video`, the `kept` ones still current taken as they are, the others made; RuntimeError if ffmpeg
    fails or one comes out cut short."""
    made = paths(video) | {key: path for key, path in (kept or {}).items() if current(key, path)}
    missing = [key for key, path in made.items() if not current(key, path)]
    if not missing:
        return made
    parts = [part(made[key]) for key in missing]
    (video.parent / FOLDER).mkdir(exist_ok=True)
    try:
        run = subprocess.run(command(video, missing, decode.hardware(video)), capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError((run.stderr.strip().splitlines() or [f"ffmpeg: exit {run.returncode}"])[-1])
        expected = duration(video)
        for path in parts:
            if abs(duration(path) - expected) > TOLERANCE_S:
                raise RuntimeError(f"{path.name} lasts {duration(path):.1f} s instead of {expected:.1f} s")
        for key in missing:
            part(made[key]).replace(made[key])
    finally:
        for path in parts:
            path.unlink(missing_ok=True)
    return made


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the lighter copies of a match's video for its hosted page.")
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    try:
        print("\n".join(map(str, make(args.video).values())))
    except (RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
