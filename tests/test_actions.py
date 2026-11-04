import numpy as np

from volleyball_stats import actions
from volleyball_stats.actions import by_flight, classify, classify_rally, late_serves, mark_dead, no_play, player_under, relance_cues, serve_starts, served
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

    def test_a_dig_sending_the_ball_straight_over_is_an_attack_a_pass_stays_a_pass(self):
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *RIGHT), (120, *RIGHT), (160, *RIGHT), (200, *LEFT), (240, *RIGHT)]

        typed = classify_rally(contacts, [20, 60, 180, 220], FPS, NET_X)

        assert kinds(typed) == ["serve", "pass", "dig", "set", "attack", "attack", "dig"]

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

    def test_the_server_bouncing_the_ball_behind_the_end_line_leaves_it_alive(self):
        contacts = [self.at(0, 10, 3), self.at(20, 10.3, 3), self.at(50, 12, 0), self.at(90, -6, -6), self.at(130, -5, 3)]

        assert kinds(classify_rally(contacts, [70], FPS, NET_X, self.CALIBRATION)) == ["floor", "floor", "serve", "pass", "floor"]

    def test_a_serve_the_server_bounces_again_was_a_catch(self):
        contacts = [self.at(0, 10, 3), self.at(20, 12, 0), self.at(40, 10.3, 3)]

        assert kinds(classify_rally(contacts, [], FPS, NET_X, self.CALIBRATION)) == ["floor", "floor", "floor"]

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

    def test_a_touch_past_the_net_on_the_other_side_follows_a_crossing_the_track_missed(self):
        contacts = [self.at(0, 12, 0), self.at(40, -6, -6), self.at(80, -3, -6), self.at(120, -2, -6), self.at(160, 5, -6)]

        assert kinds(classify_rally(contacts, [130], FPS, NET_X, self.CALIBRATION)) == ["serve", "pass", "set", "attack", "dig"]
        assert kinds(classify_rally([self.at(0, 12, 0), self.at(40, -0.5, -6)], [], FPS, NET_X, self.CALIBRATION)) == ["serve", "net"]

    def test_a_window_opening_on_a_contact_inside_the_court_is_no_rally(self):
        windows = [(105, 300), (405, 600), (705, 900)]
        contacts = [self.at(100, 3, -2), self.at(400, 12, 0), self.at(740, 0, 0)]

        assert served(windows, contacts, FPS, self.CALIBRATION) == [(405, 600), (705, 900)]
        assert served(windows, contacts, FPS) == windows


class TestClassify:
    def test_keeps_the_contacts_of_each_rally_and_a_serve_just_before_its_window(self):
        contacts = [(50, *RIGHT), (100, *LEFT), (300, *LEFT)]

        typed = classify(contacts, [70, 400], [(55, 200)], FPS, NET_X)

        assert [(t[0], t[3]) for t in typed] == [(50, "serve"), (100, "pass")]

    def test_a_contact_in_two_overlapping_windows_stays_the_first_ones(self):
        contacts = [(50, *RIGHT), (100, *LEFT), (198, *LEFT)]

        typed = classify(contacts, [70], [(55, 200), (205, 300)], FPS, NET_X)

        assert [(t[0], t[3]) for t in typed] == [(50, "serve"), (100, "pass"), (198, "set")]


class TestMarkDead:
    def test_three_touches_in_a_row_by_one_player_make_the_ball_dead_for_the_rest_of_its_rally(self):
        typed = [(f, 0, 0, kind, "left") for f, kind in enumerate(["pass", "set", "attack", "attack", "attack", "attack", "serve"])]

        marked, touchers = mark_dead(typed, [1, 2, 3, 3, 3, 4, 5], [0, 0, 0, 0, 0, 0, 1])

        assert kinds(marked) == ["pass", "set", "floor", "floor", "floor", "floor", "serve"]
        assert touchers == [1, 2, None, None, None, None, 5]

    def test_two_touches_in_a_row_by_one_player_stay(self):
        typed = [(f, 0, 0, kind, "left") for f, kind in enumerate(["dig", "set", "attack"])]

        assert mark_dead(typed, [1, 1, 2], [0, 0, 0]) == (typed, [1, 1, 2])


class TestServeStarts:
    def test_a_window_opening_after_its_serve_starts_lead_s_after_it(self):
        # The serve at 0, the window found by the ball from 20 (LEAD_S is 10 frames at 30 fps).
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *LEFT)]

        assert serve_starts([(20, 100)], contacts, [20], FPS, NET_X) == [(10, 100)]
        assert serve_starts([(5, 100)], contacts, [20], FPS, NET_X) == [(5, 100)]

    def test_a_ball_bounced_by_the_server_moves_nothing(self):
        contacts = [(0, *RIGHT), (12, RIGHT[0] + 20, RIGHT[1]), (40, *LEFT)]

        assert serve_starts([(20, 100)], contacts, [25], FPS, NET_X) == [(20, 100)]

    def test_takes_no_contact_of_the_previous_rally(self):
        contacts = [(0, *RIGHT), (40, *LEFT), (80, *LEFT)]

        assert serve_starts([(-50, 0), (20, 100)], contacts, [20], FPS, NET_X) == [(-50, 0), (20, 100)]


