import json
import subprocess

import numpy as np
import pytest

from volleyball_stats import film, web


def contact(i, t, kind, person, g=1, result="play", rally=0, **more):
    return {"i": i, "t": t, "f": round(t * 50), "type": kind, "person": person, "g": g, "team": g, "result": result, "rally": rally, **more}


def rally(i, contacts, score, winner=1, number=1, start=None):
    return {"i": i, "contacts": contacts, "score": score, "winner": winner, "set": number, "start": start if start is not None else contacts[0]["t"] - 1, "end": contacts[-1]["t"] + 1}


class TestMoments:
    def test_the_fastest_serve_and_attack_are_a_named_player_s(self):
        people = {"1": {"name": "Ana"}, "2": {"name": None}}
        contacts = [
            {"type": "serve", "person": 1, "speed": 50},
            {"type": "serve", "person": 2, "speed": 70},
            {"type": "attack", "person": 1, "attackSpeed": 60, "speed": 99},
            {"type": "attack", "person": 1, "attackSpeed": 65},
        ]
        assert film.fastest(contacts, people, "serve")["speed"] == 50
        assert film.fastest(contacts, people, "attack")["attackSpeed"] == 65
        assert film.fastest([], people, "attack") is None

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

    def test_always_shows_the_touches_picked_in_the_review(self):
        points = [contact(k, 10.0 * k, ("attack", "serve", "block")[k % 3], 1, result="point", rally=k) for k in range(film.MOMENTS + 2)]
        dig = contact(len(points), 200.0, "dig", 1, rally=len(points))
        mine = [*points, dig]
        rallies = [rally(k, [c], [k, 0]) for k, c in enumerate(mine)]

        assert dig not in film.moments_of(rallies, {1}, mine)
        assert dig in film.moments_of(rallies, {1}, mine, [dig])

    def test_leaves_out_what_they_got_wrong(self):
        fault = contact(0, 10.0, "attack", 1, result="error")
        assert film.moments_of([rally(0, [fault], [0, 1], 2)], {1}, [fault]) == []

    def test_mixes_the_kinds_of_touch_while_there_is_anything_else_to_show(self):
        serves = [contact(k, 10.0 * k, "serve", 1, result="point", rally=k) for k in range(5)]
        others = [contact(5 + k, 50.0 + 10 * k, kind, 1, rally=5 + k) for k, kind in enumerate(("dig", "pass", "set", "block"))]
        mine = [*serves, *others]
        rallies = [rally(k, [c], [k, 0]) for k, c in enumerate(mine)]

        found = film.moments_of(rallies, {1}, mine)

        assert len(found) == film.MOMENTS
        assert sum(c["type"] == "serve" for c in found) <= film.SAME_KIND + 1
        assert {"dig", "pass", "set", "block"} <= {c["type"] for c in found}

    def test_shows_a_kind_again_when_the_player_has_nothing_else(self):
        serves = [contact(k, 10.0 * k, "serve", 1, rally=k) for k in range(film.MOMENTS)]
        assert len(film.moments_of([rally(k, [c], [0, k + 1], 2) for k, c in enumerate(serves)], {1}, serves)) == film.MOMENTS

    def test_keeps_the_same_kind_apart_where_it_can_the_best_last(self):
        kinds = ["serve", "attack", "attack", "block", "attack"]
        found = film.varied([{"type": k, "n": n} for n, k in enumerate(kinds)])
        assert [c["type"] for c in found] == ["serve", "attack", "block", "attack", "attack"]
        assert found[-1]["n"] == 4

    def test_moves_a_repeat_away_from_the_best_last(self):
        found = film.varied([{"type": k} for k in ["serve", "block", "dig", "attack", "attack"]])
        assert all(a["type"] != b["type"] for a, b in zip(found, found[1:]))

    def test_replays_only_the_measured_first_and_the_best_last(self):
        cs = [contact(0, 10.0, "serve", 1, speed=50), contact(1, 30.0, "dig", 1, rally=1), contact(2, 50.0, "attack", 1, result="point", rally=2)]
        shots, _ = film.shots_of(cs, [rally(k, [c], [k, 0], start=c["t"] - 2) for k, c in enumerate(cs)])
        assert [s["contact"] for s in shots if s["kind"] == "replay"] == [0, 2]

    def test_shots_are_a_title_each_moment_played_then_replayed_and_an_end(self):
        c = contact(0, 10.0, "attack", 1, result="point")
        shots, length = film.shots_of([c], [rally(0, [c], [1, 0], start=5.0)])
        assert [s["kind"] for s in shots] == ["intro", "live", "replay", "outro"]
        assert shots[2]["from"] == pytest.approx(10.0 - film.REPLAY_BEFORE_S)
        assert shots[1]["from"] == pytest.approx(10.0 - film.PUNCH_LEAD_S)
        assert shots[1]["length"] == pytest.approx(film.PUNCH_LEAD_S + film.AFTER_POINT_S)
        assert length == pytest.approx(sum(s["length"] for s in shots))

    def test_opens_on_its_most_striking_point_but_the_best_before_the_title(self):
        cs = [contact(0, 10.0, "attack", 1, result="point", reach=2.9), contact(1, 30.0, "serve", 1, result="point", rally=1, speed=60), contact(2, 50.0, "attack", 1, result="point", rally=2, reach=3.1)]
        shots, _ = film.shots_of(cs, [rally(k, [c], [k, 0]) for k, c in enumerate(cs)])
        assert [s["kind"] for s in shots[:2]] == ["live", "intro"] and shots[0]["hook"] and shots[0]["contact"] == 0


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

    def test_names_the_films_missing_or_out_of_date(self, tmp_path, monkeypatch):
        none = {"total": 0, "stale": []}
        assert film.status(tmp_path) == {"players": none, "highlights": none}
        page = self.page()
        (tmp_path / "review").mkdir()
        monkeypatch.setattr(film, "read_page", lambda _: page)
        assert film.status(tmp_path) == {"players": {"total": 1, "stale": ["Élodie"]}, "highlights": none}
        planned = film.plan(page, tmp_path / "review", film.tracking_stamp(tmp_path))["Élodie"]
        (tmp_path / "films").mkdir()
        (tmp_path / "films" / planned["file"]).write_bytes(b"film")
        (tmp_path / "films" / "manifest.json").write_text(json.dumps({"Élodie": {"hash": planned["hash"], "file": planned["file"]}}), encoding="utf-8")
        assert film.status(tmp_path) == {"players": {"total": 1, "stale": []}, "highlights": none}
        page["people"]["1"]["jersey"] = 9
        assert film.status(tmp_path) == {"players": {"total": 1, "stale": ["Élodie"]}, "highlights": none}


