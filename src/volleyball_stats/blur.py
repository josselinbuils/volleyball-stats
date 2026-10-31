"""A copy of the match video with the players of chosen teams blurred, for publishing: the pipeline
and the review page keep working on the original.

Each tracked player of a blurred team (players.csv, teams from tracks.csv) is pixelated over their
box, enlarged by GROW, carried across tracking gaps of up to GAP_S and held HOLD_S before and after
their track and either side of a longer gap, so a player the tracker lost for a moment stays hidden. People never tracked (the
bench, the public, a player standing off the court) are not blurred. The video is decoded and
encoded by ffmpeg, on an NVIDIA GPU when it can.

    uv run python -m volleyball_stats.blur outputs/VIDEO --video VIDEO --teams 2 [--out OUT.mp4]
"""

import argparse
import csv
import subprocess
from collections.abc import Iterable
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode

# GAP_S is players.MAX_GAP_S: the longest gap stitched inside a track.
GROW, GAP_S, HOLD_S = 0.2, 2.0, 0.5
# Pixel blocks a tenth of the box's height: a face is a block or two.
BLOCKS = 10

Box = tuple[float, float, float, float]


def boxes(rows: Iterable[tuple[int, int, Box]], fps: float) -> dict[int, list[Box]]:
    """The boxes to blur per frame from (frame, track, box) rows: each track's, carried linearly across
    gaps of up to GAP_S, and held HOLD_S before its first row, after its last and either side of a
    longer gap."""
    tracks: dict[int, list[tuple[int, Box]]] = {}
    for frame, track, box in rows:
        tracks.setdefault(track, []).append((frame, box))
    gap, hold = round(GAP_S * fps), round(HOLD_S * fps)
    out: dict[int, list[Box]] = {}
    for seen in tracks.values():
        seen.sort()
        for f in range(max(0, seen[0][0] - hold), seen[0][0]):
            out.setdefault(f, []).append(seen[0][1])
        for (a, box_a), (b, box_b) in zip(seen, seen[1:] + [(seen[-1][0] + hold + 1, seen[-1][1])]):
            if b - a <= gap:
                for f in range(a, b):
                    w = (f - a) / (b - a)
                    out.setdefault(f, []).append(tuple(p + w * (q - p) for p, q in zip(box_a, box_b)))
                continue
            for f in range(a, a + hold + 1):
                out.setdefault(f, []).append(box_a)
            for f in range(b - hold, b):
                out.setdefault(f, []).append(box_b)
    return out


def pixelate(image: np.ndarray, frame_boxes: list[Box]) -> np.ndarray:
    """`image` with each box, enlarged by GROW, in blocks of BLOCKS per box height."""
    height, width = image.shape[:2]
    for x1, y1, x2, y2 in frame_boxes:
        gx, gy = (x2 - x1) * GROW / 2, (y2 - y1) * GROW / 2
        left, top, right, bottom = max(0, round(x1 - gx)), max(0, round(y1 - gy)), min(width, round(x2 + gx)), min(height, round(y2 + gy))
        if right - left < 2 or bottom - top < 2:
            continue
        block = max(2, (bottom - top) // BLOCKS)
        part = image[top:bottom, left:right]
        small = cv2.resize(part, (max(1, part.shape[1] // block), max(1, part.shape[0] // block)), interpolation=cv2.INTER_AREA)
        image[top:bottom, left:right] = cv2.resize(small, (part.shape[1], part.shape[0]), interpolation=cv2.INTER_NEAREST)
    return image


def encoder(video: Path) -> list[str]:
    """ffmpeg's video encoding: NVIDIA's hardware encoder beside its decoder, else x264."""
    if decode.cuda(video):
        listed = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if "h264_nvenc" in listed:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]


def write(match: Path, video: Path, teams: set[int], out: Path) -> None:
    """`video` with the players of `teams` pixelated into `out` (H.264, the original's sound)."""
    with open(match / "tracks.csv") as f:
        blurred = {int(r["track"]) for r in csv.DictReader(f) if int(r["team"]) in teams}
    table = np.loadtxt(match / "players.csv", delimiter=",", skiprows=1, usecols=(0, 1, 3, 4, 5, 6), ndmin=2)
    cap = cv2.VideoCapture(str(video))
    fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    width, height = decode.size(video)
    # Boxes tracked on another copy of the video (4K boxes on a 1080p export) would miss the players.
    if len(table) and (table[:, 4].max() > width + 1 or table[:, 5].max() > height + 1 or table[:, 0].max() > count + fps):
        raise ValueError(f"{match / 'players.csv'} was tracked on another video than {video} (larger frames or more of them)")
    hidden = boxes(((int(r[0]), int(r[1]), tuple(r[2:])) for r in table if int(r[1]) in blurred), fps)
    command = [
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-i", str(video), "-map", "0:v", "-map", "1:a?", *encoder(video), "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out),
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for index, image in enumerate(decode.frames(video, width)):
            process.stdin.write(pixelate(image, hidden.get(index, [])).tobytes())
    finally:
        process.stdin.close()
        process.wait()
    if process.returncode:
        raise RuntimeError(f"ffmpeg could not encode {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy a match video with the players of some teams blurred.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO), run with --players")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--teams", default="1,2", help="Teams to blur, 1, 2 or 1,2 (default: both)")
    parser.add_argument("--out", type=Path, help="Defaults to MATCH/VIDEO_blurred.mp4")
    args = parser.parse_args()
    out = args.out or args.match / f"{args.video.stem}_blurred.mp4"
    try:
        write(args.match, args.video, {int(t) for t in args.teams.split(",")}, out)
    except ValueError as error:
        parser.error(str(error))
    print(out)


if __name__ == "__main__":
    main()