class TestNoPlay:
    def test_a_window_of_floor_contacts_only_is_no_rally(self):
        typed = [(10, 0, 0, "floor", "left"), (20, 0, 0, "floor", "left"), (30, 0, 0, "serve", "left"), (40, 0, 0, "floor", "right"), (50, 0, 0, "floor", "right"), (60, 0, 0, "floor", "left")]

        assert no_play(typed, [0, 0, 1, 1, 1, 2]) == {0}


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


class TestMarkRelances:
    def test_the_cached_boxes_spare_the_video(self, tmp_path):
        import json

        from volleyball_stats.actions import mark_relances

        # A player standing under the ball, feet still: a relance.
        frames = {str(f): [[100.0, 100.0, 140.0, 300.0]] for f in range(70, 101)}
        cache = tmp_path / "relances.json"
        cache.write_text(json.dumps(frames))

        import cv2

        # The video only gives its height: the boxes come from the cache.
        video = tmp_path / "blank.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (64, 720))
        writer.write(np.zeros((720, 64, 3), dtype=np.uint8))
        writer.release()

        out = mark_relances(video, [(100, 120, 150, "attack", "left")], 30.0, cache)

        assert out[0][3] == "relance"


class TestNoPlayWindows:
    FPS = 50.0

    def test_a_window_with_no_serve_is_none(self):
        typed = [(10, 0, 0, "dig", "left"), (20, 0, 0, "set", "left")]

        assert no_play(typed, [0, 0], [(0, 100)], [50], self.FPS) == {0}

    def test_a_long_window_with_no_crossing_is_none(self):
        typed = [(10, 0, 0, "serve", "left"), (20, 0, 0, "net", "left")]

        assert no_play(typed, [0, 0], [(0, 200)], [], self.FPS) == {0}

    def test_a_short_serve_into_the_net_stays(self):
        typed = [(10, 0, 0, "serve", "left"), (20, 0, 0, "net", "left")]

        assert no_play(typed, [0, 0], [(0, 80)], [], self.FPS) == set()

    def test_a_long_rally_crossing_the_net_stays(self):
        typed = [(10, 0, 0, "serve", "left"), (60, 0, 0, "pass", "right")]

        assert no_play(typed, [0, 0], [(0, 200)], [40], self.FPS) == set()


class TestLateServes:
    FPS = 50.0

    @staticmethod
    def calibration():
        from unittest.mock import Mock

        found = Mock()
        found.to_image.return_value = np.array([[800.0, 0.0], [3000.0, 0.0]])
        # Every contact in the air: its floor projection falls behind the far sideline.
        found.to_court.return_value = np.array([[0.0, -20.0]])
        return found

    def moved(self, contacts, crossings, whistles, start=500):
        return late_serves([(start, 900)], contacts, crossings, whistles, self.FPS, 1900.0, self.calibration())[0][0]

    def test_a_window_opening_late_starts_at_the_serve_after_the_go(self):
        assert self.moved([(100, 900, 700), (250, 2800, 800)], [140], [(1.0, 1.2)]) == 100 + round(actions.LEAD_S * self.FPS)

    def test_no_serve_before_the_go(self):
        assert self.moved([(100, 900, 700)], [140], [(3.0, 3.2)]) == 500

    def test_without_a_go_only_just_before_the_window(self):
        assert self.moved([(100, 900, 700)], [140], []) == 500
        assert self.moved([(420, 900, 700)], [460], []) == 420 + round(actions.LEAD_S * self.FPS)

    def test_a_contact_short_of_the_end_line_is_no_serve(self):
        assert self.moved([(100, 1800, 700)], [140], [(1.0, 1.2)]) == 500


class TestByFlight:
    FPS = 50.0

    def typed(self, kind):
        return [(0, 0, 0, kind, "left"), (50, 0, 0, "dig", "right")]

    def test_a_high_ball_sent_down_is_an_attack(self):
        places = {0: np.array([1.0, 0.0, 2.8]), 50: np.array([-5.0, 0.0, 1.0])}

        assert by_flight(self.typed("relance"), places, self.FPS)[0][3] == "attack"

    def test_a_ball_sent_up_is_a_relance(self):
        places = {0: np.array([1.0, 0.0, 2.3]), 50: np.array([-5.0, 0.0, 4.0])}

        assert by_flight(self.typed("attack"), places, self.FPS)[0][3] == "relance"

    def test_a_low_ball_is_a_relance(self):
        places = {0: np.array([1.0, 0.0, 1.5]), 50: np.array([-5.0, 0.0, 0.5])}

        assert by_flight(self.typed("attack"), places, self.FPS)[0][3] == "relance"

    def test_no_flight_known_stays(self):
        assert by_flight(self.typed("attack"), {}, self.FPS)[0][3] == "attack"

    def test_two_contacts_on_one_frame_are_no_flight(self):
        typed = [(0, 0, 0, "attack", "left"), (0, 0, 0, "dig", "right")]

        assert by_flight(typed, {0: np.array([1.0, 0.0, 1.0])}, self.FPS)[0][3] == "attack"

    def test_other_touches_stay(self):
        places = {0: np.array([1.0, 0.0, 1.0]), 50: np.array([-5.0, 0.0, 1.0])}

        assert by_flight(self.typed("set"), places, self.FPS)[0][3] == "set"