def called(page):
    """`page` with its rallies' line calls, as read_page gives them."""
    for call in web.line_calls(page):
        page["rallies"][call["rally"]]["call"] = call
    return page


class TestLineCall:
    @staticmethod
    def attack(x, winner, **more):
        """Team 1 attacks from the left; the ball lands at (x, 1) on the right."""
        r = {**rally(0, [contact(0, 10.0, "attack", 1, x=-2.0, y=0.0), contact(1, 10.5, "floor", None, g=2, x=x, y=1.0)], [1, 0], winner), **more}
        return called({"rallies": [r], "contacts": r["contacts"], "teams": [{"name": "A"}, {"name": "B"}]})["rallies"][0]

    def test_calls_a_close_landing_as_the_point_went(self):
        assert film.line_call(self.attack(8.8, 1)) == {"t": 10.5, "x": 8.8, "y": 1.0, "in": True, "wrongCall": False, "line": "end"}
        assert film.line_call(self.attack(9.3, 2))["in"] is False
        # Touching the line is in.
        assert film.line_call(self.attack(9.08, 1))["in"] is True

    def test_leaves_out_far_landings_and_a_measure_saying_otherwise(self):
        assert film.line_call(self.attack(5.0, 1)) is None
        assert film.line_call(self.attack(9.3, 1)) is None

    def test_a_wrong_call_shows_as_the_point_really_went(self):
        call = film.line_call(self.attack(9.92, 1, wrongCall=True))
        assert (call["in"], call["wrongCall"], call["line"]) == (False, True, "end")
        assert film.line_call(self.attack(7.0, 1, wrongCall=True))["line"] is None

    def test_follows_its_clip_slowed_when_the_bounce_is_in_it(self, tmp_path):
        page = TestPlan.page()
        page["contacts"][1].update(x=-2.0, y=0.0)
        page["contacts"][2].update(x=8.8, y=1.0, g=2)
        shots = film.plan(called(page), tmp_path)["Élodie"]["shots"]
        kinds = [s["kind"] for s in shots]
        call = shots[kinds.index("call")]
        assert kinds[kinds.index("call") - 1] == "live" and call["from"] == 21.0 - film.CALL_BEFORE_S and call["speed"] == film.CALL_SPEED


