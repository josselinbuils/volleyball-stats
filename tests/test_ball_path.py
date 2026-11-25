import math

import cv2
import numpy as np
import pytest

from volleyball_stats import ball_path


class TestBallPath:
    @staticmethod
    def flight(start, n, x0, y0, vx, vy, g=0.4):
        return {start + k: (x0 + vx * k, y0 + vy * k + g * k * k / 2) for k in range(n)}

    def test_crosses_a_hole_on_the_flight_s_curve(self):
        ball = self.flight(100, 60, 500, 500, 12, -8)
        truth = dict(ball)
        for q in range(120, 135):
            del ball[q]

        path = ball_path.rally_path(ball, [100], 90, 170)

        for q in range(120, 135):
            assert math.hypot(path[q][0] - truth[q][0], path[q][1] - truth[q][1]) < 6

    def test_leaves_out_what_never_moves_and_what_no_ball_could_reach(self):
        ball = self.flight(100, 60, 500, 500, 12, -8)
        also = {q: (3000.0, 200.0) for q in range(90, 170)}
        ball[130] = (3500.0, 1800.0)

        path = ball_path.rally_path(ball, [100], 90, 170, also)

        assert all(math.hypot(path[q][0] - 3000, path[q][1] - 200) > 500 for q in path)
        assert math.hypot(path[130][0] - (500 + 12 * 30), path[130][1] - (500 - 8 * 30 + 0.4 * 900 / 2)) < 12

    def test_goes_through_a_touch_whatever_the_frame_recorded_without_a_jump(self):
        ball = {**self.flight(100, 30, 500, 500, 10, 5), **self.flight(130, 30, 790, 788, -20, 3)}

        # The touch recorded 4 frames after the real one.
        path = ball_path.rally_path(ball, [134, 158], 90, 170)

        steps = [math.hypot(path[q][0] - path[q - 1][0], path[q][1] - path[q - 1][1]) for q in path if q - 1 in path]
        assert max(steps) < 40
        assert math.hypot(path[132][0] - ball[132][0], path[132][1] - ball[132][1]) < 16

    def test_ends_at_the_landing_after_the_last_touch(self):
        down = self.flight(100, 30, 500, 300, 10, 15, 0.2)
        up = self.flight(130, 30, 790, 830, 8, -14, 0.2)

        path = ball_path.rally_path({**down, **up}, [100], 90, 170)

        assert 129 in path and 145 not in path

    def test_ends_where_the_ball_is_lost_after_the_last_touch(self):
        ball = {**self.flight(100, 20, 500, 300, 10, 5), **self.flight(150, 20, 700, 1100, -10, -5)}
        assert max(ball_path.rally_path(ball, [100], 90, 175)) == 119


class TestBallSize:
    def test_reads_the_narrow_side_of_what_moved(self):
        empty = np.full((400, 400, 3), 120, np.uint8)
        picture = empty.copy()
        cv2.ellipse(picture, (200, 200), (30, 12), 0, 0, 360, (20, 20, 20), -1)
        assert ball_path.ball_size(empty, picture, empty, 200, 200) == pytest.approx(25, abs=3)
        assert ball_path.ball_size(empty, empty, empty, 200, 200) is None

    def test_a_flight_too_small_for_our_court_is_another_court_s(self):
        part = [(q, 100.0, 100.0) for q in range(10)]
        small = {ball_path.size_key(*p): 8.0 for p in part}
        assert ball_path.too_small(part, small, lambda *_: 20.0)
        assert not ball_path.too_small(part, {k: 19.0 for k in small}, lambda *_: 20.0)
        # Too few read to say.
        assert not ball_path.too_small(part, dict(list(small.items())[:3]), lambda *_: 20.0)

    def test_leaves_out_what_was_rejected(self):
        ball = TestBallPath.flight(100, 60, 500, 500, 12, -8)
        wrong = {q: (2500.0 + q, 300.0) for q in range(100, 160)}
        path = ball_path.rally_path(wrong, [100], 90, 170, ball, wrong)
        assert all(p[0] < 2000 for p in path.values()) and 130 in path


class TestRanges:
    def test_joins_the_frames_close_enough_to_read_through(self):
        assert ball_path.ranges([1, 2, 3, 8, 30, 31]) == [(1, 8), (30, 31)]
