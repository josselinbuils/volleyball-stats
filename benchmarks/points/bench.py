"""Score rally winners and the running score against hand-labelled winners.

    uv run --group bench python benchmarks/points/bench.py CLIP ... [--verbose]

Each CLIP reads data/CLIP.mp4, its ball track (outputs/ball/CLIP_ball.csv, else
outputs/CLIP/ball.csv), this folder's ground truth (every rally's set, server and winner, by jersey
colour), the jersey colour on each side per rally of benchmarks/teams and, where they exist, the
labelled contacts of benchmarks/contacts. Pooled over the clips given, winners right out of the
labelled rallies:
- labelled: the labelled windows, contacts and types (the rules alone; rallies with labelled contacts);
- detected: contacts.detect and actions.classify in the labelled windows;
- pipeline: the same in the windows of rallies.py, matched to the labelled rallies by overlap; a
  labelled rally without a window counts as missed;
each by the end-of-rally rule, the next-serve rule (the next window's server) and the two combined
(points.combine). Then the running score of each set against the labelled one: the pipeline's,
and the labelled windows with a third of them dropped at random (200 draws).
All clips run at 29.97 fps with the net at x=612, on the court of
benchmarks/court/ground_truth/side_club.json (same camera).
"""

import argparse
import csv
import importlib.util
import random
from pathlib import Path

from volleyball_stats import actions, contacts, points, rallies, teams

