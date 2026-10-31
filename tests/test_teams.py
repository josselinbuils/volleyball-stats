import json
import os
import subprocess
from datetime import datetime

import cv2
import numpy as np
import pytest

from volleyball_stats import teams
from volleyball_stats.players import Row
from volleyball_stats.teams import (
    Teams,
    changed_ends,
    clock,
    colour_name,
    contact_teams,
    default_title,
    lefts,
    parse_date,
    parse_colour,
    parse_teams,
    part,
    seconds,
    set_numbers,
    recording_date,
    set_starts,
    settle,
    track_teams,
)


def row(frame: int, track: int, x: float) -> Row:
    return Row(frame, track, (0.0, 0.0, 1.0, 1.0), 0.9, (0.0, 0.0), (x, 0.0))


def lab(bgr: tuple[int, int, int]) -> np.ndarray:
    return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)


class TestPart:
    def test_takes_the_upper_middle_of_the_box_for_the_torso(self):
        image = np.zeros((100, 100, 3), np.uint8)
        image[20:45, 30:70] = 255

        pixels = part(image, (0.0, 0.0, 100.0, 100.0))

        assert len(pixels) == 25 * 40 and pixels.min() == 255

    def test_takes_the_shorts_below_it(self):
        image = np.zeros((100, 100, 3), np.uint8)
        image[50:65, 30:70] = 255

        assert part(image, (0.0, 0.0, 100.0, 100.0), teams.SHORTS).min() == 255


class TestLefts:
    def test_follows_the_tracks_through_a_break_whatever_their_looks(self):
        # Tracks 1 and 2 play both rallies; 3 and 4 only the second, dressed like the other side.
        rows = [row(f, 1, -3.0) for f in range(10)] + [row(f, 2, 3.0) for f in range(10)]
        rows += [row(f, 1, -3.0) for f in range(100, 110)] + [row(f, 2, 3.0) for f in range(100, 110)]
        rows += [row(f, 3, -2.0) for f in range(100, 110)] + [row(f, 4, 2.0) for f in range(100, 110)]
        looks = {1: np.zeros(6), 2: np.full(6, 200.0), 3: np.full(6, 200.0), 4: np.zeros(6)}

        assert lefts(rows, [(0, 20), (95, 115), (200, 210)], looks, 30.0) == [0, 0, None]

    def test_matches_looks_after_a_long_break_and_sees_the_ends_changed(self):
        rows = [row(f, 1, -3.0) for f in range(10)] + [row(f, 2, 3.0) for f in range(10)]
        rows += [row(f, 3, 3.0) for f in range(100, 110)] + [row(f, 4, -3.0) for f in range(100, 110)]
        looks = {1: np.zeros(6), 2: np.full(6, 200.0), 3: np.full(6, 10.0), 4: np.full(6, 190.0)}

        assert lefts(rows, [(0, 20), (95, 115)], looks, 30.0) == [0, 1]

    def test_keeps_the_ends_when_the_looks_only_lean_to_a_change(self):
        # Half the players after the break look like a player of the other side: no clear majority.
        rows = [row(f, 1, -3.0) for f in range(10)] + [row(f, 2, 3.0) for f in range(10)]
        rows += [row(f, 3, 3.0) for f in range(100, 110)] + [row(f, 4, 3.0) for f in range(100, 110)]
        looks = {1: np.zeros(6), 2: np.full(6, 200.0), 3: np.full(6, 10.0), 4: np.full(6, 190.0)}

        assert lefts(rows, [(0, 20), (95, 115)], looks, 30.0) == [0, 0]

    def test_changes_the_ends_at_a_set_break_when_the_teams_look_alike(self):
        # One kit, a shade lighter on the right: the looks would keep each team on its side.
        rows = [row(f, 1, -3.0) for f in range(10)] + [row(f, 2, 3.0) for f in range(10)]
        rows += [row(f, 3, -3.0) for f in range(3000, 3010)] + [row(f, 4, 3.0) for f in range(3000, 3010)]
        looks = {1: np.full(6, 100.0), 2: np.full(6, 120.0), 3: np.full(6, 100.0), 4: np.full(6, 120.0)}

        assert lefts(rows, [(0, 20), (2990, 3020)], looks, 30.0) == [0, 1]
        assert lefts(rows, [(0, 20), (2990, 3020)], looks, 60.0) == [0, 0]
        # Known set starts decide instead: a long break inside a set keeps the ends, a short one
        # between sets changes them.
        assert lefts(rows, [(0, 20), (2990, 3020)], looks, 30.0, [0.0, 200.0]) == [0, 0]
        assert lefts(rows, [(0, 20), (2990, 3020)], looks, 60.0, [0.0, 40.0]) == [0, 1]


