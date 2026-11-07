"""Score the defence systems (`defense.layout`) on built matches: the share of the balls the other team's attacks sent
(`defense.balls`) with a spot within `defense.CATCH_M`, each match held out in turn from the learning, against the
textbook perimeter and the players' own places at the hit. No labels say where a player should have stood: the balls are
the check.

    uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
"""

import argparse
import json
from pathlib import Path

import numpy as np

from volleyball_stats import defense, web

# The perimeter before the owner's change (7 Nov): the corners 1 m inside the sidelines 6.5 m off the net, 6 at 8 m.
TEXTBOOK = [(6.5, -3.5, 5), (8.0, 0.0, 6), (6.5, 3.5, 1)]


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


def situations(data: dict, players: dict) -> list[tuple[float, bool, np.ndarray, np.ndarray]]:
    """Each attack whose ball is seen: its across, whether two block, the defenders' places and where the ball went
    (a dug one `defense.DUG_M` further), in the defenders' frame."""
    out = []
    back = round(web.HOLD_S * data["fps"] / players["step"])
    for k, c in enumerate(data["contacts"]):
        left = data["rallies"][c["rally"]]["left"]
        if c["type"] != "attack" or c.get("x") is None or c.get("y") is None or not left:
            continue
        start, end, played = defense.flight(data["contacts"], k)
        if end is None:
            continue
        a, b = np.array(start), np.array(end)
        if played:
            b = b + defense.DUG_M * (b - a) / max(np.hypot(*(b - a)), 1e-9)
        sign = 1 if c["side"] == "left" else -1
        team = 3 - left if sign > 0 else left
        here = {p: (sign * x, -sign * y) for p, (x, y) in web.places_at(players, c["t"], data["fps"], back).items() if data["people"].get(str(p), {}).get("team") == team and sign * x > 0}
        out.append((start[1], defense.doubled(here), np.array(list(here.values())).reshape(-1, 2), b))
    return out


def caught(spots: np.ndarray, ball: np.ndarray) -> bool:
    return bool(len(spots)) and float(np.hypot(*(spots - ball).T).min()) <= defense.CATCH_M


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matches", type=Path, nargs="+")
    args = parser.parse_args()
    pages = {m: built(m) for m in args.matches}
    learned = defense.learn([b for data, _ in pages.values() for b in defense.balls(data["contacts"])])
    print("Learned on every match: " + json.dumps(learned))
    for match, (data, players) in pages.items():
        held_out = defense.learn([b for m, (d, _) in pages.items() if m != match for b in defense.balls(d["contacts"])])
        found = situations(data, players)
        rows = {"textbook perimeter": [], **{mode: [] for mode in defense.MODES}, "players' places": []}
        for across, double, places, ball in found:
            rows["textbook perimeter"].append(caught(np.array([s[:2] for s in defense.layout("perimeter", across, double)[:-3] + [(d, x if across >= 0 else -x, p) for d, x, p in TEXTBOOK]]), ball))
            for mode in defense.MODES:
                if mode != "learned" or held_out:
                    rows[mode].append(caught(np.array([s[:2] for s in defense.layout(mode, across, double, held_out)]), ball))
            rows["players' places"].append(caught(places, ball))
        print(f"\n{match.name}: {len(found)} balls, the learning on the other matches")
        for name, hits in rows.items():
            print(f"  {name:20s} " + (f"{np.mean(hits):.0%} within {defense.CATCH_M:g} m" if hits else "too few balls to learn"))


if __name__ == "__main__":
    main()
