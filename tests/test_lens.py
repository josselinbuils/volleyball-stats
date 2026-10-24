import cv2
import numpy as np

from volleyball_stats.lens import CORNERS, board_points, coverage, find_corners, fit_lens, pattern


class TestPattern:
    def test_is_found_with_all_its_corners(self):
        corners = find_corners(cv2.resize(pattern(), None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA))

        assert corners is not None and len(corners) == CORNERS[0] * CORNERS[1]


class TestFitLens:
    def test_recovers_known_fisheye_intrinsics(self):
        size = (1920, 1080)
        k = np.array([[700.0, 0, 960], [0, 700, 540], [0, 0, 1]])
        d = np.array([0.08, -0.02, 0.01, -0.003])
        rng = np.random.default_rng(0)
        views = []
        while len(views) < 25:
            rotation = rng.uniform(-0.6, 0.6, 3)
            translation = np.array([*rng.uniform(-6, 6, 2), rng.uniform(8, 14)])
            points, _ = cv2.fisheye.projectPoints(board_points().reshape(-1, 1, 3) - [4, 2.5, 0], rotation, translation, k, d)
            points = points.reshape(-1, 2)
            if ((points >= 0) & (points < size)).all():
                views.append(points)

        lens = fit_lens(views, size)

        assert lens["rms"] < 0.01
        assert np.allclose(lens["K"], k, atol=1.0)
        assert np.allclose(lens["D"], d, atol=0.01)


class TestCoverage:
    def test_counts_the_grid_cells_holding_a_corner(self):
        views = [np.array([[10.0, 10.0], [15.0, 12.0]]), np.array([[1910.0, 1070.0]])]

        assert coverage(views, (1920, 1080)) == 2 / 48
