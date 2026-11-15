"""Score likeness.guess, the 3D figures' hair and skin from each player's card picture, against hand-labelled players.

    uv run python benchmarks/likeness/bench.py [--show]

The labels are in outputs/benchmarks/likeness/truth.json (real people's looks: never committed), by match and card
("team:number"), each field with its acceptable answers, skin from 1 (lightest) to 5. Each labelled player's card
picture is the one the match's review page shows (review/players/KEY.webp), parsed here (a few seconds). Scored against
the made-up looks the figures wore before: dark short hair, the second skin tone. --show lists each player.
"""

import json
import sys
from pathlib import Path

import cv2

from volleyball_stats import likeness
from volleyball_stats.review import page_data

TRUTH = Path("outputs/benchmarks/likeness/truth.json")
MADE_UP = {"hair": "dark", "style": "short", "skin": 2}


def main() -> None:
    truth = {k: v for k, v in json.loads(TRUTH.read_text()).items() if k != "_"}
    found: dict[str, dict] = {}
    for match, labels in truth.items():
        site = Path("outputs/matches") / match / "review"
        cards = {f"{p['team']}:{p['number']}": site / p["photo"].split("?")[0] for p in page_data(site)["people"].values() if p.get("photo")}
        keys = [k for k in labels if k in cards]
        pictures = [cv2.imread(str(cards[k])) for k in keys]
        parsed = likeness.parse([(p, (0, 0, p.shape[1], p.shape[0])) for p in pictures])
        found[match] = {k: likeness.guess(f) or {} for k, f in zip(keys, parsed)}
    for name, look in (("made-up looks (before)", lambda m, k: MADE_UP), ("card picture", lambda m, k: found[m].get(k, {}))):
        hits, total = {"hair": 0, "style": 0, "skin": 0, "skin±1": 0}, 0
        for match, labels in truth.items():
            for card, label in labels.items():
                if card not in found[match]:
                    continue
                g = look(match, card)
                total += 1
                hits["hair"] += g.get("hair") in label["hair"]
                hits["style"] += g.get("style") in label["style"]
                hits["skin"] += g.get("skin") == label["skin"]
                hits["skin±1"] += g.get("skin") is not None and abs(g["skin"] - label["skin"]) <= 1
                if "--show" in sys.argv and look is not MADE_UP and name == "card picture":
                    print(f"{match[5:10]} {card:5} {'/'.join(label['style']):14} {'/'.join(label['hair']):15} {label['skin']}  ->  {g.get('style')!s:6} {g.get('hair')!s:6} {g.get('skin')}")
        print(f"{name:24} {total} players  " + "  ".join(f"{k} {v / total:.0%}" for k, v in hits.items()))
    # The looks that stand out, which the guess is for: bald, grey or blond hair, the darkest skin, long loose hair.
    standing = [(m, k, l) for m, labels in truth.items() for k, l in labels.items() if k in found[m] and (set(l["style"]) <= {"bald", "long"} or set(l["hair"]) <= {"grey", "blond"} or l["skin"] == likeness.SKINS)]
    told = sum((set(l["style"]) <= {"bald", "long"} and found[m][k].get("style") in l["style"]) or (set(l["hair"]) <= {"grey", "blond"} and found[m][k].get("hair") in l["hair"]) or (l["skin"] == likeness.SKINS and found[m][k].get("skin") == likeness.SKINS) for m, k, l in standing)
    print(f"looks that stand out: {told}/{len(standing)} told")


if __name__ == "__main__":
    main()
