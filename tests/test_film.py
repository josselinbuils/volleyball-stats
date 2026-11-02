import json
import math
import subprocess

import numpy as np
import pytest

from volleyball_stats import film, web


def contact(i, t, kind, person, g=1, result="play", rally=0, **more):
    return {"i": i, "t": t, "f": round(t * 50), "type": kind, "person": person, "g": g, "team": g, "result": result, "rally": rally, **more}


def rally(i, contacts, score, winner=1, number=1, start=None):
    return {"i": i, "contacts": contacts, "score": score, "winner": winner, "set": number, "start": start if start is not None else contacts[0]["t"] - 1, "end": contacts[-1]["t"] + 1}


class TestMoments:
    def test_puts_the_fastest_serve_first_then_the_points_building_up_to_the_best(self):
        serve = contact(0, 10.0, "serve", 1, speed=60)
        slow = contact(1, 20.0, "serve", 1, speed=40)
        ace_rally = contact(2, 30.0, "serve", 1, result="point", rally=2)
        won = contact(3, 40.0, "attack", 1, result="point", rally=3)
        rallies = [rally(0, [serve], [0, 1], 2), rally(1, [slow], [0, 2], 2), rally(2, [ace_rally], [1, 2]), rally(3, [won], [2, 2])]
        for c in (slow, ace_rally, won):
            c["rally"] = rallies.index(next(r for r in rallies if c in r["contacts"]))
        mine = [serve, slow, ace_rally, won]

        found = film.moments_of(rallies, {1}, mine)

        assert found[0] is serve
        assert ace_rally in found and won in found
        # Nothing they got wrong, at most one a rally.
        assert len({c["rally"] for c in found}) == len(found)

    def test_leaves_out_what_they_got_wrong(self):
        fault = contact(0, 10.0, "attack", 1, result="error")
        assert film.moments_of([rally(0, [fault], [0, 1], 2)], {1}, [fault]) == []

    def test_shots_are_a_title_each_moment_played_then_replayed_and_an_end(self):
        c = contact(0, 10.0, "attack", 1, result="point")
        shots, length = film.shots_of([c], [rally(0, [c], [1, 0], start=5.0)])
        assert [s["kind"] for s in shots] == ["intro", "live", "replay", "outro"]
        assert shots[1]["from"] == pytest.approx(6.5)
        assert shots[1]["length"] == pytest.approx(film.LEAD_S + film.AFTER_POINT_S)
        assert length == pytest.approx(sum(s["length"] for s in shots))


class TestPlan:
    @staticmethod
    def page():
        contacts = [contact(0, 10.0, "serve", 1, speed=50), contact(1, 20.0, "attack", 1, result="point", rally=1), contact(2, 21.0, "floor", None, rally=1)]
        rallies = [rally(0, contacts[:1], [0, 1], 2), rally(1, contacts[1:], [1, 1], 1, start=15.0)]
        for r in rallies:
            r["end"] = r["contacts"][-1]["t"] + 1
        return {"rallies": rallies, "contacts": contacts, "teams": [{"name": "A", "colour": "#000000"}, {"name": "B", "colour": "#ff0000"}], "date": "2026-10-29", "positions": {"step": 5}, "people": {"1": {"team": 1, "number": 1, "name": "Élodie", "jersey": 7}, "2": {"team": 2, "number": 2, "name": "Solo", "jersey": None}}}

    def test_gives_a_film_to_each_player_with_two_moments(self, tmp_path):
        films = film.plan(self.page(), tmp_path)
        assert list(films) == ["Élodie"]
        assert films["Élodie"]["file"] == "1-elodie.mp4"
        assert (films["Élodie"]["touches"], films["Élodie"]["points"], films["Élodie"]["fastest"]) == (2, 1, 50)

    def test_changes_only_with_what_the_film_shows(self, tmp_path):
        page = self.page()
        first = film.plan(page, tmp_path)["Élodie"]["hash"]
        assert film.plan(page, tmp_path)["Élodie"]["hash"] == first
        page["people"]["2"]["name"] = "Another"
        assert film.plan(page, tmp_path)["Élodie"]["hash"] == first
        page["people"]["1"]["jersey"] = 8
        assert film.plan(page, tmp_path)["Élodie"]["hash"] != first
        page["people"]["1"]["jersey"] = 7
        page["rallies"][1]["score"] = [2, 1]
        assert film.plan(page, tmp_path)["Élodie"]["hash"] != first
        assert film.plan(self.page(), tmp_path, "another tracking")["Élodie"]["hash"] != first

    def test_says_how_many_films_are_missing_or_out_of_date(self, tmp_path, monkeypatch):
        assert film.status(tmp_path) == {"total": 0, "stale": 0}
        page = self.page()
        (tmp_path / "review").mkdir()
        monkeypatch.setattr(film, "read_page", lambda _: page)
        assert film.status(tmp_path) == {"total": 1, "stale": 1}
        planned = film.plan(page, tmp_path / "review", film.tracking_stamp(tmp_path))["Élodie"]
        (tmp_path / "films").mkdir()
        (tmp_path / "films" / planned["file"]).write_bytes(b"film")
        (tmp_path / "films" / "manifest.json").write_text(json.dumps({"Élodie": {"hash": planned["hash"], "file": planned["file"]}}))
        assert film.status(tmp_path) == {"total": 1, "stale": 0}
        page["people"]["1"]["jersey"] = 9
        assert film.status(tmp_path) == {"total": 1, "stale": 1}


