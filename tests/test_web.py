import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.web import contacts, padded, player_spans, result, spot, track_feet, write_site, zone, zone_cells

# Pixels are court metres.
IDENTITY = Calibration(np.eye(3))


class TestSpot:
    boxes = np.array([[100.0, 50.0, 140.0, 200.0], [300.0, 80.0, 330.0, 180.0], [105.0, 120.0, 135.0, 160.0]])
    feet = np.array([[-3.0, 1.0], [2.0, -2.0], [-4.0, -3.0]])

    def test_places_a_floor_contact_at_the_balls_floor_projection(self):
        assert spot("floor", (1.5, -2.0), self.boxes, self.feet, IDENTITY, 15) == (1.5, -2.0)

    def test_takes_the_feet_of_the_player_under_the_ball_whose_head_is_nearest(self):
        assert spot("attack", (120.0, 40.0), self.boxes, self.feet, IDENTITY, 15) == (-3.0, 1.0)
        assert spot("dig", (120.0, 125.0), self.boxes, self.feet, IDENTITY, 15) == (-4.0, -3.0)

    def test_takes_the_nearest_player_horizontally_when_none_is_under_the_ball(self):
        assert spot("serve", (250.0, 60.0), self.boxes, self.feet, IDENTITY, 15) == (2.0, -2.0)

    def test_has_no_position_without_players(self):
        assert spot("set", (120.0, 40.0), np.empty((0, 4)), np.empty((0, 2)), IDENTITY, 15) is None


class TestTrackFeet:
    players = {
        10: [{"track": "4", "court_x": "1.0", "court_y": "2.0"}, {"track": "5", "court_x": "-3.0", "court_y": "0.0"}],
        14: [{"track": "4", "court_x": "3.0", "court_y": "4.0"}],
    }

    def test_takes_the_tracks_feet_at_the_frame(self):
        assert track_feet(4, 10, self.players, 2) == (1.0, 2.0)

    def test_interpolates_over_a_detection_gap(self):
        assert track_feet(4, 12, self.players, 2) == (2.0, 3.0)

    def test_has_no_position_when_the_track_is_not_that_close(self):
        assert track_feet(5, 13, self.players, 2) is None
        assert track_feet(7, 10, self.players, 2) is None


class TestZone:
    def test_numbers_the_left_half_from_its_end_line(self):
        # Facing the net, the left team's left hand is toward the far sideline (y < 0).
        assert [zone(-1.5, y) for y in (-3, 0, 3)] == [4, 3, 2]
        assert [zone(-6.0, y) for y in (-3, 0, 3)] == [5, 6, 1]

    def test_mirrors_the_right_half(self):
        assert [zone(1.5, y) for y in (-3, 0, 3)] == [2, 3, 4]
        assert [zone(6.0, y) for y in (-3, 0, 3)] == [1, 6, 5]

    def test_puts_points_off_the_court_in_the_nearest_zone(self):
        assert zone(-11.0, 5.5) == 1  # a server behind the end line, near corner
        assert zone(10.5, -6.0) == 1

    def test_cells_cover_both_halves_with_each_zone_once(self):
        cells = zone_cells()
        assert sorted(c["zone"] for c in cells if c["x"] < 0) == [1, 2, 3, 4, 5, 6]
        assert sorted(c["zone"] for c in cells if c["x"] >= 0) == [1, 2, 3, 4, 5, 6]
        assert sum(c["w"] * c["h"] for c in cells) == 18 * 9


class TestResult:
    attack = {"type": "attack", "side": "right"}

    def landing(self, side: str, x: float, y: float = 0.0) -> dict:
        return {"type": "floor", "side": side, "x": x, "y": y}

    def test_is_a_point_when_the_ball_lands_in_the_other_court(self):
        assert result(self.attack, self.landing("left", -5.0, 2.0)) == "point"

    def test_is_an_error_when_the_ball_lands_out_on_its_own_side_or_in_the_net(self):
        assert result(self.attack, self.landing("left", -9.5)) == "error"
        assert result(self.attack, self.landing("left", -5.0, 4.8)) == "error"
        assert result(self.attack, self.landing("right", 4.0)) == "error"
        assert result(self.attack, {"type": "net", "side": "right", "x": 0.5, "y": 0.0}) == "error"

    def test_is_in_play_when_the_ball_is_played_again_or_the_rally_ends(self):
        assert result(self.attack, {"type": "dig", "side": "left", "x": -6.0, "y": 0.0}) == "play"
        assert result(self.attack, None) == "play"