class TestHighlights:
    @staticmethod
    def page():
        people = {str(p): {"team": 1 + p % 2, "number": p, "name": f"P{p}", "jersey": p} for p in range(1, 7)}
        rallies, contacts = [], []
        scores = [0, 0]
        for k in range(30):
            number = 1 if k < 15 else 2
            if k == 15:
                scores = [0, 0]
            person = 1 + k % 6
            team = winner = 1 + person % 2
            scores[winner - 1] += 1
            count = 12 if k == 7 else 1
            touches = []
            for n in range(count):
                touches.append({"i": len(contacts), "t": 100.0 * k + n, "f": (100 * k + n) * 50, "type": "set" if n < count - 1 else "attack", "person": person, "g": team, "team": team, "result": "point" if n == count - 1 and team == winner else "play", "rally": k})
                contacts.append(touches[-1])
            rallies.append({"i": k, "contacts": touches, "score": list(scores), "winner": winner, "set": number, "start": 100.0 * k - 1, "end": 100.0 * k + count})
        return {"rallies": rallies, "contacts": contacts, "people": people, "teams": [{"name": "A"}, {"name": "B"}], "scores": ["8-7", "8-7"], "positions": {"step": 5}, "date": "2026-10-29"}

    def test_keeps_the_longest_rally_and_the_match_point_in_match_order_within_its_length(self, tmp_path):
        film_ = film.highlight_film(self.page(), tmp_path, "")
        lives = [s for s in film_["shots"] if s["kind"] == "live" and not s.get("hook")]

        assert 7 in [s["rally"] for s in lives] and lives[-1]["rally"] == 29
        assert [s["rally"] for s in lives] == sorted(s["rally"] for s in lives)
        assert film_["length"] <= film.HIGHLIGHTS_S + 0.01
        assert sum(s["kind"] == "replay" for s in film_["shots"]) == film.HIGHLIGHTS_REPLAYS
        assert (film_["longest"], film_["won"]) == (12, [2, 0])

    def test_sets_without_a_given_score_take_their_last_rally(self, tmp_path):
        page = {**self.page(), "scores": [None, "8-7"]}
        film_ = film.highlight_film(page, tmp_path, "")

        assert film_["sets"] == [f"{a}-{b}" for a, b in [page["rallies"][14]["score"], (8, 7)]]

    def test_shows_every_set_both_teams_and_each_touch_s_own_player(self, tmp_path):
        film_ = film.highlight_film(self.page(), tmp_path, "")
        lives = [s for s in film_["shots"] if s["kind"] == "live"]

        assert {film_["rallies"][str(s["rally"])]["set"] for s in lives} == {1, 2}
        assert {s["who"]["team"] for s in lives} == {1, 2}
        assert all(s["who"]["name"] == f"P{TestHighlights.page()['contacts'][s['contact']]['person']}" for s in lives)

    def test_names_no_one_for_a_fault(self):
        winner_touch = contact(0, 10.0, "set", 1)
        fault = contact(1, 11.0, "attack", 1, result="error")
        people = {"1": {"name": "Ana"}}
        assert film.rally_touch(rally(0, [winner_touch, fault], [1, 0]), people) is winner_touch

    def test_is_a_single_film_in_16_9(self, tmp_path):
        films = film.plan(self.page(), tmp_path)
        assert [n for n in films if n.startswith(film.HIGHLIGHTS)] == [film.HIGHLIGHTS]
        assert films[film.HIGHLIGHTS]["format"] == "wide"

    def test_a_too_short_match_has_no_film(self, tmp_path):
        assert film.highlight_film(TestPlan.page(), tmp_path, "") is None

    def test_the_longest_rally_cuts_to_its_exchanges_before_its_end(self):
        page = self.page()
        # Rally 7: attacks by P2 (team 1), each saved by a dig of P3 (team 2).
        for c in page["rallies"][7]["contacts"][:-1]:
            odd = (c["t"] - 700) % 2 == 1
            c.update(type="dig" if odd else "attack", person=3 if odd else 2, g=2 if odd else 1, team=2 if odd else 1)
        *beats, finish = [span for touch, span in film.highlight_moments(page) if touch["rally"] == 7 and not span.get("hook")]
        touches = [touch for touch, span in film.highlight_moments(page) if touch["rally"] == 7 and not span.get("hook")][:-1]

        assert 1 <= len(beats) <= film.BEATS and all(t["type"] == "dig" for t in touches)
        assert all(a["end"] <= b["start"] for a, b in zip(beats, [*beats[1:], finish]))
        assert all(b["end"] - b["start"] <= 1 + film.BEAT_BEFORE_S + film.BEAT_AFTER_S + 1e-6 for b in beats)

    def test_opens_on_a_point_before_its_title(self, tmp_path):
        page = self.page()
        film_ = film.highlight_film(page, tmp_path, "")
        hook, intro = film_["shots"][:2]

        assert hook["hook"] and hook["kind"] == "live" and intro["kind"] == "intro"
        assert page["contacts"][hook["contact"]]["result"] == "point" and hook["rally"] not in (7, 29)

    def test_takes_the_touches_picked_in_the_review(self, tmp_path):
        page = self.page()
        left = next(r for r in page["rallies"] if r["i"] not in {t["rally"] for t, _ in film.highlight_moments(page)})
        # The point of a rally left out, a frame off; a set of the longest rally, before its end.
        point, setter = left["contacts"][-1], page["rallies"][7]["contacts"][3]
        film.write_picks(tmp_path, {point["f"] + 3, setter["f"]})
        found = film.highlight_moments(page, film.read_picks(tmp_path))

        assert any(t is point for t, _ in found) and any(t is setter for t, _ in found)

    def test_other_clips_are_short(self):
        clips = [span for touch, span in film.highlight_moments(self.page()) if touch["rally"] != 7]
        assert all(span["end"] - span["start"] <= film.PUNCH_LEAD_S + film.PUNCH_END_S + film.AFTER_POINT_S for span in clips)


