import json

import cv2
import numpy as np
import pytest

from volleyball_stats import court, lens, placement
from volleyball_stats.court import Calibration

SIZE = (3840, 2160)


def calibration(x: float = 0.0, back: float = 7.3, height: float = 3.9, focal: float = 1500.0, pan: float = 0.0, tilt: float = 0.0) -> Calibration:
    """The court as a camera `x` m along the sideline from the net, `back` m from it, `height` m high sees it, aimed at the
    court's middle, then turned `pan` degrees to the right and `tilt` up: the owner's matches' by default."""
    eye = np.array([x, court.WIDTH / 2 + back, -height])
    forward = np.array([0.0, 0.0, 0.0]) - eye
    forward /= np.linalg.norm(forward)
    right = np.cross([0.0, 0.0, 1.0], forward)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    R = np.array([right, down, forward])
    a, b = np.radians(pan), np.radians(tilt)
    turn = np.array([[np.cos(a), 0, -np.sin(a)], [0, 1, 0], [np.sin(a), 0, np.cos(a)]]) @ np.array([[1, 0, 0], [0, np.cos(b), np.sin(b)], [0, -np.sin(b), np.cos(b)]])
    K = np.array([[focal, 0, SIZE[0] / 2], [0, focal, SIZE[1] / 2], [0, 0, 1]])
    P = K @ turn @ np.c_[R, -R @ eye]
    H = P[:, [0, 1, 3]]
    return Calibration(H / H[2, 2], lens={"model": "standard", "K": K.tolist(), "D": [0.0] * 4}, size=list(SIZE))


class TestJudge:
    def test_the_owners_framing_is_fine(self):
        found = placement.judge(calibration(), SIZE)

        assert found["ok"] and found["out"] == [] and found["camera"] == [0.0, 7.3, 3.9]

    def test_a_camera_too_close_moves_back(self):
        found = placement.judge(calibration(focal=1900), SIZE)

        assert found["out"] == ["left", "right"] and found["advice"] == ["back"]

    @pytest.mark.parametrize("pan, side", [(-6, "right"), (6, "left")])
    def test_a_camera_turned_away_from_an_end_turns_back(self, pan, side):
        # Turned right (positive), the left end leaves the picture.
        found = placement.judge(calibration(pan=pan), SIZE)

        assert found["out"] == [side] and found["advice"] == [f"turn_{side}"]

    def test_a_camera_tilted_up_or_down_tilts_back(self):
        high, low = placement.judge(calibration(focal=1200, tilt=35), SIZE), placement.judge(calibration(tilt=-25), SIZE)

        assert high["out"] == ["near"] and high["advice"] == ["tilt_down"]
        assert low["out"] == ["heads"] and low["advice"] == ["tilt_up"]

    def test_a_camera_off_the_nets_line_moves_to_it(self):
        assert placement.judge(calibration(x=3), SIZE)["advice"] == ["align_left"]
        assert placement.judge(calibration(x=-3), SIZE)["advice"] == ["align_right"]

    def test_a_low_camera_goes_higher(self):
        assert placement.judge(calibration(height=1.8), SIZE)["advice"] == ["higher"]

    def test_without_the_cameras_lens_no_place_is_guessed(self):
        found = placement.judge(Calibration(calibration().homography, size=list(SIZE)), SIZE)

        assert found["ok"] and found["camera"] is None
        # Its heads neither: a guessed camera puts them out of a picture they are in.
        assert "heads" not in placement.judge(Calibration(calibration(tilt=-25).homography, size=list(SIZE)), SIZE)["out"]


class TestPicture:
    def test_a_line_out_of_the_picture_goes_on_beside_it(self):
        image = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
        inside, wide = court.check_image(image, calibration()), court.check_image(image, calibration(focal=1900))

        assert inside.shape == (720, 1280, 3)
        assert wide.shape[0] == 720 and wide.shape[1] > 1280
        red = (wide[..., 2] > 200) & (wide[..., 1] < 100)
        assert red[:, :40].any() and red[:, -40:].any()


class TestTest:
    def test_finds_a_stored_court_else_asks_for_the_clicks_then_stores_it(self, tmp_path, monkeypatch):
        image = np.full((SIZE[1], SIZE[0], 3), 90, np.uint8)
        monkeypatch.setattr(court, "background", lambda video, tell: image)
        monkeypatch.setattr(lens, "camera", lambda video: {"model": "X", "size": list(SIZE), "fps": 50.0})
        found = calibration()
        monkeypatch.setattr(court, "find", lambda image, courts: None)
        assert placement.test(tmp_path / "clip.mp4", tmp_path) == {"found": False}
        assert (tmp_path / placement.FOLDER / placement.BACKGROUND).exists() and not (tmp_path / placement.FOLDER / placement.VERDICT).exists()

        monkeypatch.setattr(court, "calibrate", lambda image, clicks, lens: found)
        verdict = placement.fit({"corner_left_far": [1, 2]}, "gym", tmp_path)
        assert verdict["found"] and verdict["ok"] and (tmp_path / "courts" / "gym.json").exists()
        assert json.loads((tmp_path / placement.FOLDER / placement.VERDICT).read_text()) == verdict
        assert cv2.imread(str(tmp_path / placement.FOLDER / placement.PICTURE)) is not None

        monkeypatch.setattr(court, "find", lambda image, courts: found)
        assert placement.test(tmp_path / "clip.mp4", tmp_path)["ok"]
