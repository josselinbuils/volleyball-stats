import numpy as np

from volleyball_stats.ball3d import G, camera_place, fit_rally, project, projection, touch_places
from volleyball_stats.court import Calibration


def camera(height: float = 3.9, back: float = 12.0, focal: float = 1500.0) -> np.ndarray:
    """A homography of a camera at the net's side, looking at the court: court x to the right of the picture."""
    eye = np.array([0.0, back, -height])
    forward = np.array([0.0, -back, height + 1.0])
    forward /= np.linalg.norm(forward)
    right = np.array([1.0, 0.0, 0.0])
    down = np.cross(forward, right)
    R = np.array([right, down, forward])
    K = np.array([[focal, 0, 1920], [0, focal, 1080], [0, 0, 1]], float)
    return K @ np.c_[R, -R @ eye]


def path(touches: list[tuple[float, float, float]], frames: list[int], fps: float) -> dict[int, np.ndarray]:
    places = {}
    for k in range(len(frames) - 1):
        a, b = np.array(touches[k]), np.array(touches[k + 1])
        for f in range(frames[k] + 1, frames[k + 1]):
            u = (f - frames[k]) / (frames[k + 1] - frames[k])
            T = (frames[k + 1] - frames[k]) / fps
            places[f] = (1 - u) * a + u * b + [0, 0, G * T * T * u * (1 - u) / 2]
    return places


class TestProjection:
    def test_finds_the_camera_of_a_homography_and_its_lens(self):
        P = camera()
        H = P[:, [0, 1, 3]]
        found = projection(Calibration(H / H[2, 2], lens={"K": [[1500, 0, 1920], [0, 1500, 1080], [0, 0, 1]], "D": [0, 0, 0, 0], "model": "fisheye"}))
        assert np.allclose(camera_place(found), [0, 12, 3.9], atol=1e-6)

    def test_without_a_lens_takes_the_focal_length_that_squares_the_court(self):
        P = camera()
        H = P[:, [0, 1, 3]]
        # A camera turned a little: a level one leaves the focal length undetermined.
        turn = np.array([[np.cos(0.2), 0, np.sin(0.2)], [0, 1, 0], [-np.sin(0.2), 0, np.cos(0.2)]])
        K = np.array([[1500, 0, 1920], [0, 1500, 1080], [0, 0, 1]], float)
        H = K @ turn @ np.linalg.inv(K) @ H
        found = projection(Calibration(H / H[2, 2], size=[3840, 2160]))
        assert np.allclose(found[:, :3] / found[2, 2], (K @ turn @ np.linalg.inv(K) @ P)[:, :3] / (K @ turn @ np.linalg.inv(K) @ P)[2, 2], atol=1e-3)

    def test_none_without_lens_or_size(self):
        assert projection(Calibration(np.eye(3))) is None


class TestFitRally:
    fps = 50.0
    truth = [(-8.0, 2.0, 2.5), (5.0, -1.0, 1.0), (3.0, 0.5, 2.1), (1.5, -2.0, 3.0), (-4.0, 1.0, 0.11)]
    frames = [0, 75, 130, 170, 195]
    kinds = ["serve", "pass", "set", "attack", "floor"]

    def touches(self, off: float = 0.0) -> list[dict]:
        return [{"f": f, "type": k, "x": x + off, "y": y - off} for f, k, (x, y, _) in zip(self.frames, self.kinds, self.truth)]

    def sightings(self, P: np.ndarray, noise: float = 0.0, seed: int = 0) -> dict[int, np.ndarray]:
        places = path(self.truth, self.frames, self.fps)
        rng = np.random.default_rng(seed)
        return {f: project(P, np.array([p]))[0] + rng.normal(0, noise, 2) for f, p in places.items()}

    def test_finds_the_heights_from_the_flights(self):
        P = camera()
        places, errors = fit_rally(self.touches(), self.sightings(P, 2.0), P, self.fps)
        assert np.abs(places[:, 2] - [t[2] for t in self.truth]).max() < 0.35
        assert np.median(errors) < 4

    def test_moves_wrong_feet_towards_the_ball(self):
        P = camera()
        places, _ = fit_rally(self.touches(off=0.5), self.sightings(P, 1.0), P, self.fps)
        assert np.abs(places[1:4, 0] - [t[0] for t in self.truth[1:4]]).max() < 0.35

    def test_finds_a_hidden_touch_from_the_flights_alone(self):
        P = camera()
        places, _ = fit_rally(self.touches(), self.sightings(P, 2.0), P, self.fps, hidden={2})
        assert np.hypot(places[2, 0] - self.truth[2][0], places[2, 1] - self.truth[2][1]) < 1.0

    def test_shrugs_off_false_balls(self):
        P = camera()
        seen = self.sightings(P, 2.0)
        for f in range(10, 30):
            seen[f] = np.array([300.0, 300.0])
        places, _ = fit_rally(self.touches(), seen, P, self.fps)
        assert np.abs(places[:, 2] - [t[2] for t in self.truth]).max() < 0.6

    def test_keeps_the_typical_heights_without_a_sighting(self):
        places, errors = fit_rally(self.touches(), {}, camera(), self.fps)
        assert places[0, 2] == 2.7 and places[4, 2] == 0.11
        assert len(errors) == 0

    def test_ignores_a_flight_too_long_to_be_one(self):
        P = camera()
        touches = self.touches()
        touches[1] = {**touches[1], "f": 200, "type": "pass"}
        touches = [touches[0], touches[1]]
        _, errors = fit_rally(touches, self.sightings(P), P, self.fps)
        assert len(errors) == 0


class TestTouchPlaces:
    def calibration(self) -> Calibration:
        H = camera()[:, [0, 1, 3]]
        return Calibration(H / H[2, 2], lens=None, size=[3840, 2160])

    def test_none_without_the_ball_track(self, tmp_path):
        c = Calibration(np.eye(3), lens={"K": np.eye(3).tolist(), "D": [0, 0, 0, 0], "model": "fisheye"})
        assert touch_places([], tmp_path / "ball.csv", c, 50.0) == []

    def test_leaves_out_faults_and_lone_touches(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        lens = {"K": [[1500, 0, 1920], [0, 1500, 1080], [0, 0, 1]], "D": [0, 0, 0, 0], "model": "fisheye"}
        H = camera()[:, [0, 1, 3]]
        c = Calibration(H / H[2, 2], lens=lens)
        contacts = [
            {"f": 10, "type": "serve", "x": -9.0, "y": 0.0, "rally": 0},
            {"f": 12, "type": "fault", "x": None, "y": None, "rally": 0},
            {"f": 60, "type": "floor", "x": 5.0, "y": 1.0, "rally": 0},
            {"f": 500, "type": "serve", "x": 9.0, "y": 0.0, "rally": 1},
        ]
        flat = touch_places(contacts, ball, c, 50.0)
        assert flat[0::4] == [0, 2]
        assert flat[3] == 2.7 and flat[7] == 0.11
