import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.web import contacts, player_samples, result, spot, zone, zone_cells

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


class TestPlayerSamples:
    def test_keeps_every_steps_frame_rounded_to_the_centimetre_left_team_first(self):
        rows = [
            {"frame": "0", "team": "right", "court_x": "3.14159", "court_y": "-1.005"},
            {"frame": "0", "team": "left", "court_x": "-2.0", "court_y": "1.234"},
            {"frame": "1", "team": "left", "court_x": "-2.1", "court_y": "1.2"},
            {"frame": "6", "team": "left", "court_x": "-4.0", "court_y": "0.0"},
        ]

        assert player_samples(rows, 3, 8) == [[[-2.0, 1.23], [3.14, -1.0]], [[], []], [[-4.0, 0.0], []]]