class TestServingBody:
    def test_keeps_the_named_player_behind_the_line(self):
        assert film.serving_body((-8.5, 1.0), {5: (-9.5, 2.0)}) is None

    def test_follows_the_teammate_behind_the_line_when_the_named_track_is_inside_the_court(self):
        assert film.serving_body((0.4, 1.0), {5: (-8.8, 2.1), 6: (-3.0, 0.0)}) == 5
        assert film.serving_body(None, {5: (8.8, 2.1)}) == 5

    def test_keeps_them_when_nobody_is_behind_the_line(self):
        assert film.serving_body((0.4, 1.0), {6: (-3.0, 0.0)}) is None


class TestBuild:
    def test_makes_only_the_kind_asked(self, tmp_path, monkeypatch):
        planned = {name: {"hash": name, "file": f"{name}.mp4"} for name in ("Élodie", film.HIGHLIGHTS)}
        monkeypatch.setattr(film, "read_page", lambda _: {"rallies": []})
        monkeypatch.setattr(film, "plan", lambda *_: planned)
        monkeypatch.setattr(film.jobs, "follow", lambda command, share: None)
        assert film.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", kind="highlights") == [film.HIGHLIGHTS]
        assert list(film.manifest(tmp_path)) == [film.HIGHLIGHTS]
        assert film.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", kind="players") == ["Élodie"]

    def test_makes_only_the_films_that_changed_and_keeps_those_made_when_one_fails(self, tmp_path, monkeypatch):
        page = TestPlan.page()
        page["people"]["2"].update(name="Other")
        page["contacts"] += [contact(3, 30.0, "serve", 2, 2, speed=40, rally=2), contact(4, 40.0, "attack", 2, 2, result="point", rally=3)]
        page["rallies"] += [rally(2, [page["contacts"][3]], [1, 2], 1), rally(3, [page["contacts"][4]], [1, 3], 2)]
        monkeypatch.setattr(film, "read_page", lambda _: page)
        asked = []

        told = []

        def run(command, share):
            asked.append(command[-2:])
            share(0.5)
            told.append(command[-2])
            if command[-2:] == ["--make", "Other"] and fail:
                raise subprocess.CalledProcessError(1, command)
            if command[-2] == "--make":
                (tmp_path / "films" / film.plan(page, tmp_path / "review", "")[command[-1]]["file"]).write_bytes(b"film")

        monkeypatch.setattr(film.jobs, "follow", run)
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


class TestCamera:
    def test_moves_ahead_of_a_ball_about_to_leave_the_picture(self):
        n = 200
        ball = np.r_[np.zeros(100), np.linspace(0, 1000, 100)]
        moved = film.keep_in_view(np.zeros(n), ball, np.full(n, 200.0), np.ones(n, bool))
        assert np.abs(ball - moved).max() < 230
        assert moved[:50].max() < 1

    def test_ignores_what_it_does_not_know_of_the_ball(self):
        n = 100
        moved = film.keep_in_view(np.zeros(n), np.full(n, 5000.0), np.full(n, 200.0), np.zeros(n, bool))
        assert np.abs(moved).max() == 0


class TestFrames:
    def test_holds_still_while_the_target_stays_within_the_slack(self):
        path = film.holds(np.array([0.0, 2.0, -2.0, 1.0, 20.0, 40.0]), 5.0)
        assert np.ptp(path[:4]) < 3
        assert path[-1] > 30
