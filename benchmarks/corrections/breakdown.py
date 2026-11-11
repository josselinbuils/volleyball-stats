"""The corrections of a run (bench.py score) broken down by cause, into outputs/benchmarks/corrections/breakdown.md.

    uv run python benchmarks/corrections/breakdown.py RUN [MATCH]

Reads truth.json, corrections.json and the run folder (ball.csv, players.csv, rallies.csv, actions.csv).
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from volleyball_stats import actions, attribution, contacts, learn, match, rallies
from volleyball_stats.court import Calibration

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/benchmarks/corrections"
SEEN_AROUND_S, SEEN_SHARE = 0.4, 0.5
SLIP_S = 0.5


def table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def counts(title: str, counter: Counter) -> list[str]:
    return table([title, "n"], [[k, v] for k, v in counter.most_common()] + [["total", sum(counter.values())]])


def raw_contacts(folder: Path, court: Path, fps: float, windows: list[tuple[int, int]], rows: list, lead: int):
    """The contacts `contacts.detect` finds on the run's ball track, those the windows hold typed, and which of these have no player at the ball."""
    calibration = Calibration.load(court)
    net_x = float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    seen = rallies.load_track(folder / "ball.csv")
    track = seen.copy()
    track[calibration.in_front(track, match.SPARE_Y)] = np.nan
    found, crossings = contacts.detect(track, fps, net_x, rallies.court_scale(calibration), lambda x, y: actions.on_floor(calibration, x, y, True))
    typed = actions.classify(found, crossings, windows, fps, net_x, calibration)
    return seen, [c[0] for c in found], {t[0] for t in typed}, attribution.unreached(typed, rows, fps, crossings)


