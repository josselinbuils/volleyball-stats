"""Score the identity step on a match's own review answers: each half of identity_answers.json is
held out in turn, the step run with the other half (the names and the cuts always kept), and the
held-out answers checked: "same" pieces in one identity, "different" ones in two.

    uv run python benchmarks/identity/answers.py outputs/first_match --video data/first_match.mp4
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2

from volleyball_stats import identity, jerseys
from volleyball_stats.attribution import read_players

KINDS = ("same", "different", "not_player", "cut")


def load(match: Path, video: Path) -> dict:
    """identify's inputs from a match folder, as identity.rerun reads them."""
    with open(match / "rallies.csv") as f:
        rallies = list(csv.DictReader(f))
    with open(match / "actions.csv") as f:
        typed = list(csv.DictReader(f))
    return {
        "windows": [(int(r["start_frame"]), int(r["end_frame"])) for r in rallies],
        "left": [int(r["left"]) if r.get("left") else None for r in rallies],
        "fps": cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS),
        "rows": read_players(match / "players.csv"),
        "contacts": [(int(r["frame"]), int(r["track"])) for r in typed if r.get("track")],
    }


def constraints(entries: list[dict]) -> dict[str, list]:
    return {kind: [x for e in entries for x in e.get(kind, [])] for kind in KINDS}


def checks(segments: list[identity.Segment], entries: list[dict]) -> tuple[int, int]:
    """(kept, total) of the entries' "same" groups and "different" pairs in `segments`."""
    before = [None] * len(segments)

    def who(ref: dict) -> set[tuple[int, int]]:
        return {(segments[k].team, segments[k].identity) for k in identity.resolve(ref, segments, before)}

    kept = total = 0
    for e in entries:
        for g in e.get("same", []):
            ids = set().union(*(who(r) for r in g))
            total += 1
            kept += len(ids) == 1 and next(iter(ids))[1] != 0
        for g in e.get("different", []):
            for a in range(len(g)):
                for b in range(a + 1, len(g)):
                    total += 1
                    kept += not (who(g[a]) & who(g[b]))
    return kept, total


def run(match: Path, video: Path, inputs: dict, log: list[dict], names: list, numbers: dict | None = None) -> tuple[int, int]:
    """(kept, total) over both held-out halves, with the jersey numbers read if given."""
    kept = total = 0
    for fold in (0, 1):
        held = [e for k, e in enumerate(log) if k % 2 == fold and e.get("choice") != "cut"]
        given = [e for k, e in enumerate(log) if k % 2 != fold or e.get("choice") == "cut"]
        segments, _ = identity.identify(
            video, inputs["rows"], inputs["windows"], inputs["left"], inputs["fps"], match / "embeddings.npz", constraints(given), contacts=inputs["contacts"], jerseys=numbers, names=names
        )
        k, n = checks(segments, held)
        kept, total = kept + k, total + n
    return kept, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    inputs = load(args.match, args.video)
    log = json.loads((args.match / "identity_answers.json").read_text())["log"]
    names = [(e["ref"], e["name"]) for e in identity.read_names(args.match) if e.get("name")]
    numbers = jerseys.load(args.match)
    for label, read in (("without jersey numbers", None), ("with jersey numbers", numbers)) if numbers else (("", None),):
        start = time.perf_counter()
        kept, total = run(args.match, args.video, inputs, log, names, read)
        print(f"{len(log)} answers, {len(names)} names{', ' + label if label else ''}: {kept}/{total} held-out constraints kept ({kept / max(total, 1):.0%}), {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
