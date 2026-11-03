"""Timeouts found on each match, scored on the owner's answers in the review when it has any.

    uv run python benchmarks/timeouts/bench.py outputs/MATCH [...] [--fps 50]
"""

import argparse
from pathlib import Path

from volleyball_stats import timeouts


def clock(frame: int, fps: float) -> str:
    return f"{int(frame / fps // 60)}:{int(frame / fps % 60):02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matches", type=Path, nargs="+")
    parser.add_argument("--fps", type=float, default=50.0)
    args = parser.parse_args()
    for match in args.matches:
        step = max(1, round(timeouts.STEP_S * args.fps))
        found = timeouts.found(timeouts.read_rallies(match / "rallies.csv"), timeouts.on_court(match / "players.csv", step), step, args.fps)
        print(match.name, "found", len(found), [clock(a, args.fps) for a, _ in found])
        answers = timeouts.read_answers(match)
        real = [a for a in answers if not a.get("removed")]
        if answers:
            right = sum(any(timeouts.overlap(a, s, e) for a in real) for s, e in found)
            seen = sum(any(timeouts.overlap(a, s, e) for s, e in found) for a in real)
            print(f"  on the answers: {right}/{len(found)} found are real, {seen}/{len(real)} real are found")


if __name__ == "__main__":
    main()
