import json

import numpy as np

from volleyball_stats.voice import MARGIN_S, RATE, trimmed
from volleyball_stats.speech import JOKE_EVERY, JOKES, clip_name, fitted, number, of_name, replay_lines, script, spelled, voice_index


def touch(rally, t, kind, person, team, result="play"):
    return {"rally": rally, "t": t, "type": kind, "person": person, "team": team, "result": result}


def rally(start, score, winner=1, set_number=1, **extra):
    return {"start": start, "end": start + 5, "set": set_number, "winner": winner, "score": score, **extra}


def match(rallies, contacts):
    people = {"1": {"team": 1, "number": 1, "name": "Anthony"}, "2": {"team": 1, "number": 2, "name": "Manon"}, "3": {"team": 2, "number": 3, "name": "Sam"}, "4": {"team": 1, "number": 4, "name": None}}
    return {"teams": [{"name": "ASPOM 01"}, {"name": "ASPOM 02"}], "people": people, "rallies": rallies, "contacts": contacts}


def texts(data):
    """The lines as the voice says them."""
    return [spelled(line["text"], {}) for line in script(data)]


class TestWords:
    def test_says_scores_in_french(self):
        assert [number(n) for n in (0, 9, 16, 17, 19, 20, 21, 25, 30)] == ["zéro", "neuf", "seize", "dix-sept", "dix-neuf", "vingt", "vingt et un", "vingt-cinq", "trente"]

    def test_says_speeds_in_french(self):
        assert [number(n) for n in (61, 71, 72, 80, 81, 91, 99, 100, 112)] == [
            "soixante et un", "soixante et onze", "soixante-douze", "quatre-vingts", "quatre-vingt-un", "quatre-vingt-onze", "quatre-vingt-dix-neuf", "cent", "cent douze"
        ]

    def test_elides_before_a_vowel(self):
        assert of_name("Attaque de Anthony !") == "Attaque d'Anthony !"
        assert of_name("Attaque de Manon !") == "Attaque de Manon !"
        assert of_name("De Élodie") == "D'Élodie"

    def test_says_figures_aces_and_speeds_in_words(self):
        assert spelled("ASPOM 01 mène, 9 à 6.", {}) == "ASPOM un mène, neuf à six."
        assert spelled("Ace de Sam ! Déjà 3 aces, service à 72 km/h.", {}) == "Èsse de Sam ! Déjà trois èsses, service à soixante-douze kilomètres heure."
        assert spelled("Le service de Grace ne passe pas.", {}) == "Le service de Grace ne passe pas."

    def test_spells_words_for_the_voice(self):
        assert spelled("Attaque de Loick", {"Loick": "Lo-ïk"}) == "Attaque de Lo-ïk"


class TestScript:
    two = [rally(10, [1, 0]), rally(40, [2, 0])]

    def test_names_who_scored_with_the_score(self):
        found = texts(match(self.two, [touch(0, 11, "serve", 3, 2), touch(0, 13, "attack", 2, 1, "point"), touch(1, 41, "serve", 2, 1, "point")]))
        assert any("Manon" in t and "un à zéro" in t and "ASPOM un" in t for t in found)
        assert any("Èsse" in t and "deux à zéro" in t for t in found)

    def test_names_who_gave_the_point_away(self):
        found = texts(match([rally(10, [0, 1], winner=2), rally(40, [0, 2], winner=2)], [touch(0, 11, "serve", 3, 2), touch(0, 12, "attack", 1, 1, "error")]))
        assert any(t.startswith("L'attaque d'Anthony") and "ASPOM deux" in t and "un à zéro" in t for t in found)

    def test_credits_the_attack_over_the_touch_that_lost_it(self):
        contacts = [touch(0, 11, "attack", 3, 2, "point"), touch(0, 12, "dig", 2, 1, "error")]
        found = texts(match([rally(10, [0, 1], winner=2), rally(40, [0, 2], winner=2)], contacts))
        assert any("Sam" in t for t in found)
        assert not any("Manon" in t for t in found)

    def test_says_the_team_when_no_one_is_named(self):
        found = texts(match(self.two, [touch(0, 11, "attack", 4, 1, "point")]))
        assert any("ASPOM un" in t and "Anthony" not in t and ("Attaque gagnante" in t or "conclut" in t) and t.count("ASPOM") == 1 for t in found)

    def test_calls_the_set_and_its_server_at_its_start(self):
        found = script(match(self.two, [touch(0, 11, "serve", 2, 1)]))
        serve = next(line for line in found if line.get("kind") == "serve")
        assert serve["t"] == 10.1 and serve["text"].startswith("C'est parti pour le premier set ! ") and "Manon" in serve["text"] and serve["short"] == "Manon"

    def test_calls_set_points_and_late_ties_before_the_serve(self):
        rallies = [rally(10, [24, 22]), rally(40, [25, 22]), rally(70, [0, 0], set_number=2)]
        assert "Balle de set pour ASPOM un !" in texts(match(rallies, []))
        tied = [rally(10, [20, 20]), rally(40, [21, 20])]
        assert "Égalité, vingt partout." in texts(match(tied, []))

    def test_ends_a_set_and_the_match(self):
        rallies = [rally(10, [25, 20]), rally(40, [1, 0], set_number=2)]
        found = texts(match(rallies, [touch(0, 11, "attack", 2, 1, "point"), touch(1, 41, "attack", 2, 1, "point")]))
        assert any("ASPOM un remporte le set, vingt-cinq à vingt !" in t for t in found)
        assert any("et le match !" in t for t in found)

    def test_notices_a_long_rally(self):
        contacts = [touch(0, 10 + k, "dig", 2, 1) for k in range(9)]
        assert any(line.get("kind") == "reaction" for line in script(match(self.two, contacts)))

    def test_says_a_point_to_replay(self):
        assert "Le point est à rejouer." in texts(match([rally(10, [0, 0], winner=None, redo=True), rally(40, [1, 0])], [touch(0, 11, "serve", 2, 1)]))

    def test_says_nothing_without_teams(self):
        assert script({"teams": None, "people": {}, "rallies": [], "contacts": []}) == []

    def test_gives_a_replay_line_per_player(self):
        assert replay_lines(match([], []))["Anthony"] == "Revoyons ce point au ralenti, à la place d'Anthony."


