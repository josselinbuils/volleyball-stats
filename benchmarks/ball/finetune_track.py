"""Track the ball over a match's video with other weights, writing a ball.csv exactly as the pipeline does (`match.track`).

    uv run python benchmarks/ball/finetune_track.py MATCH OUT.csv [--weights PATH] [--threshold 0.2] [--first F --count N]

The whole video goes in parts that resume after a crash. Without --weights the pretrained model runs (to check the script reproduces the stored ball.csv). With --first/--count
only that stretch is tracked, and the rows keep their numbers from the stretch's start (frame 0 = F), for `--check`.
"""

import argparse
import csv
import sys
from pathlib import Path

from volleyball_stats import ball, decode, match

MATCHES = Path("outputs/matches")
CHUNK = 20000


def chunked(video: Path, fps: float, total: int, out: Path) -> None:
    """The whole video in parts of CHUNK frames (each decoded 2 frames before and after its own, so every frame has all its
    windows, as in one pass), kept beside `out`: a part that exists is not tracked again. Then the parts joined."""
    parts = out.with_suffix(".parts")
    parts.mkdir(exist_ok=True)
    whole = decode.frames
    for a in range(0, total, CHUNK):
        part = parts / f"{a}.csv"
        if part.exists():
            continue
        first, n = max(0, a - 2), min(CHUNK, total - a)
        decode.frames = lambda v, width=decode.WIDTH, first=first, n=n: decode.piped(v, *decode.scaled(*decode.size(v), width), first=first, count=n + (a - first) + 2)
        match.track(video, None, fps, part.with_suffix(".tmp"), None, 0)
        decode.frames = whole
        with part.with_suffix(".tmp").open() as f:
            rows = list(csv.reader(f))[1:]
        keep = rows[a - first : a - first + n]
        with part.with_suffix(".tmp").open("w", newline="") as f:
            csv.writer(f).writerows([[a + i, *r[1:]] for i, r in enumerate(keep)])
        part.with_suffix(".tmp").replace(part)
        print(f"part {a} done", flush=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "visible", "x", "y"])
        for a in range(0, total, CHUNK):
            with (parts / f"{a}.csv").open() as g:
                w.writerows(csv.reader(g))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("out", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--threshold", type=float, default=ball.THRESHOLD[1])
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--check", action="store_true", help="Compare the written stretch with the match's stored ball.csv")
    args = parser.parse_args()
    import json

    video = Path(json.loads((MATCHES / args.match / "source.json").read_text())["video"])
    load = ball.load_model
    if args.weights:
        ball.load_model = lambda device, path=args.weights: load(device, path)
    ball.THRESHOLD[1] = args.threshold
    if args.count:
        decode.frames = lambda v, width=decode.WIDTH: decode.piped(v, *decode.scaled(*decode.size(v), width), first=args.first, count=args.count)
    import cv2

    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    total = args.count or int(cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_COUNT))
    if args.count:
        match.track(video, None, fps, args.out, None, total)
    else:
        chunked(video, fps, total, args.out)
    if args.check:
        with (MATCHES / args.match / "ball.csv").open() as f, args.out.open() as g:
            old = {int(r["frame"]): r for r in csv.DictReader(f)}
            new = list(csv.DictReader(g))
        same = near = 0
        for r in new:
            o = old[int(r["frame"]) + args.first]
            if (o["visible"], o["x"], o["y"]) == (r["visible"], r["x"], r["y"]):
                same += 1
            elif o["visible"] == r["visible"] == "1" and abs(int(o["x"]) - int(r["x"])) <= 8 and abs(int(o["y"]) - int(r["y"])) <= 8:
                near += 1
        print(f"{len(new)} frames: {same} identical, {near} within 8 px, {len(new) - same - near} different; visible {sum(r['visible'] == '1' for r in new)} against {sum(old[int(r['frame']) + args.first]['visible'] == '1' for r in new)}")


if __name__ == "__main__":
    sys.exit(main())