class TestChangedEnds:
    def test_needs_the_swap_share_of_frames_matched_to_the_other_side(self):
        before = {1: (10, True), 2: (10, False)}
        looks = {1: np.zeros(6), 2: np.full(6, 200.0), 3: np.full(6, 5.0), 4: np.full(6, 195.0), 5: np.full(6, 190.0)}

        assert changed_ends(before, {3: (10, False), 4: (10, True)}, looks)
        assert not changed_ends(before, {3: (10, False), 5: (10, False)}, looks)
        assert not changed_ends({}, {3: (10, False)}, looks)


class TestTrackTeams:
    def test_gives_each_track_the_team_on_its_side_in_its_rally(self):
        rows = [row(f, 1, -3.0) for f in range(5, 15)] + [row(f, 2, 3.0) for f in range(5, 15)] + [row(f, 3, 3.0) for f in range(100, 110)]
        rows += [row(f, 4, -2.0) for f in range(300, 310)]

        # Track 4 plays between rallies, nearest to the second one, where the teams swapped ends.
        out = track_teams(rows, [(0, 20), (95, 120)], [0, 1])

        assert out == {1: 0, 2: 1, 3: 0, 4: 1}

    def test_reads_the_side_inside_the_rally_only(self):
        # Track 5 changes ends during the break, then plays the second rally on the left.
        rows = [row(f, 5, 3.0) for f in range(30, 90)] + [row(f, 5, -3.0) for f in range(95, 120)]

        assert track_teams(rows, [(0, 20), (95, 120)], [0, 1]) == {5: 1}

    def test_puts_team_0_on_the_left_without_rallies(self):
        assert track_teams([row(0, 1, -3.0), row(0, 2, 3.0)], [], []) == {1: 0, 2: 1}


class TestAssign:
    def test_numbers_team_1_on_the_left_at_the_first_rally_and_fills_rallies_without_players(self, monkeypatch):
        rows = [row(f, 1, 3.0) for f in range(10)] + [row(f, 2, -3.0) for f in range(10)]
        looks = {1: np.concatenate([lab((240, 240, 240)), lab((0, 0, 0))]), 2: np.concatenate([lab((70, 35, 25)), lab((0, 0, 0))])}
        monkeypatch.setattr(teams, "sample", lambda video, rows: (looks, {}))

        found = teams.assign(None, rows, [(500, 600), (0, 20)], 30.0)

        assert found.tracks == {1: 2, 2: 1}
        assert found.left == [1, 1]
        assert found.colours == {1: "#1b2a4a", 2: "#f4f4f4"}


class TestContactTeams:
    def test_takes_the_team_on_the_contacts_side_in_its_rally(self):
        typed = [(8, 0, 0, "serve", "right"), (40, 0, 0, "pass", "left"), (210, 0, 0, "block", "left"), (500, 0, 0, "serve", "left")]

        assert contact_teams(typed, [(10, 50), (200, 260)], [1, 2], 3) == [2, 1, 2, None]


class TestSets:
    fps = 10.0
    windows = [(0, 100), (300, 400), (2000, 2100), (2300, 2400), (3000, 3100)]

    def test_starts_a_set_when_the_teams_change_ends_after_a_set_break(self):
        # Sides swap after 160 s (a set break) and after 20 s (the deciding set's swap, no new set).
        assert set_starts(self.windows, [1, 1, 2, 1, 1], self.fps) == [0.0, 120.0]

    def test_ignores_a_long_break_without_a_change_of_ends_and_rallies_with_unknown_sides(self):
        assert set_starts(self.windows, [1, None, 1, 1, 1], self.fps) == [0.0]
        assert set_starts(self.windows, [1, None, 2, 2, 2], self.fps) == [0.0, 105.0]

    def test_numbers_each_rally_by_the_last_set_started_before_it(self):
        assert set_numbers(self.windows, [0.0, 120.0], self.fps) == [1, 1, 2, 2, 2]

    def test_reads_and_writes_set_starts_as_clock_times(self):
        assert [clock(s) for s in (0, 125.4, 3725)] == ["0:00", "2:05", "1:02:05"]
        assert [seconds(s) for s in ("0:00", "2:05", "1:02:05", 30)] == [0.0, 125.0, 3725.0, 30.0]


