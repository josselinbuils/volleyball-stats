"""The names the review proposes on each match's cards (`review_answers.propose`), against those given, each match left out
of the roster (its players' vectors and jerseys from the other matches only), as when it is first reviewed.

    uv run python benchmarks/identity/names.py

Per match: the cards, those proposed the name given (right), another roster name (wrong), "Joueur N" for a player
named otherwise (to rename), none; and how many the suggestions' first chip names right today.
"""

import copy
import json
from pathlib import Path

from volleyball_stats import identity, review_answers, review_questions, web

OUT = Path("outputs/matches")


def jerseys(matches: list[Path]) -> dict[str, dict[str, int]]:
    """Each match's jersey by folded name, from its names given."""
    out = {}
    for m in matches:
        given = json.loads((m / "player_names.json").read_text(encoding="utf-8"))["players"]
        out[m.name] = {g["name"].casefold(): g["jersey"] for g in given if g.get("name") and g.get("jersey") is not None}
    return out


def left_out(roster: list[dict], match: str, worn: dict[str, dict[str, int]]) -> list[dict]:
    """The roster as it stood without `match`: its vectors dropped, each jersey the latest other match's."""
    out = []
    for p in copy.deepcopy(roster):
        p["vectors"].pop(match, None)
        if not p["vectors"]:
            continue
        p["jersey"] = next((worn[m][p["name"].casefold()] for m in sorted(p["vectors"], reverse=True) if p["name"].casefold() in worn.get(m, {})), None)
        out.append(p)
    return out


def score(match: Path, roster: list[dict], worn) -> dict:
    q = review_questions.Questions(match, 50.0)
    names = identity.named(q.table, identity.read_names(match))
    seconds = identity.on_court(q.table, q.fps)
    left = identity.leftovers(seconds, names)
    cards = {k: q.vectors.get(k) for k in seconds if k not in left and names.get(k, {}).get("name")}
    teams = review_teams(match)
    known = left_out(roster, match.name, worn)
    proposed = review_answers.propose(cards, q.read, known, teams)
    counts = {"cards": len(cards), "right": 0, "wrong": 0, "rename": 0, "none": 0, "first chip": 0}
    for card in cards:
        truth = names[card]["name"].casefold()
        got = proposed.get(card)
        if got is None:
            counts["none"] += 1
        elif got["name"].casefold() == truth:
            counts["right"] += 1
        elif got["name"].startswith("Joueur ") and not any(p["name"].casefold() == got["name"].casefold() for p in known):
            counts["rename"] += 1
        else:
            counts["wrong"] += 1
        chips = review_answers.suggest(cards[card], known, teams[card[0] - 1], number=q.read.get(card))
        counts["first chip"] += bool(chips) and chips[0]["name"].casefold() == truth
    return counts


def review_teams(match: Path) -> list[str | None]:
    teams = web.read_teams(match)
    return [t["name"] for t in teams["teams"]] if teams else [None, None]


def main() -> None:
    matches = sorted(m for m in OUT.glob("2026-*") if (m / "player_names.json").exists())
    roster = review_answers.load_roster(review_answers.ROSTER)
    worn = jerseys(matches)
    for m in matches:
        print(f"{m.name}: {score(m, roster, worn)}")


if __name__ == "__main__":
    main()