class TestContacts:
    def test_builds_the_rallies_contacts_with_positions_zones_and_results(self):
        typed = [
            {"frame": "8", "x": "-10", "y": "3", "type": "serve", "side": "left"},  # in the window's lead
            {"frame": "40", "x": "6", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "45", "x": "7", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "100", "x": "8", "y": "0", "type": "serve", "side": "right"},
        ]
        players = {8: [{"x1": "-10.5", "y1": "1", "x2": "-9.5", "y2": "3", "court_x": "-10.4", "court_y": "3.1"}]}

        out = contacts(typed, [(10, 60), (100, 130)], players, 10.0, IDENTITY, 15)

        assert [(c["t"], c["rally"], c["type"]) for c in out] == [(0.8, 0, "serve"), (4.0, 0, "floor"), (4.5, 0, "floor"), (10.0, 1, "serve")]
        assert (out[0]["x"], out[0]["y"], out[0]["zone"]) == (-10.4, 3.1, 1)
        # The floor contact is the ball's floor projection; the dead ball after it has no position.
        assert (out[1]["x"], out[1]["y"]) == (6.0, -1.0)
        assert out[2]["x"] is None and out[2]["zone"] is None
        assert out[3]["x"] is None  # no player at that frame
        assert [c["result"] for c in out] == ["point", "play", "play", "play"]
        assert [c["track"] for c in out] == [None, None, None, None]

    def test_places_an_attributed_contact_at_its_players_feet_else_under_the_ball(self):
        typed = [
            {"frame": "10", "x": "0", "y": "0", "type": "attack", "side": "left", "track": "7"},
            {"frame": "20", "x": "0", "y": "0", "type": "dig", "side": "right", "track": "9"},  # track not found
        ]
        under = {"x1": "-1", "y1": "-1", "x2": "1", "y2": "1", "court_x": "-1.0", "court_y": "0.5", "track": "8"}
        players = {
            10: [under, {"x1": "5", "y1": "5", "x2": "6", "y2": "7", "court_x": "-4.0", "court_y": "2.0", "track": "7"}],
            20: [{**under, "court_x": "2.0"}],
        }

        out = contacts(typed, [(5, 30)], players, 10.0, IDENTITY, 15)

        assert [(c["x"], c["y"], c["track"]) for c in out] == [(-4.0, 2.0, 7), (2.0, 0.5, 9)]


class TestPadded:
    def test_widens_the_windows_within_the_video_and_merges_overlaps(self):
        assert padded([(5, 20), (45, 50), (58, 70), (95, 99)], 10, 100) == [(0, 30), (35, 80), (85, 99)]


class TestPlayerSpans:
    def test_keeps_every_steps_frame_of_each_window_rounded_to_the_centimetre_left_team_first(self):
        rows = [
            {"frame": "3", "team": "right", "court_x": "3.14159", "court_y": "-1.005"},
            {"frame": "3", "team": "left", "court_x": "-2.0", "court_y": "1.234"},
            {"frame": "4", "team": "left", "court_x": "-2.1", "court_y": "1.2"},
            {"frame": "9", "team": "left", "court_x": "-4.0", "court_y": "0.0"},
            {"frame": "12", "team": "left", "court_x": "-1.0", "court_y": "0.0"},  # between the windows
            {"frame": "21", "team": "right", "court_x": "5.0", "court_y": "1.0"},
        ]

        assert player_spans(rows, 3, [(2, 10), (20, 22)]) == [
            {"from": 1, "samples": [[[-2.0, 1.23], [3.14, -1.0]], [[], []], [[-4.0, 0.0], []]]},
            {"from": 7, "samples": [[[], [5.0, 1.0]]]},
        ]


class TestWriteSite:
    def test_copies_the_page_next_to_data_js_and_the_video(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"not a video")
        site = tmp_path / "site"
        (site / "assets").mkdir(parents=True)
        (site / "assets" / "old.js").write_text("")

        write_site({"fps": 25.0, "rallies": []}, video, site, copy=True)

        assert (site / "index.html").read_text().count('src="data.js"') == 1
        assert not (site / "assets" / "old.js").exists()
        assert (site / "data.js").read_text() == 'window.MATCH = {"fps":25.0,"rallies":[]};\n'
        assert (site / "match.mp4").read_bytes() == b"not a video"
        assert not (site / "poster.webp").exists()