class TestCalls:
    two = [rally(10, [1, 0]), rally(40, [2, 0])]

    def test_calls_every_named_touch_and_every_server(self):
        contacts = [touch(0, 11, "serve", 3, 2), touch(0, 12, "pass", 1, 1), touch(0, 13, "set", 2, 1), touch(0, 14, "attack", 1, 1), touch(0, 15, "block", 3, 2), touch(0, 16, "dig", 2, 1), touch(0, 17, "relance", 1, 1), touch(0, 18, "attack", 2, 1, "point"), touch(1, 41, "serve", 3, 2), touch(1, 42, "pass", 1, 1)]
        kinds = [line["kind"] for line in script(match(self.two, contacts)) if line.get("kind") not in (None, "reaction", "remark")]
        assert kinds == ["serve", "pass", "set", "attack", "block", "dig", "relance", "serve", "pass"]

    def test_leaves_the_end_to_tell_what_scored_or_lost_the_point(self):
        contacts = [touch(0, 11, "attack", 3, 2, "point"), touch(0, 12, "dig", 2, 1, "error")]
        assert not [line for line in script(match(self.two, contacts)) if line.get("kind") not in (None, "remark")]

    def test_stays_silent_on_a_touch_of_no_one_named(self):
        assert not [line for line in script(match(self.two, [touch(0, 11, "set", 4, 1)])) if line.get("kind") not in (None, "remark")]

    def test_a_call_offers_the_name_alone(self):
        line = next(line for line in script(match(self.two, [touch(0, 11, "serve", 3, 2), touch(0, 12, "set", 2, 1)])) if line.get("kind") == "set")
        assert line["short"] == "Manon"
        assert "Manon" in line["text"]


