"""Contact attribution: the player track that touched the ball at each typed contact.

The toucher is the track of the contact's side (actions.py; a block's side is the blocker's) whose
box is nearest to the ball at the contact frame, in box heights so near and far players compare.
A contact played above the head (serve, attack, block) may lie up to an arm above the box: the
detector leaves the blurred hitting arm out. A track the detector drops for a few frames around the
contact (blur, a teammate in front) stays a candidate, its box interpolated over the gap. Floor and
net contacts have no player. See benchmarks/attribution/README.md for the numbers behind the
constants.

    uv run python -m volleyball_stats.attribution ACTIONS_CSV PLAYERS_CSV --fps FPS [--out DIR]
"""

import argparse
import csv
from pathlib import Path

import numpy as np

from volleyball_stats.actions import Typed
from volleyball_stats.players import Row

NO_PLAYER = {"floor", "net"}
ABOVE_HEAD = {"serve", "attack", "block"}
# Box heights the ball may be above an above-the-head toucher's box.
REACH = 0.5
# Seconds a track may be missing on each side of the contact frame and stay a candidate.
GAP_S = 0.17

Box = tuple[float, float, float, float]


def read_players(path: Path) -> list[Row]:
    """Rows of a CSV written by players.write_csv."""
    with open(path) as f:
        return [
            Row(int(r["frame"]), int(r["track"]), tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2")), float(r["conf"]),
                (float(r["feet_x"]), float(r["feet_y"])), (float(r["court_x"]), float(r["court_y"])), r["team"])
            for r in csv.DictReader(f)
        ]


def distance(ball: tuple[float, float], box: Box, reach: float = 0.0) -> float:
    """Ball to box in box heights, 0 inside; the box reaches `reach` heights above its top."""
    x1, y1, x2, y2 = box
    h = y2 - y1
    return float(np.hypot(max(0, x1 - ball[0], ball[0] - x2), max(0, y1 - reach * h - ball[1], ball[1] - y2))) / h


def box_at(boxes: dict[int, Box], frame: int, gap: int) -> Box | None:
    """A track's box at `frame`: its own, else interpolated between its nearest boxes within `gap`
    frames, else the nearest one; None when it has none that close."""
    if frame in boxes:
        return boxes[frame]
    before = next((f for f in range(frame - 1, frame - gap - 1, -1) if f in boxes), None)
    after = next((f for f in range(frame + 1, frame + gap + 1) if f in boxes), None)
    if before is None or after is None:
        return boxes.get(before if after is None else after)
    a, b = np.array(boxes[before]), np.array(boxes[after])
    return tuple((a + (b - a) * (frame - before) / (after - before)).tolist())


def tracks(rows: list[Row]) -> dict[int, tuple[str, dict[int, Box]]]:
    """Track -> (team, frame -> box)."""
    out: dict[int, tuple[str, dict[int, Box]]] = {}
    for r in rows:
        out.setdefault(r.track, (r.team, {}))[1][r.frame] = r.box
    return out


def attribute(typed: list[Typed], rows: list[Row], fps: float) -> list[int | None]:
    """The track that touched each contact, None for the floor, the net or no candidate."""
    by_track, gap = tracks(rows), round(GAP_S * fps)
    out: list[int | None] = []
    # ponytail: scans every track per contact, O(tracks × contacts); index the tracks by frame if a
    # whole match is slow.
    for frame, x, y, kind, side in typed:
        reach = REACH if kind in ABOVE_HEAD else 0.0
        candidates = [(track, box) for track, (team, boxes) in by_track.items() if team == side and (box := box_at(boxes, frame, gap))]
        best = min(candidates, key=lambda c: (distance((x, y), c[1], reach), distance((x, y), c[1])), default=None)
        out.append(None if kind in NO_PLAYER or best is None else best[0])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute each typed contact to a player track.")
    parser.add_argument("actions", type=Path, help="frame,x,y,type,side CSV from actions.py")
    parser.add_argument("players", type=Path, help="Player tracks CSV from players.py")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    with open(args.actions) as f:
        typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in csv.DictReader(f)]
    found = attribute(typed, read_players(args.players), args.fps)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.actions.stem.removesuffix('_actions')}_attribution.csv"
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([["frame", "x", "y", "type", "side", "track"], *([*t, "" if k is None else k] for t, k in zip(typed, found))])
    print(f"{sum(k is not None for k in found)}/{len(typed)} contacts attributed -> {path}")


if __name__ == "__main__":
    main()
