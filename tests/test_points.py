import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.points import by_rally, combine, landing, next_servers, points, running_score, server_side, set_drift, side_lost

# Court meters to pixels: 40 px per meter along the length, the net at x = 612.
CAL = Calibration(np.array([[40.0, 0.0, 612.0], [0.0, 20.0, 400.0], [0.0, 0.0, 1.0]]))


def at(frame: int, x: float, y: float, kind: str) -> tuple:
    return (frame, round(612 + 40 * x), round(400 + 20 * y), kind, "left" if x < 0 else "right")


class TestSideLost:
    def test_a_landing_in_the_court_loses_for_its_side_the_line_included(self):
        rally = [at(0, 10, 0, "serve"), at(30, -6, 0, "pass"), at(60, -2, 0, "set"), at(90, -1.5, 0, "attack"), at(120, 9.2, 4.5, "floor")]

        assert side_lost(rally, [100], CAL) == ("right", "in")

    def test_a_landing_out_loses_for_the_side_of_the_last_touch(self):
        assert side_lost([at(0, 10, 0, "serve"), at(40, -10.5, 0, "floor")], [20], CAL) == ("right", "serve_out")

    def test_without_a_landing_a_ball_sent_over_and_not_played_again_loses_for_the_other_side(self):
        assert side_lost([at(0, 10, 0, "serve"), at(30, -6, 0, "pass"), at(60, -3, 0, "attack")], [20, 70], CAL) == ("right", "over")

    def test_without_a_landing_a_ball_that_does_not_cross_loses_for_the_side_of_the_last_touch(self):
        assert side_lost([at(0, 10, 0, "serve"), at(30, -6, 0, "pass")], [20], CAL) == ("left", "net")
        assert side_lost([at(0, 10, 0, "serve"), at(30, 0.4, 0, "net")], [], CAL) == ("right", "serve_net")

    def test_a_trailing_touch_or_a_landing_at_the_net_loses_for_the_side_that_sent_the_ball_there(self):
        assert side_lost([at(0, -10, 0, "serve"), at(25, 0.6, -2, "pass")], [20], CAL) == ("left", "serve_net")
        assert side_lost([at(0, 10, 0, "serve"), at(30, -6, 3, "dig"), at(50, 0.3, 3, "floor")], [20], CAL) == ("left", "net")

    def test_knows_nothing_without_a_touch(self):
        assert side_lost([at(0, -3, 0, "floor")], [], CAL) == (None, "unknown")


def test_judges_a_landing_at_the_foot_of_the_net_in_the_line_included_or_out():
    assert [landing(0.8, 0.0), landing(-9.2, 4.7), landing(9.5, 0.0), landing(5.0, -4.9)] == ["net", "in", "out", "out"]


def test_credits_each_rally_to_the_team_on_the_side_that_did_not_lose_it():
    # 30 fps, each serve just before its window, the teams changing ends in between.
    typed = [at(95, 10, 0, "serve"), at(130, -5, 0, "floor"), at(1995, -10, 0, "serve"), at(2030, 5, 0, "floor")]

    found = points(typed, [], [(100, 200), (2000, 2100)], [1, 2], [1, 1], 30.0, CAL)

    assert [(p["server"], p["end"], p["winner"], p["reason"], p["score"]) for p in found] == [(2, 2, 2, "serve_in", (0, 1)), (2, 2, 2, "serve_in", (0, 2))]


def test_the_server_is_the_side_of_the_contact_typed_serve():
    assert server_side([at(5, -3, 0, "pass"), at(0, 10, 0, "serve")]) == "right"
    assert server_side([at(5, -3, 0, "pass")]) is None


class TestCombine:
    fps = 1.0
    windows = [(0, 10), (30, 40), (100, 110), (130, 140)]

    def test_the_next_server_decides_when_the_rules_differ_and_no_rally_fits_in_between(self):
        assert combine([1, 2, 2, 1], [2, 2, 1, None], self.windows, self.fps)[0] == (2, None)

    def test_after_a_long_gap_the_end_rule_keeps_the_rally_and_the_next_server_gets_a_missed_one(self):
        assert combine([1, 1, 2, 1], [2, 2, 1, None], self.windows, self.fps)[1] == (1, 2)

    def test_the_next_server_stands_in_for_an_unknown_end_and_a_set_s_last_rally_keeps_its_own(self):
        nexts = next_servers([1, 2, 2, 2], [1, 1, 2, 2])

        assert nexts == [2, None, 2, None]
        assert combine([None, 1, 2, 1], nexts, self.windows, self.fps) == [(2, None), (1, None), (2, None), (1, None)]


def test_scores_each_set_from_0_0_with_the_missed_rallies_and_without_unknown_winners():
    found = [(1, None), (2, 1), (None, None), (1, None), (2, None)]

    assert running_score(found, [1, 1, 1, 1, 2]) == [(1, 0), (1, 1), (2, 1), (3, 1), (0, 1)]


def test_compares_the_estimated_set_totals_with_the_given_scores():
    assert set_drift({1: (23, 24), 2: (10, 12), 3: (5, 5)}, ["25 – 21", None]) == {1: (-2, 3), 2: None, 3: None}


def test_groups_items_by_rally_window_started_early():
    assert by_rally([(8, "a"), (25, "b"), 41, (70, "c")], [(10, 30), (40, 50)], 3) == [[(8, "a"), (25, "b")], [41]]
