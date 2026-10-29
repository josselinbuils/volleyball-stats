import numpy as np

from volleyball_stats.actions import classify, classify_rally, mark_dead, player_under, relance_cues
from volleyball_stats.court import Calibration

FPS = 30.0
NET_X = 612
LEFT, RIGHT, NET = (300, 300), (900, 300), (615, 250)


def kinds(typed: list) -> list[str]:
    return [t[3] for t in typed]


class TestClassifyRally:
    def test_numbers_each_side_s_touches_after_a_crossing(self):
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *LEFT), (120, *LEFT), (160, *RIGHT), (200, *RIGHT), (240, *RIGHT)]

        typed = classify_rally(contacts, [20, 140], FPS, NET_X)

        assert kinds(typed) == ["serve", "pass", "set", "attack", "dig", "set", "attack"]
        assert [t[4] for t in typed] == ["right", "left", "left", "left", "right", "right", "right"]

    def test_a_crossing_before_the_first_contact_makes_it_the_pass_of_an_unseen_serve(self):
        assert kinds(classify_rally([(30, *LEFT), (70, *LEFT)], [10], FPS, NET_X)) == ["pass", "set"]

    def test_a_touch_right_after_an_attack_is_the_opposing_block_and_does_not_count(self):
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *LEFT), (120, *LEFT), (125, *NET), (160, *RIGHT), (200, *RIGHT), (240, *RIGHT)]

        typed = classify_rally(contacts, [20, 122], FPS, NET_X)

        assert kinds(typed) == ["serve", "pass", "set", "attack", "block", "dig", "set", "attack"]
        assert typed[4][4] == "right"

    def test_the_touch_after_a_block_is_a_dig_even_before_the_serve_s_side_crossed_again(self):
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *LEFT), (120, *LEFT), (125, *NET), (160, *LEFT)]

        assert kinds(classify_rally(contacts, [20], FPS, NET_X)) == ["serve", "pass", "set", "attack", "block", "dig"]

    def test_the_serving_side_touching_the_ball_before_it_crosses_is_the_net(self):
        assert kinds(classify_rally([(0, *RIGHT), (40, *NET)], [], FPS, NET_X)) == ["serve", "net"]

    def test_the_side_follows_the_calibrated_net_line_over_net_x(self):
        calibration = Calibration(np.array([[30.0, 0.0, 640.0], [0.0, 20.0, 360.0], [0.0, 0.0, 1.0]]))

        assert classify_rally([(0, 630, 300)], [], FPS, NET_X)[0][4] == "right"
        assert classify_rally([(0, 630, 300)], [], FPS, NET_X, calibration)[0][4] == "left"


class TestFloor:
    # A sideline camera: court meters to pixels, horizon at v = 200, the camera at court y = 10.
    CALIBRATION = Calibration(np.array([[30.0, -64.0, 640.0], [0.0, -20.0, 360.0], [0.0, -0.1, 1.0]]))

    def at(self, frame: int, x: float, y: float) -> tuple[int, int, int]:
        """A contact whose floor projection is court (x, y)."""
        u, v = self.CALIBRATION.to_image(np.array([[x, y]]))[0]
        return frame, round(u), round(v)

    def test_a_contact_projecting_near_the_camera_is_the_floor_and_so_is_every_later_one(self):
        contacts = [self.at(0, 12, 0), self.at(40, -6, -6), self.at(80, -5, 3), self.at(100, -4, -6)]

        assert kinds(classify_rally(contacts, [20], FPS, NET_X, self.CALIBRATION)) == ["serve", "pass", "floor", "floor"]

    def test_the_last_contact_is_the_floor_when_it_projects_on_the_court(self):
        contacts = [self.at(0, 12, 0), self.at(40, -6, -6), self.at(80, -5, -3)]

        assert kinds(classify_rally(contacts, [20], FPS, NET_X, self.CALIBRATION)) == ["serve", "pass", "floor"]
        assert kinds(classify_rally([*contacts, self.at(120, -4, -6)], [20], FPS, NET_X, self.CALIBRATION)) == ["serve", "pass", "set", "attack"]

    def test_a_ball_above_the_horizon_is_never_the_floor(self):
        contacts = [self.at(0, 12, 0), (40, 640, 100)]

        assert kinds(classify_rally(contacts, [20], FPS, NET_X, self.CALIBRATION)) == ["serve", "pass"]

    def test_a_first_contact_inside_the_court_is_no_serve_but_a_dig_of_a_thrown_ball(self):
        contacts = [self.at(0, 3, -2), self.at(40, -6, -6), self.at(80, -5, -6)]

        assert kinds(classify_rally(contacts, [20], FPS, NET_X, self.CALIBRATION)) == ["dig", "dig", "set"]

    def test_a_first_contact_in_the_air_over_the_court_is_no_serve_though_it_projects_past_the_far_sideline(self):
        assert kinds(classify_rally([self.at(0, 2, -14), self.at(40, 9, 0)], [], FPS, NET_X, self.CALIBRATION))[0] == "dig"
        assert kinds(classify_rally([(0, 640, 100), self.at(40, -6, -6)], [20], FPS, NET_X, self.CALIBRATION))[0] == "serve"


class TestClassify:
    def test_keeps_the_contacts_of_each_rally_and_a_serve_just_before_its_window(self):
        contacts = [(50, *RIGHT), (100, *LEFT), (300, *LEFT)]

        typed = classify(contacts, [70, 400], [(55, 200)], FPS, NET_X)

        assert [(t[0], t[3]) for t in typed] == [(50, "serve"), (100, "pass")]


class TestMarkDead:
    def test_three_touches_in_a_row_by_one_player_make_the_ball_dead_for_the_rest_of_its_rally(self):
        typed = [(f, 0, 0, kind, "left") for f, kind in enumerate(["pass", "set", "attack", "attack", "attack", "attack", "serve"])]

        marked, touchers = mark_dead(typed, [1, 2, 3, 3, 3, 4, 5], [0, 0, 0, 0, 0, 0, 1])

        assert kinds(marked) == ["pass", "set", "floor", "floor", "floor", "floor", "serve"]
        assert touchers == [1, 2, None, None, None, None, 5]

    def test_two_touches_in_a_row_by_one_player_stay(self):
        typed = [(f, 0, 0, kind, "left") for f, kind in enumerate(["dig", "set", "attack"])]

        assert mark_dead(typed, [1, 1, 2], [0, 0, 0]) == (typed, [1, 1, 2])


class TestRelanceCues:
    def test_measures_the_ball_above_the_head_and_the_jump_in_player_heights(self):
        box = np.array([100.0, 200.0, 140.0, 300.0])

        above, lift = relance_cues((120.0, 180.0), box, [300.0, 330.0, 325.0])

        assert (round(above, 2), round(lift, 2)) == (0.2, 0.3)

    def test_a_ball_at_chest_height_with_the_feet_down_reads_below_the_head_and_no_jump(self):
        above, lift = relance_cues((120.0, 230.0), np.array([100.0, 200.0, 140.0, 300.0]), [300.0, 300.0])

        assert above < 0 and lift == 0


class TestPlayerUnder:
    def test_picks_the_box_under_the_ball_with_the_nearest_top(self):
        boxes = np.array([[0.0, 100, 40, 200], [90, 150, 130, 250], [95, 300, 135, 400], [400, 140, 440, 240]])

        assert player_under((110.0, 140.0), boxes, reach=15) == 1
        assert player_under((250.0, 140.0), boxes, reach=15) is None
        assert player_under((110.0, 140.0), np.empty((0, 4)), reach=15) is None