class TestServingBody:
    def test_keeps_the_named_player_behind_the_line(self):
        assert film.serving_body((-8.5, 1.0), {5: (-9.5, 2.0)}) is None

    def test_follows_the_teammate_behind_the_line_when_the_named_track_is_inside_the_court(self):
        assert film.serving_body((0.4, 1.0), {5: (-8.8, 2.1), 6: (-3.0, 0.0)}) == 5
        assert film.serving_body(None, {5: (8.8, 2.1)}) == 5

    def test_keeps_them_when_nobody_is_behind_the_line(self):
        assert film.serving_body((0.4, 1.0), {6: (-3.0, 0.0)}) is None


class TestBuild:
    def test_makes_only_the_films_that_changed_and_keeps_those_made_when_one_fails(self, tmp_path, monkeypatch):
        page = TestPlan.page()
        page["people"]["2"].update(name="Other")
        page["contacts"] += [contact(3, 30.0, "serve", 2, 2, speed=40, rally=2), contact(4, 40.0, "attack", 2, 2, result="point", rally=3)]
        page["rallies"] += [rally(2, [page["contacts"][3]], [1, 2], 1), rally(3, [page["contacts"][4]], [1, 3], 2)]
        monkeypatch.setattr(film, "read_page", lambda _: page)
        asked = []

        def run(command, check):
            asked.append(command[-2:])
            if command[-2:] == ["--make", "Other"] and fail:
                raise subprocess.CalledProcessError(1, command)
            if command[-2] == "--make":
                (tmp_path / "films" / film.plan(page, tmp_path / "review", "")[command[-1]]["file"]).write_bytes(b"film")

        monkeypatch.setattr(film.subprocess, "run", run)
        fail = True
        with pytest.raises(subprocess.CalledProcessError):
            film.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json")
        assert list(film.manifest(tmp_path)) == ["Élodie"]
        # The next press makes what is left, and only that.
        fail, asked[:] = False, []
        assert film.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json") == ["Other"]
        assert ["--make", "Other"] in asked and ["--make", "Élodie"] not in asked
        asked.clear()
        assert film.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json") == []
        assert asked == []


class TestBallPath:
    @staticmethod
    def flight(start, n, x0, y0, vx, vy, g=0.4):
        return {start + k: (x0 + vx * k, y0 + vy * k + g * k * k / 2) for k in range(n)}

    def test_crosses_a_hole_on_the_flight_s_curve(self):
        ball = self.flight(100, 60, 500, 500, 12, -8)
        truth = dict(ball)
        for q in range(120, 135):
            del ball[q]

        path = film.rally_path(ball, [100], 90, 170)

        for q in range(120, 135):
            assert math.hypot(path[q][0] - truth[q][0], path[q][1] - truth[q][1]) < 6

    def test_leaves_out_what_never_moves_and_what_no_ball_could_reach(self):
        ball = self.flight(100, 60, 500, 500, 12, -8)
        also = {q: (3000.0, 200.0) for q in range(90, 170)}
        ball[130] = (3500.0, 1800.0)

        path = film.rally_path(ball, [100], 90, 170, also)

        assert all(math.hypot(path[q][0] - 3000, path[q][1] - 200) > 500 for q in path)
        assert math.hypot(path[130][0] - (500 + 12 * 30), path[130][1] - (500 - 8 * 30 + 0.4 * 900 / 2)) < 12

    def test_goes_through_a_touch_whatever_the_frame_recorded_without_a_jump(self):
        ball = {**self.flight(100, 30, 500, 500, 10, 5), **self.flight(130, 30, 790, 788, -20, 3)}

        # The touch recorded 4 frames after the real one.
        path = film.rally_path(ball, [134, 158], 90, 170)

        steps = [math.hypot(path[q][0] - path[q - 1][0], path[q][1] - path[q - 1][1]) for q in path if q - 1 in path]
        assert max(steps) < 40
        assert math.hypot(path[132][0] - ball[132][0], path[132][1] - ball[132][1]) < 16

    def test_ends_at_the_landing_after_the_last_touch(self):
        down = self.flight(100, 30, 500, 300, 10, 15, 0.2)
        up = self.flight(130, 30, 790, 830, 8, -14, 0.2)

        path = film.rally_path({**down, **up}, [100], 90, 170)

        assert 129 in path and 145 not in path

    def test_ends_where_the_ball_is_lost_after_the_last_touch(self):
        ball = {**self.flight(100, 20, 500, 300, 10, 5), **self.flight(150, 20, 700, 1100, -10, -5)}
        assert max(film.rally_path(ball, [100], 90, 175)) == 119


class TestFrames:
    def test_joins_the_frames_close_enough_to_read_through(self):
        assert film.ranges([1, 2, 3, 8, 30, 31]) == [(1, 8), (30, 31)]

    def test_holds_still_while_the_target_stays_within_the_slack(self):
        path = film.holds(np.array([0.0, 2.0, -2.0, 1.0, 20.0, 40.0]), 5.0)
        assert np.ptp(path[:4]) < 3
        assert path[-1] > 30
