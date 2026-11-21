import numpy as np
import pytest

from volleyball_stats import timeline as tl


def match(rallies, timeouts=(), calls=(), duration=200.0):
    """Rallies as (start, end, set)."""
    return {"rallies": [{"start": a, "end": b, "set": s} for a, b, s in rallies], "timeouts": list(timeouts), "lineCalls": list(calls), "duration": duration}


def test_rallies_play_short_breaks_twice_as_fast_long_pauses_cut():
    data = match([(10, 20, 1), (30, 40, 1), (100, 110, 1), (130, 140, 2)])

    pieces = tl.plan(data, np.empty((0, 3)))

    # 2 s before the first rally; the 10 s break: 1 s, 8 s at x2, 1 s; the 60 s one and the set's end cut, 2 s each side.
    assert pieces == [[8, 21, 0, 13], [21, 29, 13, 17], [29, 42, 17, 30], [98, 112, 30, 44], [128, 142, 44, 58]]
    assert tl.cuts(pieces) == [30, 44]


def test_a_timeout_cuts_its_break():
    data = match([(10, 20, 1), (30, 40, 1)], timeouts=[{"start": 22, "end": 27}])

    assert tl.cuts(tl.plan(data, np.empty((0, 3)))) == [14]


def test_a_close_call_slows_down_to_its_bounce_and_holds_it():
    ball = np.array([[t / 100, 0.5, 0.3 + (0.1 if t == 1507 else 0)] for t in range(1450, 1550)])
    data = match([(10, 16, 1)], calls=[{"t": 15.0}])

    pieces = tl.plan(data, ball)

    # The bounce is where the ball is lowest: 15.07.
    assert [p[:2] for p in pieces] == [[8, 14.47], [14.47, 15.07], [15.07, 15.07], [15.07, 18]]
    assert pieces[1][3] - pieces[1][2] == pytest.approx(1.2) and pieces[2][3] - pieces[2][2] == tl.HOLD_S
    assert tl.held(pieces) == [(pytest.approx(7.67), pytest.approx(9.67))]
    # The call, its touch just before its bounce, shows from the hold.
    assert tl.retimed({**data, "contacts": []}, pieces)["lineCalls"] == [{"t": pytest.approx(7.67)}]


def test_times_both_ways():
    pieces = [[8, 20, 0, 12], [20, 30, 12, 17], [50, 60, 17, 27], [60, 60, 27, 29], [60, 70, 29, 39]]

    assert tl.to_copy(pieces, np.array([8, 25, 40, 55, 60, 65, 99])).tolist() == [0, 14.5, 17, 22, 27, 34, 39]
    assert tl.to_source(pieces, np.array([0, 14.5, 22, 28, 34])).tolist() == [8, 25, 55, 60, 65]
    assert tl.fade(pieces, np.array([17, 16.85, 16])).tolist() == pytest.approx([0, 0.5, 1])


def test_the_page_data_and_the_ball_on_the_copys_time():
    pieces = [[8, 20, 0, 12], [50, 60, 12, 22]]
    data = {"rallies": [{"start": 10, "window": 9, "end": 19, "set": 1}, {"start": 52, "window": 51, "end": 58, "set": 1}], "contacts": [{"t": 12}], "timeouts": [{"start": 25, "end": 40}], "views": [[0, 0, 0, 1], [51, 0.2, 0.1, 0.5]], "duration": 100, "end": None}

    out = tl.retimed(data, pieces)

    assert out["duration"] == 22 and out["length"] == 100 and out["rallies"][1] == {"start": 14, "window": 13, "end": 20, "set": 1, "real": [52, 58]}
    assert out["contacts"] == [{"t": 4}] and out["timeouts"] == [{"start": 12, "end": 12}] and out["views"][1][0] == 13
    ball = tl.retimed_ball(np.array([[10, 0.1, 0.2], [30, 0.5, 0.5], [55, 0.3, 0.3]]), pieces)
    assert ball.tolist() == [[2, 0.1, 0.2], [17, 0.3, 0.3]]


def test_positions_on_the_copys_time():
    # A sample every 0.1 s of a 50 fps match (step 5 frames): the copy plays 0-2 s then 5-6 s.
    players = {"step": 5, "samples": [[k] for k in range(100)]}

    out = tl.retimed_positions(players, 50, [[0, 2, 0, 2], [5, 6, 2, 3]])

    assert [s[0] for s in out["samples"]][::5] == [0, 5, 10, 15, 50, 55, 60]


def test_copies_are_worth_making_again_once_a_rally_or_a_close_call_moved():
    plan = tl.plan(match([(10, 16, 1), (30, 40, 1)]), np.empty((0, 3)))
    ball = np.array([[t / 100, 0.5, 0.3 + (0.1 if t == 1507 else 0)] for t in range(1450, 1550)])

    assert not tl.moved(plan, plan)
    # A rally's end a second later still serves; three seconds, or a rally more, not.
    assert not tl.moved(plan, tl.plan(match([(10, 17, 1), (30, 40, 1)]), np.empty((0, 3))))
    assert tl.moved(plan, tl.plan(match([(10, 19, 1), (30, 40, 1)]), np.empty((0, 3))))
    assert tl.moved(plan, tl.plan(match([(10, 16, 1), (30, 40, 1), (60, 70, 1)]), np.empty((0, 3))))
    assert tl.moved(plan, tl.plan(match([(10, 16, 1)]), np.empty((0, 3))))
    # A close call added.
    assert tl.moved(plan, tl.plan(match([(10, 16, 1), (30, 40, 1)], calls=[{"t": 15.0}]), ball))
