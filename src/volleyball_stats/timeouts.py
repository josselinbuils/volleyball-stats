"""Timeouts: the breaks inside a set when the court empties or play stops for long, which neither does between normal points.

`timeouts.csv` holds what the players show, rewritten by each run; `timeouts.json` the owner's
corrections from the review's Match tab, in frames so that a rerun moving the rallies keeps them.

This also finds an injury or a long pause: the owner removes those. The team that called a timeout is
not found, the owner picks it.

    uv run python -m volleyball_stats.timeouts outputs/matches/MATCH --fps 50
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from volleyball_stats import files

DETECTED = "timeouts.csv"
ANSWERS = "timeouts.json"
# Feet this close to the court's centre, in meters (the court is 18 x 9), are on it.
COURT_X, COURT_Y = 9.5, 5.0
MAX_ON_COURT = 6
STEP_S = 0.5
# Seconds near-empty: 43-80 s for the timeouts of two matches, 7 s at most for 262 of their 268 gaps.
MIN_EMPTY_S = 30.0
# A gap this long is a timeout or something exceptional, the court full or not (the owner's rule). Shorter
# with a full court is mostly a rally missed: 8 of 8 gaps of 39-60 s showed players in play.
MIN_GAP_S = 70.0
# Longer is no timeout: 308 s on the second match, after its last point.
MAX_GAP_S = 180.0
# An added timeout with no gap around it to fit.
ADDED_S = 30.0


def on_court(players: Path, step: int) -> Counter:
    """Players on the court at each `step`-th frame of a `players.csv`."""
    counts: Counter = Counter()
    with players.open() as f:
        columns = next(f).strip().split(",")
        frame, x, y = columns.index("frame"), columns.index("court_x"), columns.index("court_y")
        for line in f:
            row = line.rstrip("\n").split(",")
            at = int(row[frame])
            if at % step == 0 and row[x] and row[y] and abs(float(row[x])) <= COURT_X and abs(float(row[y])) <= COURT_Y:
                counts[at] += 1
    return counts


def read_rallies(path: Path) -> list[tuple[int, int, int]]:
    """Each rally's start and end frames and set, from a `rallies.csv`."""
    with path.open() as f:
        return [(int(r["start_frame"]), int(r["end_frame"]), int(r["set"] or 0)) for r in csv.DictReader(f)]


def found(rallies: list[tuple[int, int, int]], counts: Counter, step: int, fps: float) -> list[tuple[int, int]]:
    """The gaps between two rallies of a set, long or with the court near-empty long enough, as (start, end) frames."""
    out = []
    for (_, end, set_), (start, _, next_set) in zip(rallies, rallies[1:]):
        if set_ != next_set or start - end > MAX_GAP_S * fps:
            continue
        empty = sum(counts[at] <= MAX_ON_COURT for at in range(end - end % step + step, start, step))
        if empty * step / fps >= MIN_EMPTY_S or start - end >= MIN_GAP_S * fps:
            out.append((end, start))
    return out


def detect(match: Path, fps: float) -> list[tuple[int, int]]:
    """`found` on a match's folder, written to `timeouts.csv`."""
    step = max(1, round(STEP_S * fps))
    timeouts = found(read_rallies(match / "rallies.csv"), on_court(match / "players.csv", step), step, fps)
    files.write_text(match / DETECTED, "start_frame,end_frame\n" + "".join(f"{a},{b}\n" for a, b in timeouts))
    return timeouts


def read_detected(match: Path, fps: float) -> list[tuple[int, int]]:
    """A match's detected timeouts, detected now when an older run left none."""
    path = match / DETECTED
    if path.exists():
        with path.open() as f:
            return [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]
    if (match / "rallies.csv").exists() and (match / "players.csv").exists():
        return detect(match, fps)
    return []


def read_answers(match: Path) -> list[dict]:
    path = match / ANSWERS
    return json.loads(path.read_text()) if path.exists() else []


def overlap(a: dict, start: int, end: int) -> bool:
    return a["start"] < end and start < a["end"]


def merged(detected: list[tuple[int, int]], answers: list[dict]) -> list[dict]:
    """The timeouts to show, by start: the answers but those removed, and what is detected where no answer is."""
    kept = [{"start": a["start"], "end": a["end"], "team": a.get("team")} for a in answers if not a.get("removed")]
    new = [{"start": a, "end": b, "team": None} for a, b in detected if not any(overlap(x, a, b) for x in answers)]
    return sorted(kept + new, key=lambda t: t["start"])


def answered(answers: list[dict], answer: dict) -> list[dict]:
    """`answers` with `answer` in place of those it overlaps."""
    return sorted([a for a in answers if not overlap(a, answer["start"], answer["end"])] + [answer], key=lambda a: a["start"])


def added(frame: int, rallies: list[tuple[int, int, int]], fps: float) -> dict:
    """A timeout added at `frame`: the gap it falls in, else a short span from there."""
    before = [end for _, end, _ in rallies if end <= frame]
    after = [start for start, _, _ in rallies if start > frame]
    inside = any(start <= frame < end for start, end, _ in rallies)
    if before and after and not inside and after[0] - before[-1] <= MAX_GAP_S * fps:
        return {"start": before[-1], "end": after[0], "team": None}
    return {"start": frame, "end": frame + round(ADDED_S * fps), "team": None}


def answer(match: Path, fps: float, body: dict) -> list[dict]:
    """Records a correction from the review (`frame`: one added; else `start`, `end` with a `team` or `removed`, in place of those they overlap: moving a bound overlaps the one moved) and returns the timeouts to show."""
    if "frame" in body:
        rallies = read_rallies(match / "rallies.csv") if (match / "rallies.csv").exists() else []
        new = added(int(body["frame"]), rallies, fps)
    else:
        new = {"start": int(body["start"]), "end": int(body["end"])}
        if body.get("removed"):
            new["removed"] = True
        else:
            new["team"] = int(body["team"]) if body.get("team") in (1, 2) else None
    answers = answered(read_answers(match), new)
    files.write_text(match / ANSWERS, json.dumps(answers, indent=1) + "\n")
    return merged(read_detected(match, fps), answers)


def shown(match: Path, fps: float) -> list[dict]:
    return merged(read_detected(match, fps), read_answers(match))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path)
    parser.add_argument("--fps", type=float, default=50.0)
    args = parser.parse_args()
    for start, end in detect(args.match, args.fps):
        print(f"{int(start / args.fps // 60)}:{int(start / args.fps % 60):02d} {(end - start) / args.fps:.0f} s")


if __name__ == "__main__":
    main()