class TestColours:
    def test_names_footage_colours_white_navy_black_and_hues(self):
        # Gym footage: a white jersey greyed and blued, a navy one nearly black, a libero in black.
        assert colour_name(np.array([150.0, 131.0, 118.0])) == "white"
        assert colour_name(np.array([17.0, 130.0, 120.0])) == "navy"
        assert colour_name(np.array([20.0, 128.0, 129.0])) == "black"
        assert colour_name(lab((40, 40, 210))) == "red"
        assert colour_name(lab((30, 20, 110))) == "dark red"
        assert colour_name(lab((60, 160, 40))) == "green"

    def test_parses_hex_codes_and_english_and_french_names(self):
        assert parse_colour("#1F4E9C") == "#1f4e9c"
        assert parse_colour("#abc") == "#aabbcc"
        assert parse_colour(" Rouge ") == parse_colour("red") == teams.COLOURS["red"]
        assert parse_colour("marine") == teams.COLOURS["navy"]
        assert parse_colour("sparkly") is None

    def test_parses_the_teams_flag_with_optional_colours(self):
        assert parse_teams("Bègles:#1f4e9c,Mérignac:rouge") == [("Bègles", "#1f4e9c"), ("Mérignac", teams.COLOURS["red"])]
        assert parse_teams("Bègles") == [("Bègles", None), (None, None)]
        assert parse_teams(",Visitors:") == [(None, None), ("Visitors", None)]
        with pytest.raises(ValueError):
            parse_teams("A:sparkly,B")


class TestDate:
    def test_parses_day_month_year_and_iso_dates(self):
        assert parse_date("12/11/2026") == parse_date(" 2026-11-12 ") == "2026-11-12"
        assert parse_date("1/2/2026") == "2026-02-01"
        assert parse_date("31/02/2026") is None
        assert parse_date("2026-13-01") is None
        assert parse_date("12.11.2026") is None
        assert parse_date("") is None

    def test_takes_the_recording_date_from_the_creation_time_tag(self, tmp_path, monkeypatch):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"")
        monkeypatch.setattr(teams.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "2026-11-12T12:30:00.000000Z\n", ""))

        assert recording_date(video) == "2026-11-12"

    def test_falls_back_to_the_modification_date_without_a_tag_or_ffprobe(self, tmp_path, monkeypatch):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"")
        stamp = datetime(2016, 12, 21, 18, 0).timestamp()
        os.utime(video, (stamp, stamp))
        monkeypatch.setattr(teams.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "\n", ""))
        assert recording_date(video) == "2016-12-21"

        def missing(*args, **kwargs):
            raise FileNotFoundError("ffprobe")

        monkeypatch.setattr(teams.subprocess, "run", missing)
        assert recording_date(video) == "2016-12-21"

    def test_titles_the_match_with_the_team_names(self):
        assert default_title(["ASPOM Bègles", "VC Talence"]) == "Match ASPOM Bègles vs VC Talence"


