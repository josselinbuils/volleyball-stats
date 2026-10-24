import json

import cv2
import numpy as np
import pytest

from volleyball_stats import teams
from volleyball_stats.players import Row
from volleyball_stats.teams import (
    Teams,
    clock,
    colour_name,
    contact_teams,
    lefts,
    parse_colour,
    parse_teams,
    seconds,
    set_numbers,
    set_starts,
    settle,
    torso,
    track_teams,
    two_means,
)


def row(frame: int, track: int, x: float) -> Row:
    return Row(frame, track, (0.0, 0.0, 1.0, 1.0), 0.9, (0.0, 0.0), (x, 0.0))


def lab(bgr: tuple[int, int, int]) -> np.ndarray:
    return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)


class TestTorso:
    def test_takes_the_upper_middle_of_the_box(self):
        image = np.zeros((100, 100, 3), np.uint8)
        image[20:45, 30:70] = 255

        pixels = torso(image, (0.0, 0.0, 100.0, 100.0))

        assert len(pixels) == 25 * 40 and pixels.min() == 255


class TestTwoMeans:
    def test_splits_light_and_dark_jerseys_and_an_outlier_joins_the_nearer(self):
        colours = {1: lab((240, 240, 240)), 2: lab((230, 235, 235)), 3: lab((80, 40, 30)), 4: lab((70, 35, 25)), 5: lab((10, 10, 10))}
        weights = {1: 100, 2: 80, 3: 90, 4: 120, 5: 60}

        group = two_means(colours, weights)

        assert group[1] == group[2] == 1
        assert group[3] == group[4] == group[5] == 0


class TestLefts:
    def test_puts_on_the_left_the_group_with_most_frames_there(self):
        rows = [row(f, 1, -3.0) for f in range(10)] + [row(f, 2, 4.0) for f in range(10)] + [row(f, 3, 2.0) for f in range(3)]
        rows += [row(f, 1, 3.0) for f in range(100, 110)] + [row(f, 2, -4.0) for f in range(100, 110)]

        # Track 3 is a group-0 libero on the right: outvoted.
        assert lefts(rows, [(0, 20), (95, 115), (200, 210)], {1: 0, 2: 1, 3: 0}) == [0, 1, None]


class TestTrackTeams:
    def test_gives_each_track_the_group_on_its_side_in_its_rally(self):
        rows = [row(f, 1, -3.0) for f in range(5, 15)] + [row(f, 2, 3.0) for f in range(5, 15)] + [row(f, 3, 3.0) for f in range(100, 110)]
        rows += [row(f, 4, -2.0) for f in range(300, 310)]

        # Track 2's colour says group 0 (a libero) but it plays on the right; track 4 plays between
        # rallies, nearest to the second one, where the groups swapped ends.
        out = track_teams(rows, [(0, 20), (95, 120)], [0, 1], {1: 0, 2: 0, 3: 1, 4: 0})

        assert out == {1: 0, 2: 1, 3: 0, 4: 1}

    def test_keeps_the_colour_group_without_rallies(self):
        assert track_teams([row(0, 1, -3.0)], [], [], {1: 1}) == {1: 1}


class TestAssign:
    def test_numbers_team_1_on_the_left_at_the_first_rally_and_fills_rallies_without_players(self, monkeypatch):
        rows = [row(f, 1, 3.0) for f in range(10)] + [row(f, 2, -3.0) for f in range(10)]
        colours = {1: lab((240, 240, 240)), 2: lab((70, 35, 25))}
        monkeypatch.setattr(teams, "sample", lambda video, rows: (colours, {}))

        found = teams.assign(None, rows, [(500, 600), (0, 20)])

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


class TestSettle:
    found = Teams({1: 1, 2: 2}, [1, 2], {1: "#f4f4f4", 2: "#1b2a4a"}, {1: [], 2: []})
    windows = [(0, 100), (3000, 3100)]

    def test_writes_default_names_and_detected_colours_without_a_terminal(self, tmp_path):
        data = settle(tmp_path / "teams.json", self.found, self.windows, 10.0, None, interactive=False)

        assert data == {
            "teams": [
                {"name": None, "colour": None, "jersey": "#f4f4f4", "start": "left"},
                {"name": None, "colour": None, "jersey": "#1b2a4a", "start": "right"},
            ],
            "sets": ["0:00", "2:35"],
        }
        assert json.loads((tmp_path / "teams.json").read_text()) == data

    def test_asks_on_a_terminal_the_first_time_and_reuses_the_file_after(self, tmp_path, monkeypatch):
        answers = iter(["Bègles", "", "", "sparkly", "rouge"])
        monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
        monkeypatch.setattr(teams.shutil, "which", lambda name: None)
        path = tmp_path / "teams.json"

        first = settle(path, self.found, self.windows, 10.0, None, interactive=True)
        again = settle(path, self.found, self.windows, 10.0, None, interactive=True)

        assert [(t["name"], t["colour"]) for t in first["teams"]] == [("Bègles", None), (None, teams.COLOURS["red"])]
        assert again == first
        assert (tmp_path / "teams.jpg").exists()

    def test_takes_the_flag_over_the_file_and_keeps_edited_sets(self, tmp_path):
        path = tmp_path / "teams.json"
        settle(path, self.found, self.windows, 10.0, None, interactive=False)
        path.write_text(path.read_text().replace('"2:35"', '"3:00"'))

        data = settle(path, self.found, self.windows, 10.0, "Home:blanc,Away", interactive=True)

        assert [(t["name"], t["colour"]) for t in data["teams"]] == [("Home", teams.COLOURS["white"]), ("Away", None)]
        assert data["sets"] == ["0:00", "3:00"]
