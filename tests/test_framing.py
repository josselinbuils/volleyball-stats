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

    assert [v[0] for v in found] == [0, 5.3, 16]
    assert found[0][1] == 0 and found[0][3] > found[1][3]
    assert found[-1][1:] == [0, 0, 1]


def test_the_serves_view_shows_a_server_only_the_ball_gives_away():
    rows = boxes((1, 0.2, 0.7))
    touches = [{"t": 5, "type": "serve", "rally": 0}, {"t": 17, "type": "serve", "rally": 1}]
    ball = np.array([[1, 0.5, 0.4], [16.9, 0.9, 0.4]])

    found = views(rows, [rally(), rally(17, 19)], touches, ball)

    assert [v[0] for v in found] == [0, 16, 20]
    assert found[1][1] + found[1][3] == pytest.approx(0.9 + SERVER_MARGIN)


def test_a_ball_far_from_the_serve_says_nothing_of_the_server():
    assert with_server((0.2, 0.3, 0.7, 0.6), np.array([[4, 0.9, 0.4], [6, 0.9, 0.4]]), 5) == (0.2, 0.3, 0.7, 0.6)


def test_a_view_that_fits_is_kept():
    rows = boxes((1, 0.2, 0.8))

    found = views(rows, [rally(), rally(17, 19)], [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}, {"t": 17, "type": "serve", "rally": 1}, {"t": 18, "type": "pass", "rally": 1}])

    assert [v[0] for v in found] == [0, 20]


def test_a_short_exchange_keeps_the_serves_view():
    rows = np.vstack([boxes((1, 0.3, 0.8)), [r for r in boxes((2, 0.0, 0.1)) if r[0] <= 5]])
    rows = rows[np.argsort(rows[:, 0], kind="stable")]

    found = views(rows, [rally(5, 6.5)], [{"t": 5, "type": "serve", "rally": 0}, {"t": 6, "type": "pass", "rally": 0}])

    assert [v[0] for v in found] == [0, 7.5]


def test_no_players_no_views():
    assert views(np.empty((0, 6)), [rally()], []) == []
