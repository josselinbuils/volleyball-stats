"""Servers and winners of the first match's rallies (`points.csv`) against the rallies benchmark's
labels of two 10 minutes (`benchmarks/rallies/ground_truth/first_match_*.csv`): each label's note
names the end serving ("left serves"), the winner of a rally is the end serving the next one (the
sideout rule), unknown for a span's last rally.

    uv run python benchmarks/points/first_match.py [outputs/2026-10-29-aspom-1-vs-aspom-2] [--verbose]
"""

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPANS = ("first_match_26_36", "first_match_50_60")
# How far a window's start may be from its labelled serve.
NEAR = 75


def labels() -> list[tuple[int, str, str | None]]:
    """(serve frame, serving end, winning end) of each labelled rally."""
    out = []
    for span in SPANS:
        with open(ROOT / "benchmarks/rallies/ground_truth" / f"{span}.csv") as f:
            rows = [(int(r["start_frame"]), "left" if r["note"].startswith("left serves") else "right") for r in csv.DictReader(f)]
        out += [(start, end, after[1] if after else None) for (start, end), after in zip(rows, [*rows[1:], None])]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match", type=Path, nargs="?", default=ROOT / "outputs/2026-10-29-aspom-1-vs-aspom-2")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    with open(args.match / "rallies.csv") as f:
        windows = list(csv.DictReader(f))
    with open(args.match / "points.csv") as f:
        points = {int(r["start_frame"]): r for r in csv.DictReader(f)}
    found = served = won = asked = 0
    truth = labels()
    for start, server, winner in truth:
        near = [w for w in windows if abs(int(w["start_frame"]) - start) <= NEAR]
        if not near:
            if args.verbose:
                print(f"{start}: no window")
            continue
        found += 1
        w = min(near, key=lambda w: abs(int(w["start_frame"]) - start))
        p = points.get(int(w["start_frame"]), {})
        side = lambda team: None if not team or not w["left"] else ("left" if team == w["left"] else "right")  # noqa: E731
        served += side(p.get("server")) == server
        if winner:
            asked += 1
            won += side(p.get("winner")) == winner
        if args.verbose and (side(p.get("server")) != server or (winner and side(p.get("winner")) != winner)):
            print(f"{start}: server {side(p.get('server'))} (label {server}), winner {side(p.get('winner'))} (label {winner}), {p.get('reason')}")
    print(f"windows {found}/{len(truth)}, servers {served}/{found}, winners {won}/{asked}")


if __name__ == "__main__":
    main()
