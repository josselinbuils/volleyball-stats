import cv2
import numpy as np

from volleyball_stats import ballsize
from volleyball_stats.court import Calibration

from test_ball3d import camera


def picture(x: int, y: int, long: int = 40) -> np.ndarray:
    """A noisy grey crop with a ball 40 pixels wide at (x, y), blurred along x to `long`."""
    image = np.random.default_rng(x * 1000 + y).integers(90, 110, (144, 144, 3), dtype=np.uint8)
    cv2.ellipse(image, (x, y), (long // 2, 20), 0, 0, 360, (240, 240, 240), -1)
    return image


class TestBlob:
    def test_measures_the_ball_that_is_elsewhere_before_and_after(self):
        short, solid = ballsize.blob(picture(72, 72), picture(10, 30), picture(130, 110))
        assert abs(short - 40) <= 3 and solid > 0.9

    def test_motion_blur_keeps_the_short_side(self):
        short, _ = ballsize.blob(picture(72, 72, 70), picture(10, 30), picture(130, 110))
        assert abs(short - 40) <= 3

    def test_no_ball_at_the_centre_is_none(self):
        assert ballsize.blob(picture(20, 20), picture(10, 120), picture(130, 110)) is None

    def test_a_ball_that_did_not_move_is_none(self):
        assert ballsize.blob(picture(72, 72), picture(72, 72), picture(130, 110)) is None


class TestPlan:
    def test_measures_around_the_touch_against_frames_where_the_ball_is_away(self):
        ball = {f: (100 + 20 * f, 500) for f in range(100)}
        found = ballsize.plan(50, ball, 50.0, 1.0)
        assert [g for g, _, _ in found] == [44, 45, 46, 47, 48, 52, 53, 54, 55, 56]
        # 60 pixels away at 20 a frame: three frames on each side.
        assert all((a, b) == (g - 3, g + 3) for g, a, b in found)

    def test_a_ball_coming_back_on_its_path_is_not_measured(self):
        ball = {f: (100 + 20 * abs(f - 50), 500) for f in range(100)}
        assert all(abs(ball[a][0] - ball[b][0]) >= 60 for _, a, b in ballsize.plan(50, ball, 50.0, 1.0))

    def test_nothing_without_the_ball(self):
        assert ballsize.plan(50, {}, 50.0, 1.0) == []


class TestDepth:
    def depth(self) -> ballsize.Depth:
        P = camera()
        H = P[:, [0, 1, 3]]
        calibration = Calibration(H / H[2, 2], lens={"K": [[1500, 0, 1920], [0, 1500, 1080], [0, 0, 1]], "D": [0, 0, 0, 0], "model": "fisheye"})
        # Two players in line with the camera, 4 m apart; a third seen nowhere near the frame.
        return ballsize.Depth(calibration, {1: {10: (0.0, 3.0)}, 2: {10: (0.0, -1.0)}, 3: {90: (0.0, 0.0)}}, 8)

    def test_the_ball_as_wide_as_at_a_player_fits_that_player(self):
        depth = self.depth()
        near, far = depth.expected(1, 10, "set"), depth.expected(2, 10, "set")
        assert near > far * 1.2
        off = depth.misfits(far, 1920, 1080, 10, "set", [1, 2, 3])
        assert off[2] == 0.0 and abs(off[1] - np.log(near / far)) < 1e-4 and off[3] == 0.0

    def test_no_width_or_no_place_is_none(self):
        depth = self.depth()
        assert depth.misfits(None, 1920, 1080, 10, "set", [1, 2]) is None
        assert depth.misfits(30.0, 1920, 1080, 10, "set", [3]) is None
