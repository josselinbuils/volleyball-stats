"""Score the defence placement (`defense.assign`) on built matches: whether the other team scores more when the
defenders stand further from their perimeter spots, and the usual ways to the spots by position and role, as the page reads
them. No labels say where a player should have stood: the attacks they score on are the check.

    uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats import web

# As the page: a usual place from this many attacks at a position in one role, a way told from this many metres.
FROM = 5
OFF_M = 1.0


def built(match: Path) -> tuple[dict, dict]:
    """The review page's data.js and its positions' samples, as `write_site` had them."""
    text = (match / "review" / "data.js").read_text()
    data = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
    p = data["positions"]
    samples: list[list[float]] = []
    for n in range(p["files"]):
        text = (match / "review" / "positions" / f"{n}.js").read_text()
        count, columns = json.loads(text[text.index(",") + 1 : text.rindex(")")])
        flats: list[list[float]] = [[] for _ in range(count)]
        for person, runs, xs, ys in columns:
            k = move = 0
            x = y = 0
            for i, run in enumerate(runs):
                if i % 2:
                    for _ in range(run):
                        x, y = x + xs[move], y + ys[move]
                        flats[k] += [person, x * p["cm"] / 100, y * p["cm"] / 100]
                        k, move = k + 1, move + 1
                else:
                    k += run
        samples[n * p["every"] :] = flats
    return data, {"step": p["step"], "samples": samples}


def role(position: int, depth: float) -> str:
    """As the page's: at the net, off it in front (the tip at 3), or in the back row."""
    return "block" if depth <= 1 else "tip" if position == 3 else "off" if position in (2, 4) else "back"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matches", type=Path, nargs="+")
    args = parser.parse_args()
    rows = []
    by_role: dict[tuple, list] = defaultdict(list)
    for match in args.matches:
        data, players = built(match)
        people = data["people"]
        found = web.defended(data["contacts"], data["rallies"], players, data["fps"], people)
        attacks = [c for c in found if c["type"] == "attack"]
        placed = [c for c in attacks if c.get("defense")]
        print(f"{match.name}: {len(placed)} of {len(attacks)} attacks with defenders, {np.mean([len(c['defense']) / 6 for c in placed]):.1f} each")
        by_player = defaultdict(list)
        for c in placed:
            spots = np.array(c["defense"]).reshape(-1, 6)
            if c["result"] != "error":
                rows.append((float(np.hypot(spots[:, 4] - spots[:, 2], spots[:, 5] - spots[:, 3]).mean()), c["result"] == "point"))
            for person, position, depth, x, to_depth, to_x in spots:
                p = people[str(int(person))]
                key = (int(position), role(int(position), to_depth))
                by_player[(p["team"], p.get("name") or f"#{p['number']}", *key)].append((to_depth - depth, to_x - x))
                by_role[(match.name[:10], p["team"], *key)].append((to_depth - depth, to_x - x))
        told = shown = 0
        for gaps in by_player.values():
            if len(gaps) >= FROM:
                shown += 1
                told += np.abs(np.median(gaps, axis=0)).max() >= OFF_M
        print(f"  {shown} player places from {FROM} attacks, {told} of them {OFF_M:g} m or more off")
    print("\nEach team's usual way to its spots, metres back from the net and to the right:")
    for (match, team, position, kind), gaps in sorted(by_role.items()):
        back, right = np.median(gaps, axis=0)
        print(f"  {match} team {team} position {position} {kind:>5}: {len(gaps):3d}, back {back:+.1f}, right {right:+.1f}")
    gap, point = np.array(rows).T
    edges = np.percentile(gap, [25, 50, 75])
    quarter = np.digitize(gap, edges)
    print(f"\nAttacks not missed: {len(gap)}, scored {point.mean():.0%}. Mean way to the spots, quarter edges {np.round(edges, 2)} m:")
    print("  scored by quarter, nearest first: " + ", ".join(f"{point[quarter == q].mean():.0%} of {(quarter == q).sum()}" for q in range(4)))


if __name__ == "__main__":
    main()
