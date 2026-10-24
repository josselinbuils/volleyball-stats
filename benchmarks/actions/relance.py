"""Score the relance rule (actions.mark_relances) on the labelled third touches.

    uv run python benchmarks/actions/relance.py VIDEO:TRACK:GROUND_TRUTH ...

Every labelled touch counted 3rd or later on its side (blocks, serves, floor and net contacts left
out) goes through the rule as an attack, at the ball position of the interpolated track; the table
crosses its label with the rule's answer.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from volleyball_stats import actions, contacts

FPS = 29.97


def third_touches(path: Path) -> list[tuple[int, str]]:
    rallies: dict[str, list[dict]] = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            rallies[row["rally"]].append(row)
    found = []
    for rows in rallies.values():
        crossings = sorted(int(r["frame"]) for r in rows if r["event"] == "net")
        touches = crossed = 0
        for row in sorted((r for r in rows if r["event"] == "contact"), key=lambda r: int(r["frame"])):
            frame = int(row["frame"])
            now = sum(c <= frame for c in crossings)
            if now > crossed:
                touches, crossed = 0, now
            if row["type"] in ("block", "serve", "floor", "net"):
                continue
            touches += 1
            if touches >= 3:
                found.append((frame, row["type"] or "unclear"))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", help="VIDEO:TRACK:GROUND_TRUTH")
    args = parser.parse_args()
    counts: Counter[tuple[str, str]] = Counter()
    for clip in args.clips:
        video, track_path, truth = map(Path, clip.split(":"))
        track = contacts.interpolate(contacts.read_track(track_path))
        touches = third_touches(truth)
        typed = [(f, round(track[f, 0]), round(track[f, 1]), "attack", "") for f, _ in touches]
        marked = {f: kind for f, _, _, kind, _ in actions.mark_relances(video, typed, FPS)}
        for frame, label in touches:
            counts[label, marked[frame]] += 1
            print(f"{video.stem:13} {frame:6} labelled {label:8} -> {marked[frame]}")
    print("\nlabel      attack  relance")
    for label in sorted({label for label, _ in counts}):
        print(f"{label:9} {counts[label, 'attack']:7} {counts[label, 'relance']:8}")


if __name__ == "__main__":
    main()