class TestSettle:
    found = Teams({1: 1, 2: 2}, [1, 2], {1: "#f4f4f4", 2: "#1b2a4a"}, {1: [], 2: []})
    windows = [(0, 100), (3000, 3100)]
    recorded = "2026-11-12"

    def test_writes_default_names_detected_colours_and_the_recording_date_without_a_terminal(self, tmp_path):
        data = settle(tmp_path / "teams.json", self.found, self.windows, 10.0, None, False, self.recorded)

        assert data == {
            "teams": [
                {"name": None, "colour": None, "jersey": "#f4f4f4", "start": "left"},
                {"name": None, "colour": None, "jersey": "#1b2a4a", "start": "right"},
            ],
            "date": "2026-11-12",
            "title": None,
            "sets": ["0:00", "2:35"],
            "scores": [None, None],
        }
        assert json.loads((tmp_path / "teams.json").read_text()) == data

    def test_asks_on_a_terminal_the_first_time_and_reuses_the_file_after(self, tmp_path, monkeypatch):
        answers = iter(["Bègles", "", "", "sparkly", "rouge", "", "", "", "", ""])
        prompts = []
        monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))
        monkeypatch.setattr(teams.shutil, "which", lambda name: None)
        path = tmp_path / "teams.json"

        first = settle(path, self.found, self.windows, 10.0, None, True, self.recorded)
        again = settle(path, self.found, self.windows, 10.0, None, True, self.recorded)

        assert [(t["name"], t["colour"]) for t in first["teams"]] == [("Bègles", None), (None, teams.COLOURS["red"])]
        assert (first["date"], first["title"]) == ("2026-11-12", None)
        assert prompts[5:7] == ["Date du match [détectée : 12/11/2026] : ", "Titre du match [Match Bègles vs Équipe 2] : "]
        assert again == first
        assert (tmp_path / "teams.jpg").exists()

    def test_asks_the_date_again_until_it_is_one_and_keeps_a_typed_title(self, tmp_path, monkeypatch):
        answers = iter(["21.12.2016", "21/12/2016", "Finale", "", "", ""])
        prompts = []
        monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))

        data = settle(tmp_path / "teams.json", self.found, self.windows, 10.0, "ASPOM,Talence", True, self.recorded)

        assert (data["date"], data["title"]) == ("2016-12-21", "Finale")
        assert prompts[2] == "Titre du match [Match ASPOM vs Talence] : "

    def test_takes_the_flags_over_the_file_and_keeps_edited_sets(self, tmp_path):
        path = tmp_path / "teams.json"
        settle(path, self.found, self.windows, 10.0, None, False, self.recorded, title="Finale")
        path.write_text(path.read_text().replace('"2:35"', '"3:00"'))

        kept = settle(path, self.found, self.windows, 10.0, None, True, "2030-01-01")
        data = settle(path, self.found, self.windows, 10.0, "Home:blanc,Away", True, self.recorded, "2016-12-21", "")

        assert (kept["date"], kept["title"]) == ("2026-11-12", "Finale")
        assert [(t["name"], t["colour"]) for t in data["teams"]] == [("Home", teams.COLOURS["white"]), ("Away", None)]
        assert (data["date"], data["title"]) == ("2016-12-21", None)
        assert data["sets"] == ["0:00", "3:00"]

    def test_gives_a_file_from_before_the_date_the_recording_date_without_asking(self, tmp_path, monkeypatch):
        path = tmp_path / "teams.json"
        path.write_text(json.dumps({"teams": [{"name": "Home", "colour": None}, {"name": None, "colour": None}], "sets": ["0:00"]}))
        monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail(prompt))

        data = settle(path, self.found, self.windows, 10.0, None, True, self.recorded)

        assert (data["teams"][0]["name"], data["date"], data["title"]) == ("Home", "2026-11-12", None)

    def test_asks_each_set_start_and_final_score_once(self, tmp_path, monkeypatch):
        answers = iter(["", "", "", "", "", "", "25-21", "2:3x", "0:00", "3:10", "vingt", "18 – 25"])
        prompts = []
        monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))
        monkeypatch.setattr(teams.shutil, "which", lambda name: None)
        path = tmp_path / "teams.json"

        first = settle(path, self.found, self.windows, 10.0, None, True, self.recorded)
        monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail(prompt))
        again = settle(path, self.found, self.windows, 10.0, None, True, self.recorded)

        assert (first["sets"], first["scores"]) == (["0:00", "3:10"], ["25-21", "18-25"])
        assert prompts[6:8] == ["Score final du set 1 (Équipe 1 – Équipe 2) [vide si inconnu] : ", "Début du set 2 [détecté : 2:35] : "]
        assert again == first

    def test_takes_set_starts_and_scores_from_the_parameters(self, tmp_path):
        path = tmp_path / "teams.json"

        data = settle(path, self.found, self.windows, 10.0, None, False, self.recorded, sets=["0:00", "4:06"], scores=["25:21", ""])

        assert (data["sets"], data["scores"]) == (["0:00", "4:06"], ["25-21", None])
        for sets, scores in ((None, ["25"]), (None, ["25-21", "1-2", "3-4"]), (["soon"], None)):
            with pytest.raises(ValueError):
                settle(path, self.found, self.windows, 10.0, None, False, self.recorded, sets=sets, scores=scores)
