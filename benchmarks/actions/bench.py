"""Score action classification against the typed contacts of benchmarks/contacts.

    uv run --group bench python benchmarks/actions/bench.py VIDEO:TRACK:GROUND_TRUTH ... [--verbose]

Pooled over the clips given, three scores of `actions`:
- `truth`: the labelled contacts, rally windows and net crossings (the rules alone);
- `detected`: the contacts and crossings of contacts.detect in the labelled windows, matched to the
  labelled contacts within ±2 frames;
- `pipeline`: the same in the windows of rallies.py (the video gives the whistles).
All clips run at 29.97 fps with the net at x=612, on the court of
benchmarks/court/ground_truth/side_club.json (same camera, shifted under 0.1 px).
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from volleyball_stats import actions, contacts, court, rallies

FPS = 29.97
NET_X = 612
TOLERANCE = 2
COURT = Path("benchmarks/court/ground_truth/side_club.json")
TYPES = ("serve", "pass", "dig", "set", "attack", "block", "floor", "net")


def load_ground_truth(path: Path) -> list[dict]:
    """One dict per rally: start, end, contacts {frame: type}, net [frames]."""
    found: dict[str, dict] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rally = found.setdefault(row["rally"], {"contacts": {}, "net": []})
            if row["event"] in ("start", "end"):
                rally[row["event"]] = int(row["frame"])
            elif row["event"] == "contact":
                rally["contacts"][int(row["frame"])] = row["type"]
            else:
                rally["net"].append(int(row["frame"]))
    return list(found.values())


def calibration() -> court.Calibration:
    """Least squares on the hand-located line landmarks; the posts' distance to the court is unknown."""
    points = json.loads(COURT.read_text())["points"]
    return court.fit({name: tuple(p) for name, p in points.items() if not name.startswith("post")}, ransac=False)


def pair(found: list[int], truth: list[int]) -> dict[int, int]:
    """Truth frame -> detected frame, one to one, nearest first, within TOLERANCE."""
    free, out = sorted(found), {}
    for t in sorted(truth):
        near = [d for d in free if abs(d - t) <= TOLERANCE]
        if near:
            out[t] = min(near, key=lambda d: abs(d - t))
            free.remove(out[t])
    return out


def compare(labels: dict[int, str], typed: dict[int, str]) -> tuple[list[tuple[str, str]], dict[int, str], list[int]]:
    """(truth, predicted) rows, '-' for a missed or a false contact; the prediction per truth frame;
    the false detections."""
    matched = pair(list(typed), list(labels))
    false = [f for f in typed if f not in matched.values()]
    rows = [(labels[t], typed[matched[t]] if t in matched else "-") for t in labels] + [("-", typed[f]) for f in false]
    return rows, {t: typed[d] for t, d in matched.items()}, false


def report(name: str, rows: list[tuple[str, str]]) -> None:
    """Accuracy and confusion matrix; unclear labels are shown but not scored."""
    typed = [(t, p) for t, p in rows if t not in ("", "-")]
    correct = sum(t == p for t, p in typed)
    found = sum(p != "-" for _, p in typed)
    print(f"\n{name}: {correct}/{len(typed)} labelled contacts typed right ({correct / len(typed):.3f})", end="")
    print(f", {correct}/{found} of those found ({correct / found:.3f})" if found < len(typed) else "")
    columns = [*TYPES, "-"]
    counts = Counter(rows)
    print(f"  {'truth \\ pred':12}" + "".join(f"{c:>7}" for c in columns) + f"{'recall':>8}")
    for t in [*TYPES, "", "-"]:
        total = sum(counts[t, p] for p in columns)
        if total:
            recall = f"{counts[t, t] / total:8.2f}" if t in TYPES else ""
            print(f"  {t or '(unclear)':12}" + "".join(f"{counts[t, p] or '.':>7}" for p in columns) + recall)


def score(clips: list[tuple[Path, Path, Path]], verbose: bool) -> None:
    cal = calibration()
    rows: dict[str, list] = {"truth": [], "detected": [], "pipeline": []}
    sides = []
    for video, track_path, truth_path in clips:
        track = contacts.read_track(track_path)
        filled = contacts.interpolate(track)
        found, crossings = contacts.detect(track, FPS, NET_X)
        windows = actions.served(rallies.segment(rallies.load_track(track_path), rallies.whistles(rallies.read_audio(video)), FPS), found, FPS, cal)
        pipeline = {f: kind for f, _, _, kind, _ in actions.classify(found, crossings, windows, FPS, NET_X, cal)}
        for rally in load_ground_truth(truth_path):
            labels, start, end = rally["contacts"], rally["start"], rally["end"]
            given = [(f, round(filled[f, 0]), round(filled[f, 1])) for f in labels]
            truth = actions.classify_rally(given, rally["net"], FPS, NET_X, cal)
            rows["truth"] += [(labels[f], kind) for f, _, _, kind, _ in truth]
            # The ball changes side at each labelled crossing; a block's side is set by the rule.
            first, side0 = truth[0][0], truth[0][4]
            sides += [(side == side0) == (sum(first < c <= f for c in rally["net"]) % 2 == 0) for f, _, _, kind, side in truth if kind != "block"]
            inside = [c for c in found if start <= c[0] <= end]
            detected = {f: kind for f, _, _, kind, _ in actions.classify_rally(inside, [c for c in crossings if start <= c <= end], FPS, NET_X, cal)}
            pipelined = {f: kind for f, kind in pipeline.items() if start <= f <= end}
            shown, false = {}, {}
            for name, typed in (("detected", detected), ("pipeline", pipelined)):
                new, shown[name], false[name] = compare(labels, typed)
                rows[name] += new
            if verbose:
                print(f"{truth_path.stem} {start}-{end} net {rally['net']}, rallies.py {[w for w in windows if w[0] <= end and w[1] >= start]}")
                print(f"  {'frame':>6} {'x':>5} {'y':>4} {'side':5} {'label':7} {'truth':7} {'detected':8} pipeline")
                for f, x, y, kind, side in truth:
                    print(f"  {f:6} {x:5} {y:4} {side:5} {labels[f] or '?':7} {kind:7} {shown['detected'].get(f, '-'):8} {shown['pipeline'].get(f, '-')}")
                for name, typed in (("detected", detected), ("pipeline", pipelined)):
                    if false[name]:
                        print(f"  false {name}: {', '.join(f'{f}:{typed[f]}' for f in false[name])}")
    report("truth (labelled contacts, windows and crossings)", rows["truth"])
    print(f"  sides agreeing with the first contact's and the labelled crossings: {sum(sides)}/{len(sides)}")
    report(f"detected (contacts.detect in the labelled windows, ±{TOLERANCE} frames)", rows["detected"])
    report(f"pipeline (contacts.detect in the rallies.py windows, ±{TOLERANCE} frames)", rows["pipeline"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", help="VIDEO:TRACK_CSV:GROUND_TRUTH_CSV")
    parser.add_argument("--verbose", action="store_true", help="List every rally's contacts")
    args = parser.parse_args()
    score([tuple(map(Path, c.split(":"))) for c in args.clips], args.verbose)


if __name__ == "__main__":
    main()