class TestFitted:
    def line(self, t, text, strong=False):
        return {"t": t, "text": text, "strong": strong}

    def test_drops_a_light_line_that_would_run_into_the_next(self):
        lines = [self.line(1, "a"), self.line(1.5, "b", True), self.line(6, "c")]
        durations = {clip_name(x): 2.0 for x in "abc"}
        assert [row[1] for row in fitted(lines, durations, {})] == [clip_name("b"), clip_name("c")]

    def test_drops_a_light_line_over_the_one_before(self):
        lines = [self.line(1, "a", True), self.line(2, "b"), self.line(9, "c", True)]
        durations = {clip_name(x): 2.0 for x in "abc"}
        assert [row[1] for row in fitted(lines, durations, {})] == [clip_name("a"), clip_name("c")]

    def test_no_line_runs_over_a_cut_of_the_hosted_video_its_short_one_if_it_fits(self):
        lines = [{**self.line(1, "long", True), "short": "s"}, self.line(5, "b", True)]
        durations = {clip_name("long"): 3.0, clip_name("s"): 0.5, clip_name("b"): 2.0}
        assert [row[1] for row in fitted(lines, durations, {}, (2.0, 6.0))] == [clip_name("s")]

    def test_keeps_a_strong_line_whatever_comes_before(self):
        lines = [self.line(1, "a", True), self.line(1.2, "b", True)]
        durations = {clip_name(x): 3.0 for x in "ab"}
        assert len(fitted(lines, durations, {})) == 2

    def test_an_attack_takes_the_room_before_the_set_and_the_dig_after_it(self):
        lines = [
            {**self.line(1, "set"), "short": "s", "kind": "set"},
            {**self.line(2, "attack"), "short": "a", "kind": "attack"},
            {**self.line(2.5, "dig"), "short": "d", "kind": "dig"},
        ]
        durations = {clip_name("set"): 0.9, clip_name("s"): 0.4, clip_name("attack"): 1.0, clip_name("a"): 0.4, clip_name("dig"): 0.9, clip_name("d"): 0.4}
        assert [row[1] for row in fitted(lines, durations, {})] == [clip_name("s"), clip_name("attack")]

    def test_a_rally_s_end_waits_for_the_attack_being_called(self):
        lines = [{**self.line(1, "attack"), "short": "a", "kind": "attack"}, {**self.line(1.5, "end", True), "late": True}]
        durations = {clip_name("attack"): 1.0, clip_name("a"): 0.4, clip_name("end"): 2.0}
        found = fitted(lines, durations, {})
        assert [row[1] for row in found] == [clip_name("attack"), clip_name("end")]
        assert found[1][0] >= found[0][0] + found[0][2]

    def test_a_rally_s_end_is_always_said(self):
        lines = [{**self.line(1, "end", True), "late": True}, {**self.line(1.2, "dig"), "kind": "dig"}]
        durations = {clip_name("end"): 2.0, clip_name("dig"): 0.5}
        assert [row[1] for row in fitted(lines, durations, {})] == [clip_name("end")]

    def test_says_just_the_name_when_the_full_line_has_no_room(self):
        lines = [{**self.line(1, "long"), "short": "n"}, self.line(2, "b", True)]
        durations = {clip_name("long"): 3.0, clip_name("n"): 0.5, clip_name("b"): 1.0}
        assert [row[1] for row in fitted(lines, durations, {})] == [clip_name("n"), clip_name("b")]

    def test_says_it_in_full_with_room(self):
        lines = [{**self.line(1, "long"), "short": "n"}, self.line(9, "b", True)]
        durations = {clip_name("long"): 3.0, clip_name("n"): 0.5, clip_name("b"): 1.0}
        assert fitted(lines, durations, {})[0][1] == clip_name("long")

    def test_leaves_out_a_line_without_audio(self):
        assert fitted([self.line(1, "a", True)], {}, {}) == []

    def test_finds_the_audio_of_the_spelled_text(self):
        assert fitted([self.line(1, "Loick", True)], {clip_name("Lo-ik"): 1.0}, {"Loick": "Lo-ik"}) == [[1, clip_name("Lo-ik"), 1.0, "Loick"]]

    def test_a_remark_ends_before_the_next_serve_or_is_not_said(self):
        lines = [{**self.line(1, "end", True), "late": True}, {**self.line(1, "remark"), "late": True, "until": 4}]
        assert [row[3] for row in fitted(lines, {clip_name("end"): 2.0, clip_name("remark"): 1.5}, {})] == ["end"]
        assert [row[3] for row in fitted(lines, {clip_name("end"): 1.0, clip_name("remark"): 1.5}, {})] == ["end", "remark"]


class TestVoiceIndex:
    def test_none_without_audio(self, tmp_path):
        assert voice_index(tmp_path, match([], [])) is None

    def test_a_changed_match_loses_only_the_lines_no_longer_true(self, tmp_path):
        data = match([rally(10, [1, 0]), rally(40, [2, 0])], [touch(0, 11, "attack", 2, 1, "point"), touch(1, 41, "attack", 2, 1, "point")])
        folder = tmp_path / "voice"
        folder.mkdir()
        made = {clip_name(spelled(line["text"], {})): 1.0 for line in script(data)}
        (folder / "durations.json").write_text(json.dumps(made))
        full = voice_index(tmp_path, data)
        data["rallies"][1]["score"] = [1, 1]
        data["rallies"][1]["winner"] = 2
        changed = voice_index(tmp_path, data)
        assert len(changed["lines"]) < len(full["lines"])


