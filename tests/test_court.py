import json

import cv2
import numpy as np
import pytest

from volleyball_stats.court import LANDMARKS, LINES, UNSNAPPED, Calibration, Clicks, calibrate, distort, draw_grid, fit, magnifier, match, refine, undistort


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


class TestCheck:
    def test_refuses_a_video_of_another_frame_size(self):
        calibration = Calibration(np.eye(3), size=[3840, 2160])

        calibration.check((3840, 2160))
        Calibration(np.eye(3)).check((1920, 1080))
        with pytest.raises(ValueError):
            calibration.check((1920, 1080))


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

    def test_keeps_how_a_library_court_was_made(self, tmp_path):
        calibration = Calibration(np.eye(3), clicks={"center_near": [1.0, 2.0]}, points={"corner_left_far": [3.0, 4.0]}, colour=[1.0, 0.0, 0.0], template=[[5.0, 6.0]], size=[1280, 720])

        calibration.save(tmp_path / "courts" / "gym.json")
        loaded = Calibration.load(tmp_path / "courts" / "gym.json")

        assert (loaded.clicks, loaded.points, loaded.colour, loaded.template, loaded.size) == (calibration.clicks, calibration.points, [1.0, 0.0, 0.0], [[5.0, 6.0]], [1280, 720])


class TestSnapping:
    """A synthetic sideline view: blue court lines on a yellow floor, and red-orange decoy lines 15 px
    beside both sidelines, which a colour-blind snap would take."""

    CORNERS = {"corner_left_far": (240, 250), "corner_right_far": (1040, 250), "corner_left_near": (80, 600), "corner_right_near": (1200, 600)}

    def court(self):
        names = list(self.CORNERS)
        h = cv2.getPerspectiveTransform(np.float32([LANDMARKS[n] for n in names]), np.float32([self.CORNERS[n] for n in names]))
        return h, {n: tuple(cv2.perspectiveTransform(np.array([[p]], float), h)[0, 0]) for n, p in LANDMARKS.items() if not n.startswith("post")}

    def image(self):
        h, truth = self.court()
        image = np.full((720, 1280, 3), (60, 200, 230), np.uint8)
        for offset in (-15, 15):
            for side in ("far", "near"):
                ends = np.array([truth[f"corner_left_{side}"], truth[f"corner_right_{side}"]]) + (0, offset)
                cv2.line(image, *[tuple(np.round(p * 16).astype(int)) for p in ends], (0, 80, 255), 3, cv2.LINE_AA, 4)
        for line in LINES:
            ends = [tuple(np.round(np.array(truth[n]) * 16).astype(int)) for n in (line[0], line[-1])]
            cv2.line(image, *ends, (255, 100, 0), 3, cv2.LINE_AA, 4)
        return image, truth

    def clicks(self, truth):
        rng = np.random.default_rng(0)
        angles = rng.uniform(0, 2 * np.pi, len(truth))
        return {n: (x + 15 * np.cos(a), y + 15 * np.sin(a)) for (n, (x, y)), a in zip(truth.items(), angles)}

    def test_snaps_clicks_15_px_off_to_the_lines_of_the_court_colour(self):
        image, truth = self.image()

        points, colour, on_lines = refine(image, self.clicks(truth))

        assert set(points) == set(truth) - UNSNAPPED
        assert max(np.hypot(*np.subtract(points[n], truth[n])) for n in points) < 0.5
        # Blue on yellow: more blue, less red than the floor.
        assert colour[0] > 0 > colour[2]
        assert len(on_lines) > 1000

    def test_finds_a_stored_court_after_the_camera_moved_and_refuses_another(self):
        image, truth = self.image()
        court = calibrate(image, self.clicks(truth))
        moved = cv2.getRotationMatrix2D((640, 360), 1.5, 1.0)
        moved[:, 2] += (40, -25)

        calibration, found, accepted = match(cv2.warpAffine(image, moved, (1280, 720), borderMode=cv2.BORDER_REPLICATE), court)

        assert accepted and found > 0.9
        assert max(np.hypot(*np.subtract(p, moved @ [*truth[n], 1.0])) for n, p in calibration.points.items()) < 1.0
        other = cv2.warpPerspective(image, cv2.getPerspectiveTransform(np.float32([[0, 0], [1280, 0], [0, 720], [1280, 720]]), np.float32([[300, 100], [980, 100], [0, 720], [1280, 720]])), (1280, 720))
        assert not match(other, court)[2]
        assert not match(np.full_like(image, 128), court)[2]


class TestClicks:
    def test_places_skips_and_undoes_in_landmark_order(self):
        clicks = Clicks(["a", "b", "c"])

        clicks.click(1.0, 2.0)
        clicks.skip()
        clicks.click(3.0, 4.0)

        assert clicks.points == {"a": (1.0, 2.0), "c": (3.0, 4.0)} and clicks.current is None
        clicks.undo()
        clicks.undo()
        assert clicks.points == {"a": (1.0, 2.0)} and clicks.current == "b"
        clicks.click(5.0, 6.0)
        assert clicks.points == {"a": (1.0, 2.0), "b": (5.0, 6.0)} and clicks.current == "c"


class TestMagnifier:
    def test_zooms_around_the_center_with_a_cross_through_it(self):
        image = np.zeros((80, 100, 3), dtype=np.uint8)
        image[30, 40] = 255

        inset = magnifier(image, (40.2, 29.8), radius=2, zoom=3)

        assert inset.shape == (15, 15, 3)
        # The center pixel fills rows and columns 6-8; the cross runs along row and column 7.
        assert inset[6, 6].tolist() == [255, 255, 255]
        assert inset[7, 0].tolist() == [0, 0, 255]
        assert inset[0, 0].tolist() == [0, 0, 0]

    def test_pads_past_the_image_edges(self):
        inset = magnifier(np.full((80, 100, 3), 255, dtype=np.uint8), (-5, 0), radius=2, zoom=3)

        assert inset.shape == (15, 15, 3)
        assert inset[0, 0].tolist() == [0, 0, 0]
        assert inset[14, 14].tolist() == [255, 255, 255]


class TestDrawGrid:
    def test_enlarges_and_draws_lines_every_step(self):
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        out = draw_grid(frame, origin=(300, 400), scale=2, step=50)

        assert out.shape == (200, 400, 3)
        # A grid line at source x = 50 lands on output column 100.
        assert out[150, 100].tolist() == [0, 255, 255]
        assert out[150, 101].tolist() == [0, 0, 0]
