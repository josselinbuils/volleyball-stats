import json

import cv2
import numpy as np
import pytest

from volleyball_stats import likeness
from volleyball_stats.likeness import chosen, choose, corrected, dress, guess


def numbers(share=0.4, hair_l=30.0, hair_n=2000.0, skin_l=120.0, low=0.0):
    """`parse`'s numbers of a card: head width, reach, low width, hair and face shares, hair Lab and count, skin Lab and count."""
    return [100.0, 0.7, low, share, 1 - share, hair_l, 135.0, 140.0, hair_n, skin_l, 145.0, 150.0, 9000.0]


def test_the_looks_that_stand_out_are_told():
    assert guess(numbers()) == {"skin": 2, "hair": "dark", "style": "short"}
    assert guess(numbers(hair_l=20))["hair"] == "black"
    assert guess(numbers(hair_l=120))["hair"] == "blond"
    assert guess(numbers(hair_l=80))["hair"] == "grey"
    assert guess(numbers(skin_l=70))["skin"] == likeness.SKINS
    # Going bald, a fringe left: short hair of its colour; no hair seen: short and black, never bald.
    assert guess(numbers(share=0.05, hair_l=75)) == {"skin": 2, "hair": "grey", "style": "short"}
    assert guess(numbers(share=0.01, hair_n=3)) == {"skin": 2, "hair": "black", "style": "short"}
    assert guess(numbers(share=0.9, low=1.0))["style"] == "long"
    assert guess(None) is None


def test_the_figure_and_hair_set_by_name_hold_across_matches(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    choose(a, "Landy", "figure", "woman")
    choose(a, "1:3", "figure", "woman")
    choose(a, "Landy", "hair", "grey")
    (b / likeness.CHOICES).write_text(json.dumps({"Landy": {"hair": "blond", "skin": 4}}), encoding="utf-8")

    # Another match's by name, not by card, this match's over it; nothing but the figure and the hair.
    assert chosen(b) == {"Landy": {"figure": "woman", "hair": "blond"}}
    assert chosen(a)["1:3"] == {"figure": "woman"}
    assert corrected({"hair": "dark", "style": "short", "skin": 2}, chosen(b)["Landy"]) == {"hair": "blond", "style": "short", "skin": 2, "figure": "woman"}
    choose(a, "1:3", "figure", None)
    assert "1:3" not in json.loads((a / likeness.CHOICES).read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        choose(a, "Landy", "figure", "child")
    with pytest.raises(ValueError):
        choose(a, "Landy", "skin", 4)
    with pytest.raises(ValueError):
        choose(a, "Landy", "hair", "green")
    choose(a, "1:3", "hair", "bald")
    assert chosen(a)["1:3"] == {"hair": "bald"}
    # A name from the jersey number alone is another player in each match.
    choose(a, "Joueur 9", "hair", "bald")
    assert chosen(a)["Joueur 9"] == {"hair": "bald"} and "Joueur 9" not in chosen(b)


def test_dress_parses_each_card_once(tmp_path, monkeypatch):
    calls = []

    def parse(pictures):
        calls.append(len(pictures))
        return [numbers(hair_l=120)] * len(pictures)

    monkeypatch.setattr(likeness, "parse", parse)
    monkeypatch.setattr(likeness, "LOADED", [object()])
    card = tmp_path / "0.webp"
    cv2.imwrite(str(card), np.zeros((40, 30, 3), np.uint8))
    choose(tmp_path, "Laure", "figure", "woman")
    people = {0: {"team": 2, "number": 4, "name": "Laure"}, 1: {"team": 1, "number": 2, "name": None}, 2: {"team": 1, "number": None}}

    dress(tmp_path, people, {0: card})
    dress(tmp_path, people, {0: card})

    assert calls == [1]
    assert people[0]["look"] == {"skin": 2, "hair": "blond", "style": "short", "figure": "woman"}
    assert "look" not in people[1] and "look" not in people[2]


def test_looks_go_only_beside_the_video_and_never_for_a_blurred_team():
    from volleyball_stats.web import hide_looks

    def people():
        return {0: {"team": 1, "look": {"hair": "blond"}}, 1: {"team": 2, "look": {"skin": 5}}}

    shown = people()
    hide_looks(shown, set())
    assert all("look" in p for p in shown.values())
    for blurred, kept in ((None, []), ({2}, [0]), ({1, 2}, [])):
        shown = people()
        hide_looks(shown, blurred)
        assert [k for k, p in shown.items() if "look" in p] == kept
