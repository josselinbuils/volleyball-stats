"""Contact attribution: the player track that touched the ball at each typed contact.

The toucher is the track of the contact's side (actions.py; a block's side is the blocker's) whose
box is nearest to the ball at the contact frame, in box heights so near and far players compare.
A contact played above the head (serve, attack, block) may lie up to an arm above the box: the
detector leaves the blurred hitting arm out. A track the detector drops for a few frames around the
contact (blur, a teammate in front) stays a candidate, its box interpolated over the gap, unless its
feet stand clearly on the other side of the net then: a track that swapped players across the net.
Floor and net contacts have no player. Two candidates about as near the ball make the pick a doubt,
asked in the review. See benchmarks/attribution/README.md for the numbers behind the constants.

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
# A candidate whose feet stand over SIDE_M meters past the net on the other side at the contact
# frame is out: its track kept the side of the player it followed first.
SIDE_M = 0.5
# A next candidate under DOUBT box heights farther from the ball than the toucher makes a doubt.
DOUBT = 0.05

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


def court_x(xs: dict[int, float], frame: int, gap: int) -> float | None:
    """A track's feet court x at `frame`, else at its nearest frame within `gap`."""
    for d in range(gap + 1):
        for f in (frame - d, frame + d):
            if f in xs:
                return xs[f]
    return None


def ranked(typed: list[Typed], rows: list[Row], fps: float) -> list[list[tuple[float, float, int]]]:
    """Each contact's candidates, nearest first: (distance with the reach, plain distance, track);
    none for the floor and the net."""
    by_track, gap = tracks(rows), round(GAP_S * fps)
    feet: dict[int, dict[int, float]] = {}
    for r in rows:
        feet.setdefault(r.track, {})[r.frame] = r.court[0]
    out = []
    # ponytail: scans every track per contact, O(tracks × contacts); index the tracks by frame if a
    # whole match is slow.
    for frame, x, y, kind, side in typed:
        reach = REACH if kind in ABOVE_HEAD else 0.0
        found = []
        for track, (team, boxes) in by_track.items():
            box = box_at(boxes, frame, gap) if team == side and kind not in NO_PLAYER else None
            at = None if box is None else court_x(feet[track], frame, gap)
            if box is not None and not (at is not None and (at > SIDE_M if side == "left" else at < -SIDE_M)):
                found.append((distance((x, y), box, reach), distance((x, y), box), track))
        out.append(sorted(found))
    return out


def gap_to_next(candidates: list[tuple[float, float, int]]) -> float | None:
    """Box heights between the toucher's distance to the ball and the next candidate's; None alone."""
    return candidates[1][0] - candidates[0][0] if len(candidates) > 1 else None


def attribute(typed: list[Typed], rows: list[Row], fps: float) -> list[int | None]:
    """The track that touched each contact, None for the floor, the net or no candidate."""
    return [c[0][2] if c else None for c in ranked(typed, rows, fps)]


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
