"""A match's action types (`actions.csv`) against the types the review set (`identity_answers.json`
"action" answers with a `type`, the last one per frame): the review only sets the types it finds
wrong, so this scores the pipeline on its hard cases.

    uv run python benchmarks/actions/answers.py [outputs/matches/2026-10-29-aspom-1-vs-aspom-2] [--verbose]
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match", type=Path, nargs="?", default=ROOT / "outputs/matches/2026-10-29-aspom-1-vs-aspom-2")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    answers = json.loads((args.match / "identity_answers.json").read_text())
    said = {a["frame"]: a["type"] for a in answers["action"] if "type" in a}
    added = {a["frame"] for a in answers["added"]}
    with open(args.match / "actions.csv") as f:
        found = {int(r["frame"]): r["type"] for r in csv.DictReader(f)}
    pairs = Counter((found.get(frame, "added" if frame in added else "none"), kind) for frame, kind in said.items())
    right = sum(n for (a, b), n in pairs.items() if a == b)
    print(f"types right {right}/{len(said)}")
    if args.verbose:
        for (a, b), n in pairs.most_common():
            print(f"  {a} -> {b}: {n}")


if __name__ == "__main__":
    main()
