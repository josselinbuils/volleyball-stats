"""Score the defence placement (`defense.gaps`) on built matches: whether the other team scores more when the floor
defenders stand further from their perimeter spots, and each player's cue as the page gives it: their usual way to their
spot, in the kind of spot where it is longest. No labels say where a player should have stood: the attacks they score on are the check.

    uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats import web

# As the page: a player's usual gap from this many attacks, told from this many metres.
FROM = 8
OFF_M = 1.0
KINDS = ("front", "corner", "deep")


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matches", type=Path, nargs="+")
    args = parser.parse_args()
    rows = []
    for match in args.matches:
        data, players = built(match)
        people = data["people"]
        found = web.defended(data["contacts"], data["rallies"], players, data["fps"], people)
        attacks = [c for c in found if c["type"] == "attack"]
        placed = [c for c in attacks if c.get("defense")]
        print(f"{match.name}: {len(placed)} of {len(attacks)} attacks with floor defenders, {np.mean([len(c['defense']) / 4 for c in placed]):.1f} each")
        by_player = defaultdict(list)
        for c in placed:
            gaps = np.array(c["defense"]).reshape(-1, 4)
            if c["result"] != "error":
                rows.append((float(np.hypot(gaps[:, 2], gaps[:, 3]).mean()), c["result"] == "point"))
            for person, kind, back, out in gaps:
                p = people[str(int(person))]
                by_player[(p["team"], p.get("name") or f"#{p['number']}", int(kind))].append((back, out))
        cues = {}
        for (team, name, kind), gaps in by_player.items():
            back, out = np.median(gaps, axis=0)
            if len(gaps) >= FROM and max(abs(back), abs(out)) >= OFF_M and max(abs(back), abs(out)) > cues.get((team, name), (0, 0, 0, 0, 0))[0]:
                cues[(team, name)] = (max(abs(back), abs(out)), KINDS[kind], len(gaps), back, out)
        for (team, name), (_, kind, n, back, out) in sorted(cues.items()):
            print(f"  team {team} {name:>14}: {kind:>6}, {n:3d} attacks, back {back:+.1f} m, out {out:+.1f} m")
    gap, point = np.array(rows).T
    edges = np.percentile(gap, [25, 50, 75])
    quarter = np.digitize(gap, edges)
    print(f"\nAttacks not missed: {len(gap)}, scored {point.mean():.0%}. Mean way to the spots, quarter edges {np.round(edges, 2)} m:")
    print("  scored by quarter, nearest first: " + ", ".join(f"{point[quarter == q].mean():.0%} of {(quarter == q).sum()}" for q in range(4)))


if __name__ == "__main__":
    main()