def breakdown(name: str, run: str) -> list[str]:
    truth = json.loads((BASE / name / "truth.json").read_text())
    folder = BASE / name / "runs" / run / name
    found = json.loads((BASE / name / "runs" / run / "corrections.json").read_text())
    summary = json.loads((BASE / name / "runs" / run / "summary.json").read_text())
    fps = truth["fps"]
    lead, within = round(actions.LEAD_S * fps), round(learn.SAME_S * fps)
    given = json.loads((ROOT / "outputs/matches" / name / "source.json").read_text())
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in learn.read_rows(folder / "rallies.csv")]
    rows = attribution.read_players(folder / "players.csv")
    seen, raw, typed_frames, far = raw_contacts(folder, ROOT / given["court"], fps, windows, rows, lead)
    kept = [int(r["frame"]) for r in learn.read_rows(folder / "actions.csv")]
    by_key = {r["key"]: r for r in truth["rallies"]}
    out = [f"## {name} ({len(truth['rallies'])} rallies, {summary['counts']['total']} corrections, run {run})", ""]
    out += table(["add", "remove", "type", "player", "winner", "total", "per rally", "rallies at zero"], [[summary["counts"][k] for k in ("add", "remove", "type", "player", "winner", "total", "per rally", "rallies at zero")]])

    adds = [c for c in found if c["kind"] == "add"]
    causes, position, grid = Counter(), Counter(), Counter()
    for c in adds:
        f, r = c["frame"], by_key[c["rally"]]
        around = round(SEEN_AROUND_S * fps)
        share = float(np.mean(~np.isnan(seen[max(0, f - around) : f + around + 1, 0])))
        near_raw = learn.near(f, raw, within)
        if not any(a - lead <= f <= b for a, b in windows):
            cause = "a. outside every pipeline window"
        elif share < SEEN_SHARE:
            cause = "b. ball seen in under half the frames (+-0.4 s)"
        elif near_raw is None:
            cause = "c. ball seen, no contact detected"
        elif near_raw in far:
            cause = "d1. contact detected, dropped: no player at the ball"
        elif near_raw in typed_frames:
            cause = "d2. contact detected and typed, absent from actions.csv"
        else:
            cause = "d3. contact detected, not typed (outside the windows' classify)"
        order = [t["frame"] for t in r["touches"]]
        where = "first (serve)" if f == min(order) else "last" if f == max(order) else "between"
        causes[cause] += 1
        position[where] += 1
        grid[c["truth_type"], cause[0]] += 1
    out += ["### Touches to add", ""] + counts("by truth type", Counter(c["truth_type"] for c in adds)) + counts("by cause", Counter(dict(sorted(causes.items())))) + counts("by position in the rally", position)
    types = sorted({k[0] for k in grid})
    out += table(["truth type", "a", "b", "c", "d"], [[t, *(grid[t, x] for x in "abcd")] for t in types])
    out += [f"Adds with a pipeline touch within {SLIP_S} s (timing slip or duplicate case): {sum(c['nearest_s'] is not None and c['nearest_s'] <= SLIP_S for c in adds)}.", ""]

    drops = [c for c in found if c["kind"] == "remove"]
    place = Counter()
    for c in drops:
        order = [t["frame"] for t in by_key[c["rally"]]["touches"]]
        place["no truth touch in the rally" if not order else "before the truth's first" if c["frame"] < min(order) else "after the truth's last" if c["frame"] > max(order) else "in between"] += 1
    out += ["### Touches to remove", ""] + counts("by pipeline type", Counter(c["pipe_type"] for c in drops)) + counts("by position", place)
    out += [f"Within 0.2-{SLIP_S} s of a truth touch (duplicate or timing slip): {sum(c['nearest_s'] is not None and c['nearest_s'] <= SLIP_S for c in drops)} of {len(drops)}.", ""]

    wrong = [c for c in found if c["kind"] == "type"]
    pairs = Counter((c["truth_type"], c["pipe_type"]) for c in wrong)
    missing = Counter(c["truth_type"] for c in adds)
    shown = sorted({t["type"] for r in truth["rallies"] for t in r["touches"]})
    cols = sorted({p for _, p in pairs})
    total = Counter(t["type"] for r in truth["rallies"] for t in r["touches"])
    out += ["### Types (matched touches; off-diagonal cells only, rows truth, columns pipeline)", ""]
    out += table(["truth \\ pipeline", *cols, "wrong", "matched"], [[t, *(pairs[t, p] or "" for p in cols), sum(pairs[t, p] for p in cols), total[t] - missing[t]] for t in shown])
    out += table(["8 largest off-diagonal cells", "n"], [[f"{t} -> {p}", n] for (t, p), n in pairs.most_common(8)])

    bad = [c for c in found if c["kind"] == "player"]

    def who(c: dict) -> str:
        if c["pipe_identity"] is None:
            return "pipeline unknown"
        return "another named player" if c["pipe_name"] else "an unnamed identity"

    side = Counter("team unknown" if not c["pipe_team"] else "same team" if str(c["pipe_team"]) == str(c["truth_team"]) else "other team" for c in bad)
    out += ["### Players to fix", ""] + counts("by truth type", Counter(c["truth_type"] for c in bad)) + counts("pipeline said", Counter(who(c) for c in bad)) + counts("pipeline team", side)
    out += [f"Of these, the type was also wrong: {sum(c['truth_type'] != c['pipe_type'] for c in bad)}.", ""]

    lost = [c for c in found if c["kind"] == "winner"]
    why = Counter()
    for c in lost:
        r = next(r for r in truth["rallies"] if r["start"] == c["t"])
        last = max((t["frame"] for t in r["touches"]), default=None)
        mine = [int(x["frame"]) for x in learn.read_rows(folder / "actions.csv") if r["start_frame"] - lead <= int(x["frame"]) <= r["end_frame"]]
        if c["truth_winner"] is None:
            cause = "truth has no winner (not a redo)"
        elif c["window"] is None:
            cause = "no pipeline window on the rally"
        elif c["pipe_winner"] is None:
            cause = "winner missing from points.csv"
        elif not mine or last is None or learn.near(last, mine, within) is None or max(mine) - last > within:
            cause = "pipeline's last touch differs from the truth's"
        else:
            cause = "last touch right, result wrong"
        why[cause] += 1
    out += ["### Winners to fix", ""] + counts("cause", why)

    per = summary["per_rally"]
    hist = Counter("0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3-5" if n <= 5 else "6+" for n in per.values())
    worst = sorted(per.values(), reverse=True)[:10]
    out += ["### Rallies", ""] + table(["corrections", "0", "1", "2", "3-5", "6+"], [["rallies", *(hist[k] for k in ("0", "1", "2", "3-5", "6+"))]])
    out += [f"The 10 worst rallies hold {sum(worst)} of {len(found)} corrections ({sum(worst) / max(1, len(found)):.0%}): {worst}.", ""]

    out += ["### Also", ""]
    by_truth = Counter(c.get("truth_type") for c in found if c["kind"] in ("add", "type", "player"))
    out += [f"Corrections by truth type (add, type, player): {dict(by_truth.most_common())}.", ""]
    nowin = [r for r in truth["rallies"] if not any(a < r["end_frame"] and r["start_frame"] < b for a, b in windows)]
    out += [f"Checked rallies with no pipeline window at all: {len(nowin)} ({sum(len(r['touches']) for r in nowin)} truth touches, all to add).", ""]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run")
    parser.add_argument("match", nargs="?")
    args = parser.parse_args()
    names = sorted(p.name for p in BASE.iterdir() if p.is_dir() and (p / "runs" / args.run / "summary.json").exists() and (not args.match or p.name.startswith(args.match)))
    if not names:
        sys.exit("No scored run of that name: bench.py score RUN first")
    text = ["# Corrections breakdown", ""]
    for name in names:
        text += breakdown(name, args.run)
    path = BASE / "breakdown.md"
    path.write_text("\n".join(text) + "\n")
    print("\n".join(text))
    print(path)


if __name__ == "__main__":
    main()
