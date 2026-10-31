"""Score attribution on a match's own review answers: each touch asked in the review and answered
with a player (identity_answers.json's "touch") against the automatic pick (actions.csv's
identity), by why it was asked and by the gap to the next candidate. The spot checks estimate the
wrong picks the doubts miss; the gaps, where to set attribution.DOUBT.

    uv run python benchmarks/attribution/answers.py outputs/first_match
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from volleyball_stats import identity, web
from volleyball_stats.actions import LEAD_S
from volleyball_stats.review import UNKNOWN, doubtful

GAPS = (0.01, 0.02, 0.05, 0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path)
    parser.add_argument("--fps", type=float, default=50.0)
    args = parser.parse_args()
    actions = web.read_csv(args.match / "actions.csv")
    windows = [(int(r["start_frame"]) - round(LEAD_S * args.fps), int(r["end_frame"])) for r in web.read_csv(args.match / "rallies.csv")]
    why = {r["frame"]: reason for r, reason in doubtful(actions, windows)}
    row = {r["frame"]: r for r in actions}
    path = args.match / "identity_answers.json"
    answers = json.loads(path.read_text()).get("touch", []) if path.exists() else []
    given = identity.named(identity.read_identities(args.match / "identities.csv"), identity.read_names(args.match))
    by_name = {(team, g["name"]): number for (team, number), g in given.items() if g.get("name")}
    by_reason, by_gap, nobody, outside = defaultdict(list), defaultdict(list), 0, 0
    for a in answers:
        r = row.get(str(a["frame"]))
        if r is None:
            continue
        # No touch at all ("nobody", identity None): a contact the detector made up, wrong whoever got it.
        said = None if a["identity"] is None else by_name.get((a["team"], a.get("name")), a["identity"])
        right = said is not None and r["identity"] not in UNKNOWN and int(r["identity"]) == said
        nobody += said is None and a.get("play", True)
        outside += not a.get("play", True)
        by_reason[why.get(r["frame"], "asked before")].append(right)
        if r.get("gap"):
            by_gap[next((g for g in GAPS if float(r["gap"]) < g), None)].append(right)
    print(f"{sum(map(len, by_reason.values()))} touches answered, {nobody} of them no touch at all, {outside} outside the play")
    for reason, hits in sorted(by_reason.items()):
        print(f"  {reason:12} automatic pick right {sum(hits)}/{len(hits)}")
    for g in (*GAPS, None):
        if by_gap[g]:
            print(f"  gap {'< ' + str(g) if g else '>= ' + str(GAPS[-1]):7} right {sum(by_gap[g])}/{len(by_gap[g])}")


if __name__ == "__main__":
    main()