FPS = 29.97
NET_X = 612
DROP, DRAWS = 1 / 3, 200
spec = importlib.util.spec_from_file_location("actions_bench", Path(__file__).parents[1] / "actions" / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def read(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def track_path(clip: str) -> Path:
    path = Path(f"outputs/ball/{clip}_ball.csv")
    return path if path.exists() else Path(f"outputs/{clip}/ball.csv")


def overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return min(a[1], b[1]) - max(a[0], b[0])


def lefts(windows: list[tuple[int, int]], sides: list[dict], team_of: dict[str, int]) -> list[int]:
    """Team on the left of each window: the labelled one of the teams benchmark's nearest rally."""
    return [team_of[min(sides, key=lambda r: abs(int(r["start_frame"]) - s))["left"]] for s, _ in windows]


def accuracy(pairs: list[tuple[int | None, int | None]]) -> str:
    """Right / all (share), and how many got an answer, of (found, truth) pairs."""
    right = sum(f == t for f, t in pairs)
    answered = sum(f is not None for f, _ in pairs)
    return f"{right}/{len(pairs)} ({right / max(1, len(pairs)):.2f}), {answered} answered"


def no_credit(found: list[dict]) -> list[tuple[int, int]]:
    return points.running_score([(p["winner"], None) for p in found], [p["set"] for p in found])


def final_drifts(found: list[dict], scores: list[tuple[int, int]], truth: dict[int, tuple[int, int]]) -> list[int]:
    """Per labelled set, |estimated - labelled| final points summed over both teams."""
    last = {p["set"]: s for p, s in zip(found, scores)}
    return [abs(last.get(n, (0, 0))[0] - t[0]) + abs(last.get(n, (0, 0))[1] - t[1]) for n, t in truth.items()]


def clip_scores(clip: str, cal, verbose: bool) -> tuple[dict[str, list], list[str], dict[str, list[int]]]:
    """(found, truth) pairs per score, the drift lines of each set, and the simulated drifts."""
    labelled = read(Path(f"benchmarks/points/ground_truth/{clip}.csv"))
    sides = read(Path(f"benchmarks/teams/ground_truth/{clip}.csv"))
    team_of = {sides[0]["left"]: 1, sides[0]["right"]: 2}
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in labelled]
    sets = [int(r["set"]) for r in labelled]
    truth = [team_of[r["winner"]] for r in labelled]
    true_scores = points.running_score([(w, None) for w in truth], sets)
    true_final = {n: s for n, s in zip(sets, true_scores)}
    left = lefts(windows, sides, team_of)
    lead = round(actions.LEAD_S * FPS)
    out: dict[str, list] = {k: [] for k in ("labelled", "detected end", "detected next", "detected combined", "pipeline end", "pipeline next", "pipeline combined")}

    track = contacts.read_track(track_path(clip))
    filled = contacts.interpolate(track)
    found, crossings = contacts.detect(track, FPS, NET_X)

    # Labelled contacts: the rules' sides, the labelled types.
    path = Path(f"benchmarks/contacts/ground_truth/{clip}.csv")
    for rally in bench.load_ground_truth(path) if path.exists() else []:
        k = max(range(len(windows)), key=lambda i: overlap(windows[i], (rally["start"], rally["end"])))
        given = [(f, round(filled[f, 0]), round(filled[f, 1])) for f in rally["contacts"]]
        typed = [(f, x, y, rally["contacts"][f] or kind, side) for f, x, y, kind, side in actions.classify_rally(given, rally["net"], FPS, NET_X, cal)]
        side, reason = points.side_lost(typed, rally["net"], cal)
        won = points.team(None if side is None else points.other(side), left[k])
        out["labelled"].append((won, truth[k]))
        if verbose and won != truth[k]:
            print(f"  {clip} {windows[k]} labelled: {reason} -> {won}, truth {truth[k]}: {[(t[0], t[3], t[4]) for t in typed[-3:]]}")

    def describe(typed: list[actions.Typed]) -> list:
        return [(t[0], t[3], t[4], *(round(float(v), 1) for v in cal.to_court([[t[1], t[2]]])[0])) for t in typed[-3:]]

    # Detected contacts in the labelled windows.
    typed = actions.classify(found, crossings, windows, FPS, NET_X, cal)
    detected = points.points(typed, crossings, windows, left, sets, FPS, cal)
    per_rally = points.by_rally(typed, windows, lead)
    for k, p in enumerate(detected):
        out["detected end"].append((p["end"], truth[k]))
        out["detected next"].append((p["next"], truth[k]))
        out["detected combined"].append((p["winner"], truth[k]))
        if verbose and truth[k] not in (p["end"], p["winner"]):
            print(f"  {clip} {windows[k]} detected: end {p['end']} {p['reason']}, next {p['next']}, truth {truth[k]} ({labelled[k]['end']}): {describe(per_rally[k])}")

    # Labelled windows with some dropped, as rallies.py misses them.
    rng = random.Random(0)
    simulated: dict[str, list[int]] = {"combined": [], "no credit": [], "end": []}
    for _ in range(DRAWS):
        kept = [k for k in range(len(windows)) if rng.random() >= DROP]
        found_kept = points.points(typed, crossings, [windows[k] for k in kept], [left[k] for k in kept], [sets[k] for k in kept], FPS, cal)
        simulated["combined"] += final_drifts(found_kept, [p["score"] for p in found_kept], true_final)
        simulated["no credit"] += final_drifts(found_kept, no_credit(found_kept), true_final)
        ends = points.running_score([(p["end"], None) for p in found_kept], [p["set"] for p in found_kept])
        simulated["end"] += final_drifts(found_kept, ends, true_final)

    # The pipeline.
    pipe_windows = actions.served(rallies.segment(rallies.load_track(track_path(clip)), rallies.whistles(rallies.read_audio(Path(f"data/{clip}.mp4"))), FPS), found, FPS, cal)
    pipe_left = lefts(pipe_windows, sides, team_of)
    pipe_sets = teams.set_numbers(pipe_windows, teams.set_starts(pipe_windows, pipe_left, FPS), FPS)
    pipe_typed = actions.classify(found, crossings, pipe_windows, FPS, NET_X, cal)
    pipe = points.points(pipe_typed, crossings, pipe_windows, pipe_left, pipe_sets, FPS, cal)
    pipe_rallies = points.by_rally(pipe_typed, pipe_windows, lead)
    for k, window in enumerate(windows):
        j = max(range(len(pipe_windows)), key=lambda i: overlap(pipe_windows[i], window), default=None)
        if j is None or overlap(pipe_windows[j], window) <= 0:
            for name in ("pipeline end", "pipeline next", "pipeline combined"):
                out[name].append((None, truth[k]))
            if verbose:
                print(f"  {clip} {window} pipeline: missed, truth {truth[k]}")
            continue
        p = pipe[j]
        out["pipeline end"].append((p["end"], truth[k]))
        out["pipeline next"].append((p["next"], truth[k]))
        out["pipeline combined"].append((p["winner"], truth[k]))
        if verbose and truth[k] not in (p["end"], p["winner"]) or verbose and p["winner"] != truth[k]:
            print(f"  {clip} {window} pipeline {pipe_windows[j]}: end {p['end']} {p['reason']}, next {p['next']}, combined {p['winner']}, truth {truth[k]}: {describe(pipe_rallies[j])}")

    # Running score of each set: at each labelled rally's end, the pipeline's after its last rally
    # started by then.
    lines = []
    for scores, label in ((None, "combined"), (no_credit(pipe), "no credit")):
        scores = scores or [p["score"] for p in pipe]
        for number in sorted(true_final):
            worst = 0
            for (_, end), n, true in zip(windows, sets, true_scores):
                if n == number:
                    now = next((s for w, p, s in reversed(list(zip(pipe_windows, pipe, scores))) if p["set"] == number and w[0] <= end), (0, 0))
                    worst = max(worst, abs(now[0] - true[0]) + abs(now[1] - true[1]))
            final = next((s for p, s in reversed(list(zip(pipe, scores))) if p["set"] == number), (0, 0))
            lines.append(f"{clip} set {number}, {label}: labelled {true_final[number][0]}-{true_final[number][1]}, estimated {final[0]}-{final[1]}, worst drift {worst}")
    return out, lines, simulated


def score(clips: list[str], verbose: bool) -> None:
    cal = bench.calibration()
    pooled: dict[str, list] = {}
    drift_lines: list[str] = []
    simulated: dict[str, list[int]] = {}
    for clip in clips:
        found, lines, sims = clip_scores(clip, cal, verbose)
        print(f"{clip}: " + "; ".join(f"{name} {accuracy(pairs)}" for name, pairs in found.items() if pairs))
        for name, pairs in found.items():
            pooled.setdefault(name, []).extend(pairs)
        drift_lines += lines
        for name, values in sims.items():
            simulated.setdefault(name, []).extend(values)
    print("\nwinners, all clips:")
    for name, pairs in pooled.items():
        print(f"  {name}: {accuracy(pairs)}")
    print("\nrunning score, pipeline:")
    for line in drift_lines:
        print(f"  {line}")
    print(f"\nrunning score, labelled windows with {DROP:.0%} dropped ({DRAWS} draws), mean final drift per set (points):")
    for name, values in simulated.items():
        print(f"  {name}: {sum(values) / len(values):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", help="Clip stems, e.g. side_club")
    parser.add_argument("--verbose", action="store_true", help="List the rallies some rule gets wrong")
    args = parser.parse_args()
    score(args.clips, args.verbose)


if __name__ == "__main__":
    main()
