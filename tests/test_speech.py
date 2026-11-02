import json

from volleyball_stats.speech import clip_name, fitted, number, of_name, replay_lines, script, spelled, team_name, voice_index


def touch(rally, t, kind, person, team, result="play"):
    return {"rally": rally, "t": t, "type": kind, "person": person, "team": team, "result": result}


def rally(start, score, winner=1, set_number=1, **extra):
    return {"start": start, "end": start + 5, "set": set_number, "winner": winner, "score": score, **extra}


def match(rallies, contacts):
    people = {"1": {"team": 1, "number": 1, "name": "Anthony"}, "2": {"team": 1, "number": 2, "name": "Manon"}, "3": {"team": 2, "number": 3, "name": "Sam"}, "4": {"team": 1, "number": 4, "name": None}}
    return {"teams": [{"name": "ASPOM 01"}, {"name": "ASPOM 02"}], "people": people, "rallies": rallies, "contacts": contacts}


def texts(data):
    return [line["text"] for line in script(data)]


class TestWords:
    def test_says_scores_in_french(self):
        assert [number(n) for n in (0, 9, 16, 17, 19, 20, 21, 25, 30)] == ["zéro", "neuf", "seize", "dix-sept", "dix-neuf", "vingt", "vingt et un", "vingt-cinq", "trente"]

    def test_elides_before_a_vowel(self):
        assert of_name("Attaque de Anthony !") == "Attaque d'Anthony !"
        assert of_name("Attaque de Manon !") == "Attaque de Manon !"
        assert of_name("De Élodie") == "D'Élodie"

    def test_says_a_team_s_number(self):
        assert team_name("ASPOM 01") == "ASPOM un"
        assert team_name("Les Bleus") == "Les Bleus"

    def test_spells_words_for_the_voice(self):
        assert spelled("Attaque de Loick", {"Loick": "Lo-ïk"}) == "Attaque de Lo-ïk"


class TestScript:
    two = [rally(10, [1, 0]), rally(40, [2, 0])]

    def test_names_who_scored_with_the_score(self):
        found = texts(match(self.two, [touch(0, 11, "serve", 3, 2), touch(0, 13, "attack", 2, 1, "point"), touch(1, 41, "serve", 2, 1, "point")]))
        assert any("Manon" in t and "ASPOM un mène, un à zéro." in t for t in found)
        assert any("Èsse" in t and "deux à zéro" in t for t in found)

    def test_names_who_gave_the_point_away(self):
        found = texts(match([rally(10, [0, 1], winner=2), rally(40, [0, 2], winner=2)], [touch(0, 11, "serve", 3, 2), touch(0, 12, "attack", 1, 1, "error")]))
        assert any(t.startswith("L'attaque d'Anthony ne passe pas.") and "ASPOM deux mène, un à zéro." in t for t in found)

    def test_credits_the_attack_over_the_touch_that_lost_it(self):
        contacts = [touch(0, 11, "attack", 3, 2, "point"), touch(0, 12, "dig", 2, 1, "error")]
        found = texts(match([rally(10, [0, 1], winner=2), rally(40, [0, 2], winner=2)], contacts))
        assert any("Sam" in t for t in found)
        assert not any("Manon" in t for t in found)

    def test_says_the_team_when_no_one_is_named(self):
        found = texts(match(self.two, [touch(0, 11, "attack", 4, 1, "point")]))
        assert any("Attaque gagnante pour ASPOM un" in t for t in found)

    def test_calls_the_set_and_its_server_at_its_start(self):
        found = script(match(self.two, [touch(0, 11, "serve", 2, 1)]))
        assert found[0] == {"t": 9.3, "text": "Set un. Manon au service.", "strong": False}

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
        assert "Quel échange !" in texts(match(self.two, contacts))

    def test_says_a_point_to_replay(self):
        assert "Le point est à rejouer." in texts(match([rally(10, [0, 0], winner=None, redo=True), rally(40, [1, 0])], [touch(0, 11, "serve", 2, 1)]))

    def test_says_nothing_without_teams(self):
        assert script({"teams": None, "people": {}, "rallies": [], "contacts": []}) == []

    def test_gives_a_replay_line_per_player(self):
        assert replay_lines(match([], []))["Anthony"] == "Revoyons ce point au ralenti, à la place d'Anthony."


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

    def test_keeps_a_strong_line_whatever_comes_before(self):
        lines = [self.line(1, "a", True), self.line(1.2, "b", True)]
        durations = {clip_name(x): 3.0 for x in "ab"}
        assert len(fitted(lines, durations, {})) == 2

    def test_leaves_out_a_line_without_audio(self):
        assert fitted([self.line(1, "a", True)], {}, {}) == []

    def test_finds_the_audio_of_the_spelled_text(self):
        assert fitted([self.line(1, "Loick", True)], {clip_name("Lo-ik"): 1.0}, {"Loick": "Lo-ik"}) == [[1, clip_name("Lo-ik"), 1.0]]


class TestVoiceIndex:
    def test_none_without_audio(self, tmp_path):
        assert voice_index(tmp_path, match([], [])) is None

    def test_a_changed_match_loses_only_the_lines_no_longer_true(self, tmp_path):
        data = match([rally(10, [1, 0]), rally(40, [2, 0])], [touch(0, 11, "attack", 2, 1, "point"), touch(1, 41, "attack", 2, 1, "point")])
        folder = tmp_path / "voice"
        folder.mkdir()
        made = {clip_name(line["text"]): 1.0 for line in script(data)}
        (folder / "durations.json").write_text(json.dumps(made))
        full = voice_index(tmp_path, data)
        data["rallies"][1]["score"] = [1, 1]
        data["rallies"][1]["winner"] = 2
        changed = voice_index(tmp_path, data)
        assert len(changed["lines"]) < len(full["lines"])
