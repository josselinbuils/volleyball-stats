"""Time and peak memory of the steps after the trackers on a match as long as a real one.

    uv run --group bench python benchmarks/scale.py build [--clip side_holdout] [--times 20]
    uv run --group bench python benchmarks/scale.py run

`build` repeats a clip's outputs (players, rallies, actions, net crossings) `--times` times one
after the other in outputs/scale/, with a tiny black video of the same length and noise for audio.
20 times side_holdout (10 min at 30 fps) holds the player rows of 2 hours at 50 fps. `run` runs
each step in its own process and prints its time and peak memory. The video is 64x36: the steps
reading it (teams, identity's embeddings, patched to random vectors) are timed without the 4K
decoding, which benchmarks/speed.py covers.

Results on the M4 Pro, 20 x side_holdout (3.8 million player rows, 43,000 identity pieces):

| step | time | peak memory |
| --- | --- | --- |
| whistles | 12 s | 2.3 GB (15.5 GB with the whole spectrum at once) |
| finish | 19 s | 4.1 GB |
| teams | 19 s | 3.1 GB |
| attribution | 11 s | 3.1 GB |
| identity | 48 s | 6.3 GB (over 20 GB, unfinished, with dense cannot-links) |
| web | 10 s | 0.6 GB (4.5 GB holding every row as text) |
| review | 2 s | 0.7 GB (4.0 GB holding every box as Python objects) |

ponytail: the players' rows are Python objects, ~0.8 KB each, 2.9 GB of the peaks above; numpy
columns would hold them in ~0.2 GB if a match ever needs it.
"""

import argparse
import csv
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

OUT = Path("outputs/scale")
VIDEO = OUT / "scale.mp4"
STEPS = ["whistles", "finish", "teams", "attribution", "identity", "web", "review"]


def tile(src: Path, dst: Path, times: int, frames: int, keys: dict[str, str]) -> None:
    """`src` CSV repeated `times` times, frames shifted by `frames` and tracks by 10,000 per copy;
    `keys` maps each column to "frame", "track" or "" (kept)."""
    with open(src) as f:
        rows = list(csv.DictReader(f))
    with open(dst, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for k in range(times):
            for r in rows:
                out = dict(r)
                for column, kind in keys.items():
                    if out.get(column):
                        out[column] = str(int(out[column]) + (k * frames if kind == "frame" else k * 10_000))
                writer.writerow(out)


def build(clip: str, times: int) -> None:
    src, video = Path(f"outputs/{clip}"), Path(f"data/{clip}.mp4")
    cap = cv2.VideoCapture(str(video))
    fps, frames = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    tile(src / "players.csv", OUT / "players.csv", times, frames, {"frame": "frame", "track": "track"})
    tile(src / "rallies.csv", OUT / "rallies.csv", times, frames, {"start_frame": "frame", "end_frame": "frame"})
    tile(src / "actions.csv", OUT / "actions.csv", times, frames, {"frame": "frame", "track": "track"})
    tile(src / "net.csv", OUT / "net.csv", times, frames, {"frame": "frame"})
    tile(src / "tracks.csv", OUT / "tracks.csv", times, frames, {"track": "track"})
    tile(src / "points.csv", OUT / "points.csv", times, frames, {"start_frame": "frame", "end_frame": "frame"})
    (OUT / "teams.json").write_text((src / "teams.json").read_text())
    seconds = times * frames / fps
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s=64x36:r={fps}:d={seconds}", "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:a=0.02:r=16000",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "32k", "-shortest", str(VIDEO)],
        check=True,
    )
    print(f"{times} x {clip}: {seconds / 3600:.1f} h at {fps:.2f} fps -> {OUT}")


def step(name: str) -> None:
    from volleyball_stats import attribution, identity, players, rallies, review, teams, web
    from volleyball_stats.court import Calibration

    fps = cv2.VideoCapture(str(VIDEO)).get(cv2.CAP_PROP_FPS)
    with open(OUT / "rallies.csv") as f:
        rally_rows = list(csv.DictReader(f))
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rally_rows]
    left = [int(r["left"]) if r.get("left") else None for r in rally_rows]
    if name == "whistles":
        found = rallies.whistles(rallies.read_audio(VIDEO))
        return print(f"{len(found)} whistles")
    if name == "web":
        calibration = Calibration(np.eye(3))
        data, samples = web.match_data(OUT, VIDEO, calibration)
        size = len(json.dumps(samples, separators=(",", ":"))) if samples else 0
        return print(f"{len(data['contacts'])} contacts, players.js {size / 1e6:.0f} MB")
    if name == "review":
        found, _ = review.Questions(OUT, fps).build(set())
        return print(f"{len(found)} questions")
    rows = attribution.read_players(OUT / "players.csv")
    if name == "finish":
        return print(f"{len(rows)} rows -> {len(players.finish(rows, fps))}")
    if name == "teams":
        found = teams.assign(VIDEO, rows, windows, fps)
        return print(f"{len(found.tracks)} tracks")
    if name == "attribution":
        with open(OUT / "actions.csv") as f:
            typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in csv.DictReader(f)]
        return print(f"{sum(t is not None for t in attribution.attribute(typed, rows, fps))} / {len(typed)} attributed")
    if name == "identity":
        rng = np.random.default_rng(0)

        def embed(video, rows, segments, cover, cache=None):
            v = rng.standard_normal((len(segments), identity.DIM))
            return v / np.linalg.norm(v, axis=1, keepdims=True), np.ones(len(segments))

        identity.embed = embed
        table = identity.run(OUT, VIDEO, rows, windows, left, fps)
        return print(f"{len(table)} segments")


def main() -> None:
    parser = argparse.ArgumentParser(description="Time and peak memory of the offline steps on a long match.")
    parser.add_argument("command", choices=["build", "run", *STEPS])
    parser.add_argument("--clip", default="side_holdout")
    parser.add_argument("--times", type=int, default=20)
    args = parser.parse_args()
    if args.command == "build":
        return build(args.clip, args.times)
    if args.command in STEPS:
        start = time.perf_counter()
        step(args.command)
        # Bytes on macOS, kilobytes on Linux.
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 if sys.platform == "darwin" else 1 / 1024)
        return print(f"| {args.command} | {time.perf_counter() - start:.0f} s | {peak / 1e9:.1f} GB |")
    print("| step | time | peak memory |\n| --- | --- | --- |")
    for name in STEPS:
        result = subprocess.run([sys.executable, __file__, name], capture_output=True, text=True)
        lines = [line for line in result.stdout.splitlines() if line.startswith("|")]
        print(lines[-1] if lines else f"| {name} | failed: {(result.stderr.strip().splitlines() or ['?'])[-1]} | |", flush=True)


if __name__ == "__main__":
    main()
