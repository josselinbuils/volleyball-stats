import numpy as np
import pytest

from volleyball_stats.framing import MARGIN, MIN_VIEW, SERVER_MARGIN, players_box, read_boxes, view_of, views, with_server


def boxes(*players):
    """A row every 0.1 s from 0 to 20 s for each player's (track, x1, x2)."""
    rows = [(t / 10, track, x1, 0.3, x2, 0.6) for t in range(201) for track, x1, x2 in players]
    return np.array(rows, dtype=float)


def rally(start=5, end=15):
    return {"start": start, "end": end}


def test_read_boxes_keeps_a_row_every_step_in_fractions(tmp_path):
    path = tmp_path / "players.csv"
    path.write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "".join(f"{f},1,left,100,50,200,150,0.9,0,0,0,0\n" for f in range(6)))

    found = read_boxes(path, (1000, 500), 50)

    assert found.tolist() == [[0, 1, 0.1, 0.1, 0.2, 0.3], [0.1, 1, 0.1, 0.1, 0.2, 0.3]]


def test_a_short_track_is_no_player():
    rows = np.vstack([boxes((1, 0.3, 0.4)), [[5.05, 9, 0, 0.3, 0.05, 0.6]]])

    assert players_box(rows[np.argsort(rows[:, 0])], 0, 10)[0] == 0.3 - MARGIN


def test_a_view_has_the_pictures_shape_with_the_players_at_its_bottom_inside_the_picture():
    assert view_of((0.2, 0.1, 0.9, 0.6)) == pytest.approx((0.2, 0, 0.7))
    assert view_of((0.8, 0.1, 1, 0.9)) == pytest.approx((0.2, 0.1, 0.8))
    assert view_of((0.4, 0.4, 0.5, 0.5))[2] == MIN_VIEW


def test_the_serve_then_the_exchange_then_the_whole_picture():
    server = (1, 0.0, 0.1)
    others = (2, 0.3, 0.8)
    rows = boxes(others)
    # The server stands back until the serve at 5 s.
    rows = np.vstack([rows, [r for r in boxes(server) if r[0] <= 5]])
    rows = rows[np.argsort(rows[:, 0], kind="stable")]

    found = views(rows, [rally()], [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}])

    # The whole picture, the server's view 3 s before the serve, the exchange's.
    assert [v[0] for v in found] == [0, 2, 5.3, 16]
    assert found[0][3] == 1 and found[1][1] == 0 and found[1][3] > found[2][3]
    assert found[-1][1:] == [0, 0, 1]


def test_the_serves_view_shows_a_server_only_the_ball_gives_away():
    rows = boxes((1, 0.2, 0.7))
    touches = [{"t": 5, "type": "serve", "rally": 0}, {"t": 17, "type": "serve", "rally": 1}]
    ball = np.array([[1, 0.5, 0.4], [16.9, 0.9, 0.4]])

    found = views(rows, [rally(), rally(17, 19)], touches, ball)

    # The whole picture before the first serve, the server 3 s before it; a 2 s break goes straight to the next server.
    assert [v[0] for v in found] == [0, 2, 16, 20]
    assert found[2][1] + found[2][3] == pytest.approx(0.9 + SERVER_MARGIN)


def test_a_ball_far_from_the_serve_says_nothing_of_the_server():
    assert with_server((0.2, 0.3, 0.7, 0.6), np.array([[4, 0.9, 0.4], [6, 0.9, 0.4]]), 5) == (0.2, 0.3, 0.7, 0.6)


def test_a_view_that_fits_is_kept():
    rows = boxes((1, 0.2, 0.8))

    found = views(rows, [rally(), rally(17, 19)], [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}, {"t": 17, "type": "serve", "rally": 1}, {"t": 18, "type": "pass", "rally": 1}])

    assert [v[0] for v in found] == [0, 2, 20]


def test_a_long_break_shows_the_whole_picture_until_the_next_serve_comes():
    rows = boxes((1, 0.2, 0.7))
    touches = [{"t": 1, "type": "serve", "rally": 0}, {"t": 2, "type": "pass", "rally": 0}, {"t": 17, "type": "serve", "rally": 1}, {"t": 18, "type": "pass", "rally": 1}]

    found = views(rows, [rally(1, 5), rally(17, 19)], touches)

    assert [(v[0], v[3] == 1) for v in found] == [(0, False), (6, True), (14, False), (20, True)]


