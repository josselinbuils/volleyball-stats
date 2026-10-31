import numpy as np

from volleyball_stats.contacts import detect, detect_contacts, detect_crossings, gravity, peaks

FPS = 30.0
G = 0.6


def flight(start: tuple[float, float], velocity: tuple[float, float], frames: int) -> np.ndarray:
    """Positions of a free flight under gravity G, rounded like the tracker's."""
    t = np.arange(frames)[:, None]
    return np.round(np.array(start) + t * np.array(velocity) + [0, G / 2] * t**2)


class TestGravity:
    def test_recovers_the_acceleration_of_a_flight(self):
        assert abs(gravity(flight((100, 300), (6, -14), 50), 5) - G) < 0.05

    def test_is_zero_without_a_moving_ball(self):
        assert gravity(np.full((40, 2), np.nan), 5) == 0.0


class TestPeaks:
    def test_keeps_the_strongest_frame_of_a_cluster_and_sorts_by_frame(self):
        signal = np.array([0, 5, 9, 7, 0, 0, 0, 0, 8, 0], dtype=float)

        assert peaks(signal, 5, 2) == [2, 8]

    def test_ignores_nan_and_values_under_the_threshold(self):
        assert peaks(np.array([np.nan, 3, np.nan, 4]), 5, 2) == []


class TestDetectContacts:
    def test_finds_the_frame_where_the_velocity_changes(self):
        incoming = flight((100, 300), (10, -12), 31)
        outgoing = flight(incoming[-1], (-8, -15), 30)
        track = np.vstack([incoming, outgoing[1:]])

        contacts = detect_contacts(track, FPS)

        assert len(contacts) == 1
        frame, x, y = contacts[0]
        assert abs(frame - 30) <= 1
        assert (x, y) == tuple(track[frame])

    def test_ignores_an_apex_hidden_in_a_gap(self):
        track = flight((100, 300), (5, -15), 60)
        track[18:33] = np.nan

        assert detect_contacts(track, FPS) == []

    def test_interpolates_the_position_of_a_contact_hidden_in_a_gap(self):
        incoming = flight((100, 300), (10, -12), 31)
        track = np.vstack([incoming, flight(incoming[-1], (-8, -15), 30)[1:]])
        track[29:32] = np.nan

        contacts = detect_contacts(track, FPS)

        assert len(contacts) == 1
        frame, x, y = contacts[0]
        assert abs(frame - 30) <= 1
        assert abs(x - incoming[-1, 0]) < 30 and abs(y - incoming[-1, 1]) < 30


class TestDetectCrossings:
    def test_interpolates_the_crossing_frame_over_a_gap(self):
        track = np.stack([500 + 10.0 * np.arange(21), np.full(21, 200.0)], axis=1)
        track[9:15] = np.nan

        assert detect_crossings(track, 612, FPS) == [11]

    def test_counts_a_frame_exactly_on_the_net_once(self):
        track = np.stack([572 + 10.0 * np.arange(10), np.full(10, 200.0)], axis=1)

        assert detect_crossings(track, 612, FPS) == [4]

    def test_ignores_a_ball_played_at_the_net(self):
        x = np.array([500, 560, 600, 620, 605, 625, 600, 560, 500], dtype=float)

        assert detect_crossings(np.stack([x, np.full(len(x), 200.0)], axis=1), 612, FPS) == []

    def test_does_not_interpolate_over_a_long_gap(self):
        track = np.stack([500 + 10.0 * np.arange(21), np.full(21, 200.0)], axis=1)
        track[5:18] = np.nan

        assert detect_crossings(track, 612, 10.0) == []


class TestDetect:
    def test_returns_contacts_and_crossings(self):
        incoming = flight((400, 300), (10, -12), 31)
        track = np.vstack([incoming, flight(incoming[-1], (12, -15), 30)[1:]])

        contacts, crossings = detect(track, FPS, 612)

        assert [abs(frame - 30) <= 1 for frame, _, _ in contacts] == [True]
        assert len(crossings) == 1 and track[crossings[0] - 1, 0] <= 612 <= track[crossings[0] + 1, 0]

    def test_finds_nothing_without_a_visible_ball(self):
        assert detect(np.full((100, 2), np.nan), FPS, 612) == ([], [])