class TestTrimmed:
    def test_cuts_the_silence_at_both_ends_and_keeps_a_margin(self):
        words = np.full(RATE, 0.5, dtype=np.float32)
        audio = np.concatenate([np.zeros(RATE), words, np.zeros(RATE)])
        assert abs(len(trimmed(audio)) - (RATE + 2 * MARGIN_S * RATE)) <= 2

    def test_keeps_a_pause_between_words(self):
        audio = np.concatenate([np.full(100, 0.5), np.zeros(RATE), np.full(100, 0.5)]).astype(np.float32)
        assert len(trimmed(audio)) >= RATE + 200

    def test_leaves_silence_alone(self):
        assert len(trimmed(np.zeros(100))) == 100


class TestLively:
    @staticmethod
    def points(scores, contacts=None, **extra):
        """A set of `scores`, each won by its winner's attack of no one named unless `contacts` says otherwise, then a rally
        of the next set: the match's end says goodbye instead of a remark."""
        rallies = [rally(10 + 30 * k, list(score), winner=winner, **extra) for k, (score, winner) in enumerate(scores)]
        if contacts is None:
            contacts = [touch(k, 11 + 30 * k, "attack", 4, winner, "point") for k, (_, winner) in enumerate(scores)]
        n = len(rallies)
        last = scores[-1][0]
        more = [rally(10 + 30 * n, [last[0] + 1, last[1]]), rally(10 + 30 * (n + 1), [1, 0], set_number=2)]
        return match([*rallies, *more], [*contacts, *(touch(n + k, 11 + 30 * (n + k), "attack", 4, 1, "point") for k in range(2))])

    def test_never_says_a_touch_the_same_way_twice_in_a_row(self):
        contacts = [touch(k, 11 + 30 * k, "serve", 2, 1) for k in range(12)]
        calls = [line["text"] for line in script(self.points([((k + 1, 0), 1) for k in range(12)], contacts)) if line.get("kind") == "serve"]
        calls[0] = calls[0].split("! ")[-1]
        assert all(a != b for a, b in zip(calls, calls[1:])) and len(set(calls)) >= 3

    def test_says_who_takes_the_lead(self):
        found = texts(self.points([((0, 1), 2), ((1, 1), 1), ((2, 1), 1)]))
        assert any("égalise" in t or "partout" in t for t in found)
        assert any("passe devant" in t or "prend l'avantage" in t for t in found)

    def test_remarks_on_a_streak_and_its_end(self):
        scores = [((k + 1, 0), 1) for k in range(5)] + [((5, 1), 2)]
        found = texts(self.points(scores))
        assert any("Troisième point d'affilée" in t or "troisième point de suite" in t for t in found)
        assert any("cinq points" in t for t in found)
        assert any("série" in t for t in found)

    def test_remarks_on_a_comeback(self):
        scores = [((0, k + 1), 2) for k in range(4)] + [((k + 1, 4), 1) for k in range(4)]
        assert any("quatre points de retard" in t for t in texts(self.points(scores)))

    def test_counts_a_player_s_aces(self):
        contacts = [touch(k, 11 + 30 * k, "serve", 2, 1, "point") for k in range(3)]
        found = texts(self.points([((k + 1, 0), 1) for k in range(3)], contacts))
        assert any("Manon" in t and ("Deuxième èsse" in t or "de deux" in t) for t in found)
        assert any("trois èsses" in t for t in found)

    def test_a_joke_now_and_then_never_more_often(self):
        rallies = 40
        contacts = [touch(k, 11 + 30 * k, "serve", 3, 2, "point") for k in range(rallies)]
        jokes = {joke for ways in JOKES.values() for joke in ways}
        said = [line for line in script(self.points([((0, k + 1), 2) for k in range(rallies)], contacts)) if any(line["text"].startswith(j.split("{")[0]) for j in jokes)]
        assert 1 < len(said) <= rallies // JOKE_EVERY + 1
        assert all(b["t"] - a["t"] >= 30 * JOKE_EVERY - 1 for a, b in zip(said, said[1:]))
        assert len({line["text"] for line in said}) == len(said)

    def test_no_joke_names_a_player(self):
        assert not any("{name}" in joke for ways in JOKES.values() for joke in ways)

    def test_welcomes_and_says_goodbye(self):
        found = texts(match([rally(10, [25, 20])], [touch(0, 11, "attack", 2, 1, "point")]))
        assert found[0].startswith("Bienvenue") and "ASPOM un" in found[0] and found[-1].startswith("Merci")

    def test_says_a_timeout_and_who_asked_for_it(self):
        data = self.points([((1, 0), 1), ((2, 0), 1)])
        data["timeouts"] = [{"start": 20, "end": 35, "team": 2}]
        found = script(data)
        assert any(line["text"] in ("Temps mort pour ASPOM 02.", "ASPOM 02 demande un temps mort.") and line["t"] == 21 for line in found)