def test_a_short_exchange_keeps_the_serves_view():
    rows = np.vstack([boxes((1, 0.3, 0.8)), [r for r in boxes((2, 0.0, 0.1)) if r[0] <= 5]])
    rows = rows[np.argsort(rows[:, 0], kind="stable")]

    found = views(rows, [rally(5, 6.5)], [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}])

    assert [v[0] for v in found] == [0, 2, 7.5]


def test_no_players_no_views():
    assert views(np.empty((0, 6)), [rally()], []) == []


def test_the_exchange_is_followed_second_by_second_closer_than_its_whole():
    # Two players crossing the picture from the left to the right over the rally.
    rows = np.array([(t / 10, track, 0.05 + t / 300 + dx, 0.3, 0.15 + t / 300 + dx, 0.6) for t in range(201) for track, dx in ((1, 0), (2, 0.1))])
    touches = [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}]

    found = views(rows, [rally(5, 15)], touches)
    during = [v for v in found if 5.3 <= v[0] < 15]

    assert len(during) > 3
    assert all(v[3] == pytest.approx(MIN_VIEW) for v in during)
    assert during[-1][1] > during[0][1]


class TestCamera:
    def test_follows_the_view_with_a_spring_and_comes_back_to_the_whole_picture(self):
        from volleyball_stats.framing import camera

        track = camera([[0, 0, 0, 1], [5, 0.2, 0.1, 0.5], [10, 0, 0, 1]], np.empty((0, 3)), 20)

        assert track.shape == (201, 3) and track[0].tolist() == [0.5, 0.5, 1.0]
        # Under way a second before the view (averaged), there a second after, the whole picture again at the end.
        assert 1 < track[45, 2] < 2 and track[70].tolist() == pytest.approx([0.45, 0.35, 2.0], abs=0.01)
        assert track[-1].tolist() == pytest.approx([0.5, 0.5, 1.0], abs=0.001)
        assert np.all(np.diff(track[40:70, 2]) >= 0)

    def test_widens_to_keep_the_ball_in(self):
        from volleyball_stats.framing import EDGE, camera

        ball = np.array([[t / 10, 0.9, 0.3] for t in range(0, 201)])
        track = camera([[0, 0.2, 0.1, 0.5]], ball, 20)

        x, _, zoom = track[100]
        # EDGE of the players' view (0.5 wide) kept beside the ball.
        assert x + 0.5 / zoom == pytest.approx(0.9 + EDGE * 0.5, abs=1e-3) and zoom < 2

    def test_spans_keep_the_zoomed_moments_only_and_read_back_between_samples(self):
        from volleyball_stats.framing import CAMERA_STEP_S, camera, camera_at, camera_spans

        track = camera([[0, 0, 0, 1], [5, 0.2, 0.1, 0.5], [10, 0, 0, 1]], np.empty((0, 3)), 20)
        spans = camera_spans(track)

        assert len(spans) == 1 and 2 < spans[0][0] < 4
        times = np.arange(len(track)) * CAMERA_STEP_S
        assert np.abs(camera_at(spans, times) - track).max() < 1e-3
        between = camera_at(spans, np.array([7.05]))[0]
        assert between == pytest.approx((track[70] + track[71]) / 2, abs=1e-4)
        assert camera_at([], np.array([3.0])).tolist() == [[0.5, 0.5, 1.0]]

    def test_reads_back_as_the_page_does(self):
        from volleyball_stats.framing import camera_at

        # The same runs as web's zoom.test.ts: both cut and draw by the same camera.
        spans = [[2, 5000, 5000, 10000, -1000, 0, 5000, 0, -500, 5000]]
        assert camera_at(spans, np.array([2.1, 2.15, 2.3])).ravel().tolist() == pytest.approx([0.4, 0.5, 1.5, 0.4, 0.475, 1.75, 0.5, 0.5, 1.0])
