"""The lighter copies of a match's video its hosted page plays, on the source's timeline.

    uv run python -m volleyball_stats.video_copies VIDEO

`light`, 1080p H.264, plays in browsers without AV1; `av1`, 1080p, plays in the others, smaller at the
same quality; `small`, 720p H.264, plays while the player is small. Makes those missing, from one reading
of the source: decoding 4K costs more than the encoders' share. A copy only appears once whole.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from volleyball_stats import decode

H264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-maxrate", "5M", "-bufsize", "10M"]
# Every 2 s: the jumps between clips do not freeze.
KEYFRAMES = ["-g", "50"]
COPIES = {
    "light": ("_1080p", 1080, H264),
    "av1": ("_av1", 1080, ["-c:v", "libsvtav1", "-preset", "6", "-crf", "40"]),
    "small": ("_720p", 720, H264),
}
TOLERANCE_S = 1.0


def paths(video: Path) -> dict[str, Path]:
    """Where each copy of `video` goes, beside it."""
    return {key: video.with_name(f"{video.stem}{suffix}.mp4") for key, (suffix, _, _) in COPIES.items()}


def part(path: Path) -> Path:
    return path.with_name(f"{path.stem}.part.mp4")


def command(video: Path, keys: list[str], flags: tuple[str, ...] = ()) -> list[str]:
    """ffmpeg's command writing the `keys` copies of `video` from one decoding."""
    labels = [f"[c{k}]" for k in range(len(keys))]
    scaled = ";".join(f"{label}scale=-2:{COPIES[key][1]}:flags=lanczos[v{k}]" for k, (key, label) in enumerate(zip(keys, labels)))
    outputs = []
    for k, key in enumerate(keys):
        outputs += ["-map", f"[v{k}]", "-map", "0:a:0?", *COPIES[key][2], *KEYFRAMES, "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(part(paths(video)[key]))]
    return ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-stats", "-y", *flags, "-i", str(video), "-filter_complex", f"[0:v]fps=25,format=yuv420p,split={len(keys)}{''.join(labels)};{scaled}", *outputs]


def duration(path: Path) -> float:
    run = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)]
    return float(subprocess.run(run, capture_output=True, text=True, check=True).stdout)


def make(video: Path) -> dict[str, Path]:
    """The copies of `video`, making those missing; RuntimeError if one comes out cut short."""
    made = paths(video)
    missing = [key for key, path in made.items() if not path.exists()]
    if not missing:
        return made
    parts = [part(made[key]) for key in missing]
    try:
        subprocess.run(command(video, missing, decode.hardware(video)), check=True)
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
