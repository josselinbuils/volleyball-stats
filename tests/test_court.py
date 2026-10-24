import json

import cv2
import numpy as np
import pytest

from volleyball_stats.court import LANDMARKS, Calibration, distort, draw_grid, fit, undistort


class TestFit:
    # A plausible sideline camera: court meters to pixels.
    H = np.array([[60.0, -20.0, 640.0], [5.0, 30.0, 400.0], [0.0, 0.03, 1.0]])

    def project(self, names):
        court = np.array([LANDMARKS[n] for n in names])
        pixels = cv2.perspectiveTransform(court.reshape(-1, 1, 2), self.H).reshape(-1, 2)
        return {n: tuple(p) for n, p in zip(names, pixels)}

    def test_recovers_the_homography_and_maps_both_ways(self):
        calibration = fit(self.project(list(LANDMARKS)))

        assert calibration.error < 1e-3
        court = np.array([[3.0, -4.5], [-9.0, 4.5]])
        assert np.allclose(calibration.to_court(calibration.to_image(court)), court)
        assert np.allclose(calibration.to_image(court), cv2.perspectiveTransform(court.reshape(-1, 1, 2), self.H).reshape(-1, 2))

    def test_reports_the_reprojection_error_of_a_shifted_landmark(self):
        points = self.project(["corner_left_far", "corner_right_far", "corner_left_near", "corner_right_near", "center_near"])
        x, y = points["center_near"]
        points["center_near"] = (x + 6.0, y)

        calibration = fit(points)

        # The shift is within the RANSAC threshold, so it spreads over the fit.
        assert 1.0 < calibration.error < 6.0

    def test_rejects_unknown_names_and_too_few_points(self):
        with pytest.raises(ValueError, match="Unknown"):
            fit({"corner_left_far": (0, 0), "corner_right_far": (1, 0), "corner_left_near": (0, 1), "nope": (1, 1)})
        with pytest.raises(ValueError, match="At least 4"):
            fit(self.project(["corner_left_far", "corner_right_far", "corner_left_near"]))


class TestLens:
    K = [[800.0, 0.0, 640.0], [0.0, 800.0, 360.0], [0.0, 0.0, 1.0]]

    @pytest.mark.parametrize("lens", [{"model": "fisheye", "K": K, "D": [-0.05, 0.01, 0.0, 0.0]}, {"model": "standard", "K": K, "D": [-0.3, 0.1, 0.0, 0.0]}])
    def test_undistort_inverts_distort(self, lens):
        pixels = np.array([[100.0, 80.0], [640.0, 360.0], [1200.0, 700.0]])

        assert np.allclose(undistort(distort(pixels, lens), lens), pixels, atol=0.1)
        assert not np.allclose(distort(pixels, lens)[0], pixels[0], atol=1.0)

    def test_calibration_with_a_lens_round_trips_and_saves(self, tmp_path):
        lens = {"model": "fisheye", "K": self.K, "D": [-0.05, 0.01, 0.0, 0.0]}
        calibration = Calibration(np.array([[60.0, -20.0, 640.0], [5.0, 30.0, 400.0], [0.0, 0.03, 1.0]]), lens, 0.5)
        court = np.array([[3.0, -4.5], [-9.0, 4.5]])

        calibration.save(tmp_path / "calibration.json")
        loaded = Calibration.load(tmp_path / "calibration.json")

        assert np.allclose(loaded.to_court(loaded.to_image(court)), court, atol=1e-6)
        assert loaded.lens == lens and loaded.error == 0.5
        assert json.loads((tmp_path / "calibration.json").read_text())["lens"]["model"] == "fisheye"


class TestDrawGrid:
    def test_enlarges_and_draws_lines_every_step(self):
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        out = draw_grid(frame, origin=(300, 400), scale=2, step=50)

        assert out.shape == (200, 400, 3)
        # A grid line at source x = 50 lands on output column 100.
        assert out[150, 100].tolist() == [0, 255, 255]
        assert out[150, 101].tolist() == [0, 0, 0]
