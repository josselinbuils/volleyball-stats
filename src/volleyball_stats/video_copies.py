"""The lighter copies of a match's video its hosted page plays, shorter than the match (`timeline.py`: the breaks faster,
the long pauses cut, the close calls held) and cut by the automatic zoom.

    uv run python -m volleyball_stats.video_copies VIDEO MADE_JSON

`light`, 1440p H.264, plays in browsers without AV1; `av1`, 1440p, plays in the others, smaller at the same quality;
`small`, 720p H.264, plays while the player is small. Each frame is the source's at the map's time, its sound rebuilt
piece by piece (`sound`), cut from the source where the automatic zoom looks
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

from volleyball_stats import decode, files, framing, jobs, timeline

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
# The copies' height, which the frames are cut at, the small one resized from them; their sound's rate.
HEIGHT = 1440
RATE = 48000
# Beside a match's outputs: how its listed copies were made, their time map and camera (`timeline.cut`), which its
# hosted page plays and draws on them by.
MADE = "copies_made.json"


def paths(video: Path) -> dict[str, Path]:
    """Where each copy of `video` goes, in the FOLDER beside it."""
    return {key: video.parent / FOLDER / f"{video.stem}{suffix}.mp4" for key, (suffix, _, _) in COPIES.items()}


def part(path: Path) -> Path:
    return path.with_name(f"{path.stem}.part.mp4")


def encoding(key: str) -> list[str]:
    """ffmpeg's flags encoding the `key` copy: on the GPU when ffmpeg can there."""
    codec, flags = ON_GPU[key]
    return flags if decode.nvenc(codec) else COPIES[key][2]


def reading(video: Path, flags: tuple[str, ...], spans: list[tuple[int, int]]) -> list[str]:
    """ffmpeg's command sending `video`'s frames of the `spans` (first and last index), as they are, as raw YUV 4:2:0,
    decoded with `flags`."""
    select = "+".join(f"between(n,{a},{b})" for a, b in spans)
    return ["ffmpeg", "-nostdin", "-v", "error", *flags, "-i", str(video), "-an", "-sn", "-dn", "-vf", f"select='{select}'", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]


def writing(sound: Path | None, size: tuple[int, int], made: dict[str, Path]) -> list[str]:
    """ffmpeg's command encoding the cut frames (raw YUV 4:2:0 of `size`, on its input) into the copies `made`, with
    `sound` (raw RATE stereo 16-bit) if any."""
    small = COPIES["small"][1]
    graph = f"[0:v]split=3[light][av1][big];[big]scale=-2:{small}:flags=lanczos[small]"
    heard = ["-f", "s16le", "-ar", str(RATE), "-ac", "2", "-i", str(sound)] if sound else []
    outputs = []
    for key in COPIES:
        outputs += ["-map", f"[{key}]", *(["-map", "1:a:0", "-c:a", "aac", "-b:a", "96k"] if sound else []), *encoding(key), *KEYFRAMES, "-movflags", "+faststart", str(part(made[key]))]
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-", *heard, "-filter_complex", graph, *outputs]


