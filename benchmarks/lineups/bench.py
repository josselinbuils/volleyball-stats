"""Reads the page's lineups without labels: how many sixes each team has (they change rarely), and the touches on a
player of the six, which a toucher being counted as on court keeps high: it only catches a broken build.

    uv run python benchmarks/lineups/bench.py outputs/first_match outputs/side_setend
"""

import json
import sys
from pathlib import Path


def key(people: dict, person: int | None) -> tuple | None:
    p = people.get(str(person))
    if not p or p["number"] is None:
        return None
    return (p["team"], p.get("name") or p.get("jersey") or p["number"])


def score(match: Path) -> None:
    text = (match / "site" / "data.js").read_text()
    data = json.loads(text[text.index("{") : text.rindex("}") + 1])
    people, rallies = data["people"], data["rallies"]
    print(match.name)
    for team in (1, 2):
        stretches = [x for x in data["lineups"] if x["team"] == team]
        six = {frozenset(key(people, p) for p in x["people"]) for x in stretches}
        covered = sum(x["last"] - x["first"] + 1 for x in stretches)
        print(f"  team {team}: {len(stretches)} stretches, {len(six)} sixes, {covered} of {len(rallies)} rallies")
    inside = total = 0
    for c in data["contacts"]:
        name = key(people, c.get("person")) if c["type"] not in ("floor", "net", "fault") else None
        if name:
            total += 1
            on = [x for x in data["lineups"] if x["team"] == name[0] and x["first"] <= c["rally"] <= x["last"]]
            inside += any(name in {key(people, p) for p in x["people"]} for x in on)
    print(f"  touches on a player of the six: {inside} of {total}")


if __name__ == "__main__":
    for folder in sys.argv[1:]:
        score(Path(folder))
