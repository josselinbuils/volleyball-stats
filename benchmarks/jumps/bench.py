"""Scores `jumps.measure` against the hand-labelled attacks of `ground_truth/labels.csv`, per match: the first tunes, the
second is held out. Poses come from each match's `jumps.json` (computed when missing).

    uv run python benchmarks/jumps/bench.py [--sweep]
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats import jumps
from volleyball_stats.court import Calibration

LABELS = Path(__file__).parent / "ground_truth" / "labels.csv"
MATCHES = Path("outputs/matches")
FPS = 50.0


def number(text: str) -> int | None:
    return int(text) if text.strip().lstrip("-").isdigit() else None


def load() -> dict[str, dict]:
    """Each match's labels, tracks, poses and calibration."""
    by_match: dict[str, list[dict]] = defaultdict(list)
    for row in csv.DictReader(open(LABELS)):
        by_match[row["match"]].append(row)
    out = {}
    for name, labels in by_match.items():
        match = MATCHES / name
        source = json.loads((match / "source.json").read_text())
        attacks = [(int(r["frame"]), int(r["track"])) for r in labels]
        tracks = jumps.read_tracks(match / "players.csv", {t for _, t in attacks})
        poses = jumps.pose_all(Path(source["video"]), attacks, tracks, FPS, match / "jumps.json")
        ball = jumps.read_ball(match / "ball.csv", {f for a, _ in attacks for f in jumps.window(a, FPS)})
        out[name] = {"labels": labels, "tracks": tracks, "poses": poses, "ball": ball, "calibration": Calibration.load(Path(source["court"]))}
    return out


def distance(rows: np.ndarray, frame: int) -> float:
    return float(abs(jumps.at(rows, range(frame, frame + 1), round(jumps.HOLE_S * FPS))[0, 4]))


def late(contact: int, takeoff: int, landing: int) -> float:
    return (contact - (takeoff + landing - 1) / 2) / FPS * 1000


def score(data: dict, verbose: bool = False, quiet: bool = False) -> dict[str, float]:
    found = missed = false = 0
    takeoffs, landings, lates, apexes, hits, near, starts = [], [], [], [], [], [], []
    for row in data["labels"]:
        if row["attacker"] != "yes":
            continue
        frame, track = int(row["frame"]), int(row["track"])
        rows = data["tracks"][track]
        got = jumps.measure(frame, rows, data["poses"][f"{frame}:{track}"], data["calibration"], FPS, data["ball"])
        takeoff, landing = number(row["takeoff"]), number(row["landing"])
        if row["jump"] != "yes" or takeoff is None or landing is None:
            false += got is not None and row["jump"] == "no"
            continue
        if got is None:
            missed += 1
            continue
        found += 1
        takeoffs.append(got["takeoff"] - takeoff)
        landings.append(got["landing"] - landing)
        contact = number(row["contact"]) or frame
        lates.append(got["late"] - late(contact, takeoff, landing))
        apexes.append(got["late"] - late(got["hit"], takeoff, landing))
        if number(row["contact"]) is not None:
            hits.append(got["hit"] - contact)
        if got.get("takeoff_m") is not None:
            near.append(got["takeoff_m"] - distance(rows, takeoff - 1))
        start = number(row["start"]) if row["start"] != "none" else takeoff - 1
        start_error = got["start_m"] - distance(rows, start) if got.get("start_m") is not None and start is not None else float("nan")
        if not np.isnan(start_error):
            starts.append(start_error)
        if verbose:
            print(f"  {frame:>7} {track:>5}  takeoff {takeoffs[-1]:+3d}  landing {landings[-1]:+3d}  late {lates[-1]:+5.0f} ms  start {start_error:+.2f} m")

    def within(errors: list, limit: float) -> str:
        return f"{sum(abs(e) <= limit for e in errors)}/{len(errors)}"

    def median(errors: list) -> float:
        return float(np.median(np.abs(errors))) if errors else float("nan")

    if quiet:
        print(f"  found {found} missed {missed} false {false}  takeoff {median(takeoffs):.1f} {within(takeoffs, 2)}  landing {median(landings):.1f} {within(landings, 2)}  late {median(lates):.0f} ms {within(lates, 60)}  apex {median(apexes):.0f} ms")
        return {}
    print(f"  jumps found {found}, missed {missed}, false {false}")
    print(f"  takeoff  |error| median {median(takeoffs):.1f} frames, within 2: {within(takeoffs, 2)}")
    print(f"  landing  |error| median {median(landings):.1f} frames, within 2: {within(landings, 2)}")
    print(f"  hit      |error| median {median(hits):.1f} frames, within 2: {within(hits, 2)}")
    print(f"  late     |error| median {median(lates):.0f} ms, within 60 ms: {within(lates, 60)} (the flight's top alone {median(apexes):.0f} ms)")
    print(f"  takeoff distance to the net |error| median {median(near):.2f} m, run-up start {median(starts):.2f} m, within 0.5 m: {within(starts, 0.5)}")
    return {}


def main() -> None:
    data = load()
    if "--sweep" in sys.argv:
        for jumps.LIFT_M in (0.1, 0.15, 0.2):
            for jumps.FLOOR_M in (0.03, 0.05, 0.08):
                for jumps.STOP in (0.2, 0.3, 0.4, 0.5):
                    print(f"LIFT_M {jumps.LIFT_M} FLOOR_M {jumps.FLOOR_M} STOP {jumps.STOP}")
                    for d in data.values():
                        score(d, quiet=True)
        return
    for name, d in data.items():
        print(name)
        score(d, "--verbose" in sys.argv)


if __name__ == "__main__":
    main()