def cut(frame: np.ndarray, size: tuple[int, int], out: tuple[int, int], view: np.ndarray, shown: float = 1.0) -> bytes:
    """A raw YUV 4:2:0 `frame` of `size` cut where `view` ([centre x, centre y, zoom], fractions of the picture) looks,
    at `out`, bicubic at sub-pixel precision; `shown` under 1 fades it to black."""
    (w, h), (ow, oh) = size, out
    x, y, zoom = view
    planes = [(frame[: w * h].reshape(h, w), 1), (frame[w * h : w * h * 5 // 4].reshape(h // 2, w // 2), 2), (frame[w * h * 5 // 4 :].reshape(h // 2, w // 2), 2)]
    done = []
    for k, (plane, down) in enumerate(planes):
        pw, ph = w / down, h / down
        scale = ow / down / (pw / zoom)
        left, top = x * pw - pw / zoom / 2, y * ph - ph / zoom / 2
        # Pixel centres matched: a pixel's centre at k + 0.5 on both sides.
        move = np.float32([[scale, 0, (0.5 - left) * scale - 0.5], [0, scale, (0.5 - top) * scale - 0.5]])
        cut_plane = cv2.warpAffine(plane, move, (ow // down, oh // down), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if shown < 1:
            # Black: 16 in light, 128 in colour.
            black = 128 if k else 16
            cut_plane = (black + (cut_plane.astype(np.float32) - black) * shown).astype(np.uint8)
        done.append(cut_plane)
    return b"".join(p.tobytes() for p in done)


def sound(video: Path, pieces: list[list[float]], out: Path, share: jobs.Share = jobs.quiet) -> bool:
    """The copy's sound along `pieces` (`timeline.py`) in `out` (raw RATE stereo 16-bit): each piece's sound at its speed
    (ffmpeg's atempo: the voices' pitch kept), a held frame silent, faded through each cut and at each change of speed;
    False when `video` has none."""
    reader = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vn", "-ac", "2", "-ar", str(RATE), "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    read = 0
    total = len(pieces)
    with open(out, "wb") as f:
        for n, (start, end, at, until) in enumerate(pieces):
            first, last = round(start * RATE), round(end * RATE)
            # Up to the piece's start, left behind: the map only goes forward.
            while read < first:
                skipped = reader.stdout.read(4 * min(first - read, RATE))
                if not skipped:
                    break
                read += len(skipped) // 4
            taken = reader.stdout.read(4 * (last - first)) if last > first else b""
            read += len(taken) // 4
            samples = np.frombuffer(taken, np.int16).reshape(-1, 2)
            count = round(until * RATE) - round(at * RATE)
            if last <= first or not len(samples):
                piece = np.zeros((count, 2), np.float32)
            elif abs((end - start) - (until - at)) < 1e-6:
                piece = samples.astype(np.float32)
            else:
                # The map's rounding aside; atempo takes 0.5 at least.
                tempo = max(0.5, round((end - start) / (until - at), 4))
                stretched = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "2", "-i", "-", "-af", f"atempo={tempo}", "-f", "s16le", "-"], input=samples.tobytes(), capture_output=True, check=True).stdout
                piece = np.frombuffer(stretched, np.int16).reshape(-1, 2).astype(np.float32)
            piece = np.pad(piece, ((0, max(0, count - len(piece))), (0, 0)))[:count]
            # No click where the speed changes: 10 ms in and out; the cuts' fades.
            ramp = min(len(piece) // 2, RATE // 100)
            if ramp:
                piece[:ramp] *= np.linspace(0, 1, ramp)[:, None]
                piece[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
            piece *= timeline.fade(pieces, round(at * RATE) / RATE + np.arange(len(piece)) / RATE)[:, None]
            f.write(np.clip(piece, -32768, 32767).astype(np.int16).tobytes())
            share((n + 1) / total)
    reader.kill()
    reader.wait()
    return read > 0


def duration(path: Path) -> float:
    return float(decode.probe(path, "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", check=True))


# Each file's height by its path, with the size and time it had: the Site tab asks it on every look.
_heights: dict[str, tuple[tuple[int, int], int | None]] = {}


def height(path: Path) -> int | None:
    """The height of `path`'s picture, None if it is no video."""
    stat = path.stat()
    stamp = (stat.st_size, stat.st_mtime_ns)
    known = _heights.get(str(path))
    if known and known[0] == stamp:
        return known[1]
    try:
        found = int(decode.probe(path, "-select_streams", "v:0", "-show_entries", "stream=height", "-of", "csv=p=0", check=True))
    except (subprocess.CalledProcessError, ValueError):
        found = None
    _heights[str(path)] = (stamp, found)
    return found


def current(key: str, path: Path) -> bool:
    """Whether `path` is the `key` copy as made today: there, at its height (a copy made before 1440p is not)."""
    return path.exists() and height(path) == COPIES[key][1]


def nearest(times: np.ndarray, at: np.ndarray) -> np.ndarray:
    """The index of the frame of `times` (sorted) nearest each of `at`."""
    k = np.clip(np.searchsorted(times, at), 1, len(times) - 1)
    return np.where(np.abs(times[k - 1] - at) <= np.abs(times[k] - at), k - 1, k)


def read_spans(firsts: np.ndarray, lasts: np.ndarray) -> list[tuple[int, int]]:
    """The frames' spans (first, last) from the pieces' own, those touching or overlapping one."""
    out: list[tuple[int, int]] = []
    for a, b in zip(firsts.tolist(), lasts.tolist()):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def encode(video: Path, made_by: dict, made: dict[str, Path], heard: Path | None, share: jobs.Share, flags: tuple[str, ...]) -> int:
    """The copies `made` (their parts) of `video` along `made_by` (`timeline.cut`: its map and camera) with the sound
    `heard`, decoded with `flags`; the frames sent. RuntimeError when ffmpeg fails."""
    width, high = decode.size(video)
    size = (2 * round(HEIGHT * width / high / 2), HEIGHT)
    pieces = made_by["map"] or [[0.0, duration(video), 0.0, duration(video)]]
    times = decode.timestamps(video)
    count = max(1, int(pieces[-1][3] * FPS))
    told = jobs.every(count, share)
    at = np.arange(count) / FPS
    # The source frame each frame of the copy shows (the nearest), where its camera looks, and how much of it a cut's fade
    # leaves; the frames read, those of the pieces' spans of the source.
    wanted = nearest(times, timeline.to_source(pieces, at))
    views = framing.camera_at(made_by["camera"], at)
    shown = timeline.fade(pieces, at)
    spans = read_spans(nearest(times, np.array([p[0] for p in pieces])), nearest(times, np.array([p[1] for p in pieces])))
    with tempfile.TemporaryFile() as read_errors, tempfile.TemporaryFile() as write_errors:
        reader = decode.popen(reading(video, flags, spans), stderr=read_errors)
        writer = decode.popen(writing(heard, size, made), "stdin", stderr=write_errors)
        delivered = (k for a, b in spans for k in range(a, b + 1))
        frame = np.empty(width * high * 3 // 2, np.uint8)
        current, sent = -1, 0
        try:
            for n in range(count):
                while current < wanted[n]:
                    if reader.stdout.readinto(frame) != frame.nbytes:
                        break
                    current = next(delivered)
                if current < 0:
                    break
                writer.stdin.write(cut(frame, (width, high), size, views[n], float(shown[n])))
                told(n)
                sent += 1
            writer.stdin.close()
        except BrokenPipeError:
            pass
        finally:
            reader.kill()
            reader.wait()
            writer.wait()
        for process, errors in ((reader, read_errors), (writer, write_errors)):
            if process.returncode and (process is writer or not sent) and process.returncode != -9:
                errors.seek(0)
                said = errors.read().decode(errors="replace").strip().splitlines()
                raise RuntimeError(said[-1] if said else f"ffmpeg: exit {process.returncode}")
    return sent


def make(video: Path, made_by: dict, share: jobs.Share = jobs.quiet) -> dict[str, Path]:
    """The three copies of `video` made along `made_by` (`timeline.cut`: their time map and camera; the whole video
    without a map), the share done told as it goes; RuntimeError if ffmpeg fails or one comes out cut short."""
    made = paths(video)
    (video.parent / FOLDER).mkdir(exist_ok=True)
    pieces = made_by["map"] or [[0.0, duration(video), 0.0, duration(video)]]
    # Its parts' shares: the sound read through and stretched, then the frames.
    part_of = jobs.parts(share, {"sound": 1.0, "frames": 9.0})
    with tempfile.TemporaryDirectory() as folder:
        heard = Path(folder) / "sound.raw"
        if not sound(video, pieces, heard, part_of("sound")):
            heard = None
        try:
            flags = decode.hardware(video)
            try:
                encode(video, {**made_by, "map": pieces}, made, heard, part_of("frames"), flags)
            except RuntimeError:
                # The GPU busy with other work may refuse another decoder.
                if not flags:
                    raise
                encode(video, {**made_by, "map": pieces}, made, heard, part_of("frames"), ())
            expected = pieces[-1][3]
            for key, path in made.items():
                if abs(duration(part(path)) - expected) > TOLERANCE_S:
                    raise RuntimeError(f"{part(path).name} lasts {duration(part(path)):.1f} s instead of {expected:.1f} s")
            for path in made.values():
                part(path).replace(path)
        finally:
            for path in made.values():
                part(path).unlink(missing_ok=True)
    return made


def record(match: Path, light: Path, made: dict) -> None:
    """The copies of `match` whose `light` one was just `made` so (`timeline.cut`: MADE)."""
    files.write_text(match / MADE, json.dumps({"light": light.name, "size": light.stat().st_size, **made}, separators=(",", ":")) + "\n")


def recorded(match: Path, light: Path) -> dict | None:
    """How the copies of `match` were made (`timeline.cut`), if `light` is the copy made with them; None for copies made
    before 16 Nov (the whole picture, which the page zoomed) or another one."""
    path = match / MADE
    if not path.exists() or not light.exists():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    return {"map": saved["map"], "camera": saved["camera"]} if saved.get("light") == light.name and saved.get("size") == light.stat().st_size and "map" in saved else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the lighter copies of a match's video for its hosted page, cut by the automatic zoom.")
    parser.add_argument("video", type=Path)
    parser.add_argument("made", type=Path, help="How to make them: {map, camera} as timeline.cut gives them (JSON)")
    args = parser.parse_args()
    try:
        print("\n".join(map(str, make(args.video, json.loads(args.made.read_text(encoding="utf-8"))).values())))
    except (RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
