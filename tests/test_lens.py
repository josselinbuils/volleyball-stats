import json

import cv2
import numpy as np

from volleyball_stats.lens import CAMERA, CORNERS, LEGACY, OWN, board_points, camera_of, coverage, find_corners, fit_lens, for_camera, for_match, pattern


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


class TestCamera:
    def test_names_the_camera_its_tags_name(self):
        video = {"codec_type": "video", "width": 3840, "height": 2160, "avg_frame_rate": "50/1", "tags": {"handler_name": "VideoHandler"}}
        dji = {"format": {"tags": {"encoder": "DJI OsmoAction3"}}, "streams": [{"codec_type": "audio"}, video]}
        iphone = {"format": {"tags": {"com.apple.quicktime.make": "Apple", "com.apple.quicktime.model": "iPhone 15"}}, "streams": [{**video, "avg_frame_rate": "30000/1001"}]}
        copied = {"format": {"tags": {"encoder": "Lavf60.16.100"}}, "streams": [video]}

        assert camera_of(dji) == {"model": "DJI OsmoAction3", "size": [3840, 2160], "fps": 50.0}
        assert camera_of(iphone) == {"model": "Apple iPhone 15", "size": [3840, 2160], "fps": 29.97}
        assert camera_of(copied)["model"] is None


class TestProfiles:
    OSMO = {"model": "DJI OsmoAction3", "size": [3840, 2160], "fps": 50.0}

    def test_picks_the_cameras_profile_for_its_mode_only(self, tmp_path):
        assert for_camera(tmp_path, self.OSMO).name == "dji_osmoaction3_3840x2160_50.json"
        assert for_camera(tmp_path, {**self.OSMO, "fps": 100.0}) is None
        assert for_camera(tmp_path, {**self.OSMO, "size": [2704, 1520]}) is None
        assert for_camera(tmp_path, {**self.OSMO, "model": None}) is None

    def test_prefers_the_latest_calibrated_here(self, tmp_path):
        (tmp_path / OWN).mkdir()
        for name, made in (("old", "2026-11-01"), ("new", "2026-11-20")):
            (tmp_path / OWN / f"{name}.json").write_text(json.dumps({"camera": self.OSMO, "made": made}), encoding="utf-8")
        unnamed = {**self.OSMO, "model": None}
        (tmp_path / OWN / "unnamed.json").write_text(json.dumps({"camera": unnamed, "made": "2026-11-02"}), encoding="utf-8")

        assert for_camera(tmp_path, self.OSMO).name == "new.json"
        assert for_camera(tmp_path, unnamed).name == "unnamed.json"

    def test_a_match_imported_before_cameras_takes_the_one_lens(self, tmp_path):
        match = tmp_path / "matches" / "m"
        match.mkdir(parents=True)

        assert for_match(tmp_path, match) is None
        (tmp_path / LEGACY).write_text("{}", encoding="utf-8")
        assert for_match(tmp_path, match) == tmp_path / LEGACY
        (match / CAMERA).write_text(json.dumps({**self.OSMO, "model": "Apple iPhone 15"}), encoding="utf-8")
        assert for_match(tmp_path, match) is None
