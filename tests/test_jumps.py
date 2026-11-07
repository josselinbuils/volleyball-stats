import numpy as np

from volleyball_stats.ball3d import G, project
from volleyball_stats.court import Calibration, distort
from volleyball_stats import jumps
from volleyball_stats.jumps import attack_rows, flight, hit, lift, lower_hull, measure, run_up, window


class TestJumps:
    FPS = 50.0
    TAKEOFF, LANDING, CONTACT = 71, 99, 85

    @staticmethod
    def camera(height: float = 3.9, back: float = 12.0, focal: float = 1500.0) -> np.ndarray:
        """A camera at the net's side looking at the court: court x to the right of the picture."""
        eye = np.array([0.0, back, -height])
        forward = np.array([0.0, -back, height + 1.0])
        forward /= np.linalg.norm(forward)
        right = np.array([1.0, 0.0, 0.0])
        R = np.array([right, np.cross(forward, right), forward])
        K = np.array([[focal, 0, 1920], [0, focal, 1080], [0, 0, 1]], float)
        return K @ np.c_[R, -R @ eye]

    def attack(self) -> tuple[np.ndarray, list, Calibration]:
        """A player standing 4.5 m from the net, running to 2 m by frame 70, flying 0.56 s while carried 0.3 m on."""
        P = self.camera()
        H = P[:, [0, 1, 3]]
        calibration = Calibration(H / H[2, 2], lens={"K": [[1500, 0, 1920], [0, 1500, 1080], [0, 0, 1]], "D": [0, 0, 0, 0], "model": "fisheye"})
        rows, keypoints = [], {}
        for f in range(0, 140):
            if f < 40:
                x, h = -4.5, 0.0
            elif f < self.TAKEOFF:
                x, h = -4.5 + 2.5 * (f - 39) / 31, 0.0
            elif f < self.LANDING:
                u, T = (f - self.TAKEOFF + 0.5) / (self.LANDING - self.TAKEOFF), (self.LANDING - self.TAKEOFF) / self.FPS
                x, h = -2.0 + 0.3 * u, G * T * T * u * (1 - u) / 2
            else:
                x, h = -1.7, 0.0
            feet, head, ankle = distort(project(P, np.array([[x, 1.0, h], [x, 1.0, h + 1.8], [x, 1.0, h + 0.08]])), calibration.lens)
            court = calibration.to_court(feet[None])[0]
            rows.append([f, feet[0] - 60, head[1], feet[0] + 60, feet[1], *court])
            points = np.zeros((17, 3))
            points[[15, 16]] = [*ankle, 0.9]
            keypoints[f] = points.tolist()
        return np.array(rows), [keypoints[f] for f in window(self.CONTACT, self.FPS)], calibration

    def test_lower_hull_bridges_a_bump(self):
        t = np.arange(5.0)
        assert lower_hull(t, np.array([0.0, 2.0, 3.0, 2.0, 0.0])).tolist() == [0.0] * 5
        assert lower_hull(t, t).tolist() == t.tolist()

    def test_measures_the_jump_and_run_up(self, monkeypatch):
        monkeypatch.setattr(jumps, "HEEL_UP_S", 0.0)
        monkeypatch.setattr(jumps, "HEEL_DOWN_S", 0.0)
        rows, keypoints, calibration = self.attack()
        got = measure(self.CONTACT, rows, keypoints, calibration, self.FPS)
        assert got is not None
        assert abs(got["takeoff"] - self.TAKEOFF) <= 1 and abs(got["landing"] - self.LANDING) <= 1
        assert abs(got["late"] - 10) <= 20
        assert abs(got["height"] - G * 0.56**2 / 8) < 0.06
        assert abs(got["takeoff_m"] - 2.0) < 0.1 and abs(got["drift_m"] - 0.3) < 0.1
        assert abs(got["start_m"] - 4.5) <= 0.1 and 39 <= got["start"] <= 42

    def test_no_jump_without_a_flight(self):
        rows, keypoints, calibration = self.attack()
        flat = [k if k is None else [p if i not in (15, 16) else [p[0], keypoints[0][15][1], p[2]] for i, p in enumerate(k)] for k in keypoints]
        assert measure(self.CONTACT, rows, flat, calibration, self.FPS) is None

    def test_run_up_stops_where_the_player_had_come_nearer(self):
        rows = np.array([[f, 0, 0, 1, 1, -(2.0 if f < 20 else 4.0 if f < 60 else 4.0 - 2.0 * (f - 60) / 40), 0] for f in range(100)], float)
        assert 60 <= run_up(rows, 100, self.FPS) <= 62

    def test_hits_where_the_ball_is_nearest_a_wrist(self):
        frames = window(100, self.FPS)
        keypoints = [None] * len(frames)
        for k, f in enumerate(frames):
            points = np.zeros((17, 3))
            points[10] = [500.0, 300.0, 0.9]
            keypoints[k] = points.tolist()
        ball = {f: (500.0 + 10 * abs(f - 106), 300.0) for f in range(90, 120)}
        assert hit(100, keypoints, ball, self.FPS) == 106
        # Too far from the contact, or no ball seen: the contact stays.
        assert hit(100, keypoints, {f: (500.0, 300.0) for f in (80, 120)}, self.FPS) == 100
        assert hit(100, keypoints, {}, self.FPS) == 100

    def test_mirrors_an_end_a_hidden_foot_runs_off(self, monkeypatch):
        monkeypatch.setattr(jumps, "HEEL_UP_S", 0.0)
        monkeypatch.setattr(jumps, "HEEL_DOWN_S", 0.0)
        rows, keypoints, calibration = self.attack()
        frames = list(window(self.CONTACT, self.FPS))
        # After landing, another player's foot stands in for the ankle, as high as at the flight's top, for 0.4 s.
        high = keypoints[frames.index(85)][15]
        for f in range(self.LANDING, self.LANDING + 20):
            keypoints[frames.index(f)] = [p if i not in (15, 16) else high for i, p in enumerate(keypoints[frames.index(f)])]
        got = measure(self.CONTACT, rows, keypoints, calibration, self.FPS)
        assert got is not None
        assert abs(got["takeoff"] - self.TAKEOFF) <= 1 and abs(got["landing"] - self.LANDING) <= 2

    def test_holds_when_the_ankle_is_lost_right_after_its_highest(self):
        y = np.full(81, 500.0)
        y[41] = 450.0
        y[43:] = np.nan
        found = flight(y, lift(y, 100.0), 40, self.FPS)
        assert found is None or (found[1] - found[0]) / self.FPS < jumps.SHORTEST_S

    def test_keeps_each_attacks_rows_and_reads_the_players_once(self, monkeypatch, tmp_path):
        rows = np.array([[f, 0, 0, 1, 1, 0, 0] for f in range(0, 1000)], float)
        reads = []
        monkeypatch.setattr(jumps, "read_tracks", lambda path, tracks: reads.append(tracks) or {t: rows for t in tracks})
        first = attack_rows(tmp_path / "players.csv", [(500, 3)], self.FPS, tmp_path / "rows.npz")
        again = attack_rows(tmp_path / "players.csv", [(500, 3)], self.FPS, tmp_path / "rows.npz")
        frames = first[(500, 3)][:, 0]
        # The run-up's 2 s and the window's 0.8 s before the contact, its 0.8 s after, and a margin.
        assert frames.min() <= 500 - (jumps.BEFORE_S + jumps.RUN_UP_S) * self.FPS and frames.max() >= 500 + jumps.AFTER_S * self.FPS
        assert len(frames) < len(rows) and np.array_equal(first[(500, 3)], again[(500, 3)]) and reads == [{3}]
