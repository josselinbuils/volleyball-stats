import json
import os
from collections import Counter
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from volleyball_stats.identity import read_names
from volleyball_stats import files, presence, review as review_module, web
from volleyball_stats.teams import match_end
from volleyball_stats.review import answers_stamp, joins, teaches, reviewed, last_comparison, card_numbers, hosted_state, APPLIED, Questions, aces, rotation_slips, checked, commented, corrections, read_comments, write_comments, eta, follow_teams, locked, pinned, unlocked, report_answer, superseded, unusual, report_question, reports, unnamed, chain, constraints, doubtful, rally_answer, meeting, path, name_merges, supersede, load_roster, mark_odd, range_of, reanchor, receiver_answer, remember, save, set_name, set_photo, set_team, settled, state, suggest, touch_answer, undo, waiting, with_review, write_names, list_page, match_list, reopening, set_end, set_start, let_go, piece_conflict, pooled_runs


class TestHostedState:
    today = date(2026, 11, 3)

    def test_behind_without_an_upload(self):
        assert hosted_state(None, "x", self.today) == {"at": None, "day": None, "error": None, "behind": True}

    def test_up_to_date_while_the_page_is_what_was_uploaded(self):
        state = hosted_state({"at": "2026-11-03T00:51:12", "stamp": "x"}, "x", self.today)

        assert (state["at"], state["day"], state["behind"]) == ("00:51", None, False)

    def test_behind_once_the_page_changed_and_says_another_day(self):
        state = hosted_state({"at": "2026-11-02T22:03:00", "stamp": "x"}, "y", self.today)

        assert (state["at"], state["day"], state["behind"]) == ("22:03", "2026-11-02", True)


class TestMatchList:
    @staticmethod
    def folder(out, name, date, finished=True):
        (out / name).mkdir(parents=True)
        video, court = out / f"{name}.mp4", out / f"{name}.json"
        video.touch()
        court.touch()
        files.write_source(out / name, video, court)
        (out / name / "teams.json").write_text(json.dumps({"date": date, "teams": [{"name": "A", "colour": None}, {"name": "B", "colour": None}], "scores": ["25-20", None]}))
        if finished:
            (out / name / "report.md").touch()

    def test_lists_the_matches_with_a_source_newest_first_and_which_are_finished(self, tmp_path):
        self.folder(tmp_path, "old", "2026-10-29")
        self.folder(tmp_path, "new", "2026-11-02", finished=False)
        (tmp_path / "bench").mkdir()

        listed = match_list(tmp_path)

        assert [(m["path"], m["ready"]) for m in listed] == [("new", False), ("old", True)]
        assert listed[0]["sets"] == 1 and listed[0]["rallies"] == 0

    def test_a_match_whose_video_is_gone_is_not_ready(self, tmp_path):
        self.folder(tmp_path, "m", "2026-10-29")
        (tmp_path / "m.mp4").unlink()

        assert not match_list(tmp_path)[0]["ready"]

    def test_opens_only_a_finished_match_of_the_list(self, tmp_path):
        self.folder(tmp_path, "done", "2026-10-29")
        self.folder(tmp_path, "running", "2026-11-02", finished=False)

        command = reopening("done", tmp_path, "aspom", 8765, tmp_path / "roster.json")

        assert str(tmp_path / "done") in command and "--no-browser" in command and "--with-window" not in command
        for name in ("running", "nothing", "../done"):
            with pytest.raises(LookupError):
                reopening(name, tmp_path, "aspom", 8765, tmp_path / "roster.json")

    def test_keeps_closing_with_its_window_on_another_match(self, tmp_path, monkeypatch):
        self.folder(tmp_path, "done", "2026-10-29")
        monkeypatch.setattr(presence, "ON", True)
        assert "--with-window" in reopening("done", tmp_path, "aspom", 8765, tmp_path / "roster.json")

    def test_the_page_lists_them_for_the_review_and_serves_only_its_own_files(self, tmp_path):
        self.folder(tmp_path, "m", "2026-10-29")

        html, kind = list_page("/matches/", tmp_path, "none")

        assert b"matches.js" in html and kind.startswith("text/html")
        body, _ = list_page("/matches/matches.js", tmp_path, "none")
        assert b'"review": true' in body and b'"path": "m"' in body
        assert list_page("/matches/../../secret", tmp_path, "none") is None
        assert list_page("/matches/nothing.js", tmp_path, "none") is None
        assert list_page("/matches/../secret/data.js", tmp_path, "none") is None
        assert list_page("/matches/m/data.js", tmp_path, "none") is None
        (tmp_path / "m" / "review").mkdir()
        (tmp_path / "m" / "review" / "data.js").write_text("window.MATCH = {};")
        assert list_page("/matches/m/data.js", tmp_path, "none")[0] == b"window.MATCH = {};"
        assert list_page("/matches/other/data.js", tmp_path, "none") is None

    def test_the_server_s_matches_come_apart_and_only_for_a_machine_keeping_its_matches_there(self, tmp_path, monkeypatch):
        out = tmp_path / "matches"
        self.folder(out, "m", "2026-10-29")
        reached = []
        monkeypatch.setattr("volleyball_stats.sync.listing", lambda outputs: reached.append(outputs) or {"m": {}, "2026-11-02-x": {}})

        list_page("/matches/", out, "none")
        assert json.loads(list_page("/matches/remote.json", out, "none")[0]) == []
        assert not reached
        (tmp_path / "server.json").write_text("{}")
        found = json.loads(list_page("/matches/remote.json", out, "none")[0])

        assert [(m["path"], m["date"], m["remote"]) for m in found] == [("2026-11-02-x", "2026-11-02", True)]


class TestRedirect:
    def sent(self, path):
        from urllib.parse import urlparse

        handler = SimpleNamespace(headers={}, send_response=lambda code: handler.headers.update(status=code), send_header=lambda k, v: handler.headers.update({k: v}), end_headers=lambda: None)
        return review_module.redirect(handler, urlparse(path)), handler.headers

    def test_each_page_answers_with_and_without_a_trailing_slash(self):
        assert self.sent("/matches?x=1") == (True, {"status": 302, "Location": "/matches/?x=1"})
        assert self.sent("/review/") == (True, {"status": 302, "Location": "/review"})
        assert self.sent("/page/") == (True, {"status": 302, "Location": "/page"})
        assert self.sent("/matches/")[0] is False
        assert self.sent("/review")[0] is False


class TestConstraints:
    piece = {"track": 7, "frame": 100}
    three, five = {"track": 1, "frame": 10}, {"track": 2, "frame": 20}
    refs = {"piece": piece, "choices": [three, five]}

    def test_a_choice_joins_the_piece_to_it_and_parts_it_from_the_other(self):
        assert constraints("1", self.refs) == {"same": [[self.piece, self.five]], "different": [[self.piece, self.three]]}

    def test_someone_else_parts_the_piece_from_every_choice(self):
        assert constraints("other", self.refs) == {"different": [[self.piece, self.three, self.five]]}

    def test_not_a_player_and_dont_know(self):
        assert constraints("not_player", self.refs) == {"not_player": [self.piece]}
        assert constraints("skip", self.refs) == {}

    def test_a_cut_ends_the_piece_before_and_parts_the_two_sides(self):
        before, after = {"track": 7, "frame": 140}, {"track": 7, "frame": 142}

        assert constraints("cut", self.refs, cut=(before, after)) == {"cut": [before], "different": [[before, after]]}

    def test_two_identities_are_one_player_or_two(self):
        refs = {"choices": [self.three, self.five]}

        assert constraints("same", refs) == {"same": [[self.three, self.five]]}
        assert constraints("different", refs) == {"different": [[self.three, self.five]]}

    def test_a_player_said_by_name_joins_the_piece_to_them_first_and_parts_it_from_the_choices(self):
        paul = {"track": 9, "frame": 90}

        assert constraints("player:1:7", self.refs, paul) == {"same": [[paul, self.piece]], "different": [[self.piece, self.three, self.five]]}
        assert constraints("player:1:3", self.refs, self.three) == {"same": [[self.three, self.piece]], "different": [[self.piece, self.five]]}


class TestDoubtful:
    def test_asks_unknown_touchers_then_one_player_twice_then_close_calls(self):
        def row(frame, kind, team, who, gap=""):
            return {"frame": str(frame), "type": kind, "team": str(team), "identity": str(who), "gap": gap}

        actions = [
            row(10, "serve", 1, 3, "0.5"),
            row(40, "pass", 2, ""),
            row(60, "set", 2, 4, "0.3"),
            # The set's player again: the attack, less sure, is asked.
            row(80, "attack", 2, 4, "0.01"),
            # A blocker may play the ball again.
            row(100, "block", 1, 5, "0.2"),
            row(110, "dig", 1, 5, "0.04"),
            row(130, "floor", "", ""),
            # Not twice: the next rally.
            row(200, "serve", 1, 5, "0.03"),
            row(230, "pass", 2, 4, "0.02"),
        ]

        found = doubtful(actions, [(0, 150), (190, 300)])

        assert [(r["frame"], why) for r, why in found[:2]] == [("40", "unknown"), ("80", "twice")]
        # The touches not doubted, all spot-checked here.
        assert sorted(r["frame"] for r, why in found[2:5]) == ["10", "100", "60"] and {why for _, why in found[2:5]} == {"check"}
        assert [(r["frame"], why) for r, why in found[5:]] == [("230", "close"), ("200", "close"), ("110", "close")]


class TestRallyAnswer:
    def test_a_window_is_a_rally_or_no_play_else_nothing(self):
        assert rally_answer({"start": 900}, "rally") == {"rally": [{"start": 900, "play": True}]}
        assert rally_answer({"start": 900}, "not_play") == {"rally": [{"start": 900, "play": False}]}
        assert rally_answer({"start": 900}, "skip") == {}


class TestTouchAnswer:
    def test_a_touch_is_the_players_said_with_their_name_or_no_touch_else_nothing(self):
        touch = {"frame": 98776, "team": 2}

        assert touch_answer(touch, "player:2:5", {(2, 5): {"name": "Léa", "jersey": 9}}) == {"touch": [{"frame": 98776, "team": 2, "identity": 5, "name": "Léa"}]}
        assert touch_answer(touch, "player:2:6", {}) == {"touch": [{"frame": 98776, "team": 2, "identity": 6, "name": None}]}
        # A player of the other team: the touch is theirs.
        assert touch_answer(touch, "player:1:4", {}) == {"touch": [{"frame": 98776, "team": 1, "identity": 4, "name": None}]}
        assert touch_answer(touch, "nobody", {}) == {"touch": [{"frame": 98776, "team": 2, "identity": None, "name": None}]}
        assert touch_answer(touch, "not_play", {}) == {"touch": [{"frame": 98776, "team": 2, "identity": None, "name": None, "play": False}]}
        assert touch_answer(touch, "skip", {}) == {}



class TestReports:
    page = {
        "rallies": [{"start": 10.0, "end": 20.0, "set": 1, "winner": 1}, {"start": 40.0, "end": 50.0, "set": 1, "winner": 2}],
        "people": {"0": {"team": 1, "number": 3}, "1": {"team": 2, "number": None}},
        "contacts": [
            {"t": 41.0, "type": "serve", "team": 2, "person": 1, "rally": 1, "result": "play"},
            {"t": 42.0, "type": "pass", "team": 1, "person": 0, "rally": 1, "result": "error"},
            {"t": 42.5, "type": "floor", "team": 1, "person": None, "rally": 1, "result": "play"},
        ],
    }

    def test_reads_this_match_s_reports_once_from_the_fetched_logs(self, tmp_path):
        line = lambda r: json.dumps({"received": "t", "report": json.dumps(r)})  # noqa: E731
        mine, other = {"match": "m", "time": 41.0, "kind": "player", "comment": ""}, {"match": "x", "time": 5.0, "kind": "other"}
        (tmp_path / "feedback").mkdir()
        (tmp_path / "feedback" / "feedback.log").write_text(line(mine) + "\n" + line(other) + "\n")
        (tmp_path / "feedback" / "feedback-copy.log").write_text(line(mine) + "\n")
        (tmp_path / "matches" / "m").mkdir(parents=True)

        found = reports(tmp_path / "matches" / "m")

        assert [(r["time"], len(r["key"])) for r in found] == [(41.0, 12)]

    def test_a_report_asks_about_its_rally_s_touches_by_the_touch_replayed_or_its_time(self):
        question, ref = report_question({"time": 52.0, "clip": None, "kind": "result", "shown": "x", "comment": "Pas de faute"}, self.page, 50.0)

        assert (question["clip"]["start"], question["winner"], question["reports"][0]["comment"]) == (40.0, 2, "Pas de faute")
        assert [(t["frame"], t["type"], t["player"]) for t in question["touches"]] == [(2050, "serve", None), (2100, "pass", "1:3")]
        assert ref == {"start": 2000, "touches": {"2050": 2, "2100": 1}} and question["rally"] == 2000
        assert report_question({"time": 100.0, "clip": {"time": 12.0}}, self.page, 50.0)[1]["start"] == 500

    def test_a_moment_in_a_rally_is_about_it_rather_than_the_one_just_before(self):
        page = {**self.page, "rallies": [{"start": 10.0, "end": 36.0, "set": 1, "winner": 1}, *self.page["rallies"][1:]]}

        assert report_question({"time": 40.0}, page, 50.0)[1]["start"] == 2000

    def test_flags_the_rallies_that_do_not_look_like_one(self):
        def c(t, kind, team, rally):
            return {"t": t, "type": kind, "team": team, "side": "left" if team == 1 else "right", "rally": rally}

        page = {
            "teams": [{}, {}],
            "rallies": [{"start": float(k), "end": k + 0.5, "set": 1, "winner": w} for k, w in enumerate([1, 1, 2, 2, None, 1, 1, 1])],
            "scores": ["5-3"],
            "contacts": [
                c(0.1, "serve", 1, 0),  # fine
                c(1.1, "pass", 2, 1),  # no serve
                c(2.1, "serve", 2, 2),  # served by the loser of the point before
                c(2.2, "serve", 2, 2),
                c(3.0, "serve", 2, 3),
                *[c(3.1 + n / 10, kind, 1, 3) for n, kind in enumerate(["pass", "set", "attack"])],
                c(3.5, "block", 2, 3),
                *[c(3.6 + n / 100, kind, 2, 3) for n, kind in enumerate(["dig", "set", "attack", "relance"])],
                c(4.1, "floor", None, 4),  # no touch, no winner
                {**c(5.1, "serve", 2, 5), "result": "error"},  # a touch after a fault
                c(5.2, "pass", 1, 5),
                {**c(7.0, "serve", 1, 7), "result": "point"},  # a touch after a point
                c(7.2, "pass", 2, 7),
                c(6.0, "serve", 1, 6),
                {**c(6.1, "pass", 2, 6), "person": 4},  # the same player twice
                {**c(6.2, "set", 2, 6), "person": 4},
            ],
        }

        found = unusual(page)

        assert [(r["time"], r["kind"]) for r in found] == [
            (1.0, "auto.noServe"),
            (1.0, "auto.passWithoutServe"),
            (2.0, "auto.twoServes"),
            (2.0, "auto.serveNotReceived"),
            (2.0, "auto.server"),
            (3.0, "auto.fourTouches"),
            (4.0, "auto.empty"),
            (4.5, "auto.noWinner"),
            (5.0, "auto.afterFault"),
            (6.0, "auto.samePlayer"),
            (7.0, "auto.afterPoint"),
        ]
        assert found[0]["key"] == unusual(page)[0]["key"]
        # The set's last rally ends off the final score given; its report comes back once the score moves.
        page["rallies"][-1]["score"] = [5, 2]
        off = [r for r in unusual(page) if r["kind"] == "auto.scoreOff"]
        assert [r["time"] for r in off] == [7.5]
        page["rallies"][-1]["score"] = [4, 3]
        assert [r["key"] for r in unusual(page) if r["kind"] == "auto.scoreOff"] != [off[0]["key"]]
        page["rallies"][-1]["score"] = [5, 3]
        assert not [r for r in unusual(page) if r["kind"] == "auto.scoreOff"]

    def test_a_playing_fault_is_no_touch_of_the_ball_and_ends_the_rally(self):
        def c(t, kind, team, result="play"):
            return {"t": t, "type": kind, "team": team, "side": "left" if team == 1 else "right", "rally": 0, "result": result}

        # The receivers' rotation fault at the serve: no reception missing; then a touch after it.
        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 5.0, "set": 1, "winner": 1}], "contacts": [c(0.1, "serve", 1), c(0.2, "fault", 2, "error")]}
        assert unusual(page) == []
        page["contacts"].append(c(1.0, "pass", 2))
        assert [r["kind"] for r in unusual(page)] == ["auto.afterFault"]

    def test_an_attack_played_low_or_a_relance_high_is_a_doubt_on_its_touch(self):
        def c(t, kind, team):
            return {"t": t, "type": kind, "team": team, "side": "left" if team == 1 else "right", "rally": 0, "result": "play"}

        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 5.0, "set": 1, "winner": 1}], "contacts": [c(0.1, "serve", 1), c(1.0, "pass", 2), c(1.8, "set", 2), c(2.6, "attack", 2), c(3.4, "relance", 1)]}
        # index, x, y, height: the attack at 1.5 m, the first-touch relance (asked as such) high, a floor-level place no height.
        places = [3, 0, 0, 1.5, 4, 0, 0, 2.9]
        found = [r for r in unusual(page, places) if r["kind"] in ("auto.lowAttack", "auto.highRelance")]
        assert [(r["kind"], r["at"], r["time"]) for r in found] == [("auto.lowAttack", [2.6], 0.0)]
        assert not [r for r in unusual(page, [3, 0, 0, 0.11]) if r["kind"] == "auto.lowAttack"]
        page["ball3d"] = [3, 0, 0, 2.7]
        assert not [r for r in unusual(page, places) if r["kind"] == "auto.lowAttack"]

    def test_a_relance_as_first_touch_is_reported(self):
        def c(t, kind, team):
            return {"t": t, "type": kind, "team": team, "side": "left" if team == 1 else "right", "rally": 0, "result": "play"}

        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 5.0, "set": 1, "winner": 1}], "contacts": [c(0.1, "serve", 1), c(1.0, "pass", 2), c(1.8, "set", 2), c(2.6, "relance", 2)]}
        assert unusual(page) == []
        page["contacts"].append(c(3.5, "relance", 1))
        assert [r["kind"] for r in unusual(page)] == ["auto.relanceFirst"]
        page["contacts"][2]["type"] = "relance"
        assert [r["kind"] for r in unusual(page)] == ["auto.relanceSecond", "auto.relanceFirst"]

    def test_the_server_is_not_checked_after_a_point_the_referee_got_wrong(self):
        def serve(rally, team):
            return {"t": float(rally), "type": "serve", "team": team, "side": "left" if team == 1 else "right", "rally": rally, "result": "error"}

        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 1.0, "set": 1, "winner": 2, "wrongCall": True}, {"start": 2.0, "end": 3.0, "set": 1, "winner": 2}], "contacts": [serve(0, 2), serve(1, 1)]}
        assert "auto.server" not in [r["kind"] for r in unusual(page)]
        del page["rallies"][0]["wrongCall"]
        assert "auto.server" in [r["kind"] for r in unusual(page)]

    def test_a_report_question_says_when_the_report_came(self):
        page = {"rallies": [{"key": 50, "start": 1.0, "end": 5.0, "set": 1, "winner": 1}], "contacts": []}
        question, _ = report_question({"time": 2.0, "kind": "flag", "received": "2026-11-01T12:21:00+00:00"}, page, 50.0)
        assert question["reports"][0]["received"] == "2026-11-01T12:21:00+00:00"

    def test_a_long_pause_between_two_touches_is_reported(self):
        def touch(t, kind):
            return {"t": t, "type": kind, "team": 1, "side": "left", "rally": 0, "result": "play"}

        page = {"rallies": [{"start": 0.0, "end": 9.0, "set": 1}], "contacts": [touch(0.0, "serve"), {**touch(1.0, "pass"), "team": 2}, {**touch(3.5, "set"), "team": 2}]}
        assert unusual(page) == []
        page["contacts"][-1]["t"] = 3.6
        assert [r["kind"] for r in unusual(page)] == ["auto.gap"]

    def test_two_named_players_of_a_team_with_one_jersey_are_reported_once(self):
        people = {"1": {"team": 1, "jersey": 10, "name": "Ana"}, "2": {"team": 1, "jersey": 10, "name": "Zoé"}, "3": {"team": 2, "jersey": 10, "name": "Léa"}, "4": {"team": 1, "jersey": 7, "name": "Ana"}}
        rallies = [{"start": 0.0, "end": 1.0, "set": 1}, {"start": 2.0, "end": 3.0, "set": 1}]
        contact = {"t": 2.1, "type": "serve", "team": 1, "side": "left", "rally": 1, "result": "error", "person": 2}
        found = unusual({"people": people, "rallies": rallies, "contacts": [contact]})
        assert [(r["kind"], r["time"], r["shown"]) for r in found if r["kind"] == "auto.sameJersey"] == [("auto.sameJersey", 2.0, "10 · Ana, Zoé")]
        # One player under two tracking numbers wears one jersey.
        people["2"]["name"] = "Ana"
        assert not [r for r in unusual({"people": people, "rallies": rallies, "contacts": [contact]}) if r["kind"] == "auto.sameJersey"]

    def test_a_server_out_of_their_teams_order_is_found(self):
        def page(*serves):
            rallies = [{"start": float(k), "end": k + 0.5, "set": set_} for k, (set_, _, _) in enumerate(serves)]
            contacts = [{"t": float(k), "type": "serve", "team": team, "rally": k, "person": person} for k, (_, team, person) in enumerate(serves)]
            return {"rallies": rallies, "contacts": contacts, "people": {}}

        # The other team's servers keep to their own order.
        turn = lambda *servers: [x for k, s in enumerate(servers) for x in ((1, 1, s), (1, 2, 90 + k % 6))]  # noqa: E731
        # Six turns apart is the order; five is not.
        assert rotation_slips(page(*turn(1, 2, 3, 4, 5, 6, 1))) == set()
        assert rotation_slips(page(*turn(1, 2, 3, 4, 5, 1))) == {10}
        # A team keeping the serve keeps its server; a new set starts again.
        assert rotation_slips(page((1, 1, 1), (1, 1, 1), (1, 1, 2))) == {2}
        assert rotation_slips(page((1, 1, 1), (2, 1, 1))) == set()

    def test_a_rally_to_replay_is_not_reported_for_having_no_winner(self):
        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 5.0, "set": 1, "winner": None, "redo": True}], "contacts": [{"t": 0.1, "type": "serve", "team": 1, "side": "left", "rally": 0, "result": "play"}, {"t": 1.0, "type": "pass", "team": 2, "side": "right", "rally": 0, "result": "play"}]}
        assert unusual(page) == []
        del page["rallies"][0]["redo"]
        assert [r["kind"] for r in unusual(page)] == ["auto.noWinner"]

    # Two rallies: 2000-2200 and 3000-3200; touches at 2050 (team 2), 2100 and 3050 (team 1).
    teams, windows = {2050: 2, 2100: 1, 3050: 1}, [(2000, 2200), (3000, 3200)]

    def test_corrections_anywhere_become_touch_action_rally_winner_end_and_join_answers(self):
        changes = {
            "touches": [{"frame": 2050, "player": "none"}, {"frame": 3050, "player": "1:4", "result": "play", "type": "bogus"}, {"frame": 9999, "player": "1:4"}],
            "rallies": [{"start": 2000, "winner": 1, "play": False, "join": True}, {"start": 3000, "end": 3400}, {"start": 1234, "winner": 2}],
        }

        out = report_answer(changes, self.teams, self.windows, {(1, 4): {"name": "Léa"}}, 20)

        assert out["touch"] == [{"frame": 2050, "team": 2, "identity": None, "name": None}, {"frame": 3050, "team": 1, "identity": 4, "name": "Léa"}]
        assert out["action"] == [{"frame": 3050, "result": "play"}]
        assert (out["rally"], out["winner"], out["end"]) == ([{"start": 2000, "play": False}], [{"start": 2000, "winner": 1}], [{"start": 3000, "end": 3400}])
        assert out["join"] == [{"start": 2000}]

    def test_a_fault_s_cause_becomes_an_action_answer_alone_or_beside_the_result(self):
        changes = {
            "touches": [{"frame": 2100, "cause": 2050}, {"frame": 3050, "result": "error", "cause": 0}, {"frame": 2050, "cause": "x"}],
            "added": [{"frame": 2150, "team": 1, "type": "attack", "result": "error", "cause": 2100}],
        }

        out = report_answer(changes, self.teams, self.windows, {}, 20)

        assert out["action"] == [
            {"frame": 2150, "result": "error", "cause": 2100}, {"frame": 2100, "cause": 2050}, {"frame": 3050, "result": "error", "cause": None}, {"frame": 2050, "cause": None},
        ]

    def test_the_referee_s_error_or_no_longer_becomes_a_referee_answer_beside_the_winner(self):
        changes = {"rallies": [{"start": 2000, "winner": 2, "wrong": True}, {"start": 3000, "wrong": False}]}

        out = report_answer(changes, self.teams, self.windows, {}, 20)

        assert out["referee"] == [{"start": 2000, "wrong": True}, {"start": 3000, "wrong": False}]
        assert out["winner"] == [{"start": 2000, "winner": 2}]

    def test_a_rally_s_end_counts_from_where_it_starts_not_from_its_key(self):
        changes = {"rallies": [{"start": 3100, "end": 3050}]}

        # Named 3100, started by a serve added at 3000.
        assert report_answer(changes, self.teams, self.windows, {}, 20, [2000, 3100])["end"] == [{"start": 3100, "end": 3050}]
        assert "end" not in report_answer({"rallies": [{"start": 3100, "end": 2900}]}, self.teams, self.windows, {}, 20, [2000, 3100])

    def test_a_rally_to_replay_or_no_longer_becomes_a_redo_answer(self):
        changes = {"rallies": [{"start": 2000, "redo": True}, {"start": 3000, "redo": False}, {"start": 1234, "redo": True}]}

        out = report_answer(changes, self.teams, self.windows, {}, 20)

        assert out["redo"] == [{"start": 2000, "redo": True}, {"start": 3000, "redo": False}]

    def test_a_rally_started_by_the_review_takes_the_touches_added_after_it(self):
        changes = {
            "splits": [2600, 3100],
            "added": [{"frame": 2600, "team": 2, "type": "serve"}, {"frame": 2650, "team": 1, "type": "pass"}, {"frame": 3150, "team": 1, "type": "dig"}],
            "rallies": [{"start": 2600, "winner": 1}, {"start": 3100, "join": True}],
        }

        out = report_answer(changes, self.teams, self.windows, {}, 20, [2000, 3010])

        assert out["split"] == [{"frame": 2600}, {"frame": 3100}]
        assert [(a["start"], a["frame"]) for a in out["added"]] == [(2600, 2600), (2600, 2650), (3100, 3150)]
        assert (out["winner"], out["join"]) == ([{"start": 2600, "winner": 1}], [{"start": 3100}])

    def test_the_winners_of_the_rallies_checked_are_pinned_as_the_page_shows_them(self):
        page = {"rallies": [{"key": 2000, "winner": 1}, {"key": 3000, "winner": None}, {"key": 4000, "winner": 2}]}

        assert pinned(page, [2000, 3000]) == [{"id": "pin", "choice": "pinned", "pinned": [{"start": 2000, "winner": 1}], "applied": True}]
        assert pinned(page, [3000]) == []

    def test_a_rally_checked_is_locked_as_the_page_shows_it(self):
        page = {
            "fps": 50,
            "rallies": [{"key": 2000}, {"key": 3000}],
            "people": {"7": {"team": 1, "number": 4}, "8": {"team": 2, "number": None}},
            "contacts": [
                {"rally": 0, "f": 2010, "t": 40.2, "type": "serve", "team": 1, "result": "play", "person": 7},
                {"rally": 0, "f": 2050, "t": 41.0, "type": "pass", "team": 2, "result": "error", "person": 8},
                {"rally": 0, "f": 2060, "t": 41.2, "type": "floor", "team": None, "result": "play", "person": None},
                {"rally": 1, "f": 3010, "t": 60.2, "type": "serve", "team": 2, "result": "point", "person": None},
            ],
        }

        [entry] = locked(page, [2000], {(1, 4): {"name": "Léa"}})

        assert entry["locked"] == [{"start": 2000, "touches": [{"frame": 2010, "team": 1, "type": "serve"}, {"frame": 2050, "team": 2, "type": "pass"}]}]
        assert entry["action"] == [{"frame": 2010, "type": "serve", "result": "play"}, {"frame": 2050, "type": "pass", "result": "error"}]
        # Only a named player is kept: none was shown for the pass.
        assert entry["touch"] == [{"frame": 2010, "team": 1, "identity": 4, "name": "Léa"}]
        assert locked(page, [], {}) == []
        assert unlocked([2000])[0]["locked"] == [{"start": 2000, "touches": None}]

    def test_the_time_left_counts_the_stages_and_steps_still_to_run(self):
        took = {"training": 100.0, "pipeline": 900.0, "pipeline:actions": 300.0, "pipeline:wrists": 400.0, "pipeline:teams": 500.0, "review": 10.0}
        run = {"steps": ["training", "pipeline", "review"], "done": 1, "started": 0.0, "since": 100.0, "stage": "wrists", "stage_since": 500.0}

        # 100 s of the wrists' 400 spent; the teams and the review to come; no tracking, the other stages unknown.
        assert eta(run, took, 600.0) == {"steps": run["steps"], "done": 1, "stage": "wrists", "elapsed": 600.0, "left": 300.0 + 500.0 + 10.0, "late": False, "part": 0.25}
        late = eta(run, took, 1000.0)
        assert (late["left"], late["late"]) == (510.0, True)
        # Before its first stage, a step counts as a whole.
        assert eta({**run, "stage": None, "done": 0, "since": 0.0}, took, 40.0)["left"] == 60.0 + 900.0 + 10.0

    def test_a_correction_a_frame_off_names_the_touch_there(self):
        out = report_answer({"touches": [{"frame": 2101, "type": "dig"}]}, self.teams, self.windows, {}, 20)

        assert out["action"] == [{"frame": 2100, "type": "dig"}]

    def test_a_touch_added_goes_to_the_rally_it_falls_in_else_a_serve_to_the_next_another_to_the_one_before(self):
        changes = {
            "added": [
                {"frame": 2075, "team": 1, "type": "pass", "result": "error", "player": "1:4"},
                {"frame": 2500, "team": 2, "type": "dig"},
                {"frame": 2600, "team": 2, "type": "serve"},
                {"frame": 2650, "team": 1, "type": "pass"},
                {"frame": 2050, "team": 1, "type": "pass"},
                {"frame": 2080, "team": 1, "type": "bogus"},
                {"frame": 1000, "team": 1, "type": "pass"},
            ]
        }

        # The second rally named by its key: its start moved back to a serve added before.
        out = report_answer(changes, self.teams, self.windows, {(1, 4): {"name": "Léa"}}, 20, [2000, 3010])

        assert out == {
            "added": [
                {"start": 2000, "frame": 2075, "team": 1, "type": "pass"},
                {"start": 2000, "frame": 2500, "team": 2, "type": "dig"},
                {"start": 3010, "frame": 2600, "team": 2, "type": "serve"},
                # After a serve added before a rally: in that rally.
                {"start": 3010, "frame": 2650, "team": 1, "type": "pass"},
                {"start": 2000, "frame": 1000, "team": 1, "type": "pass"},
            ],
            "action": [{"frame": 2075, "result": "error"}],
            "touch": [{"frame": 2075, "team": 1, "identity": 4, "name": "Léa"}],
        }


class TestUnnamed:
    def test_asks_each_touch_the_page_credits_to_no_named_player_of_its_team(self, tmp_path):
        data = {
            "people": {"0": {"team": 1, "number": 3}, "1": {"team": 2, "number": None}, "2": {"team": 2, "number": 5}},
            "contacts": [
                {"t": 1.0, "type": "pass", "team": 1, "person": 0},
                {"t": 2.0, "type": "pass", "team": 1, "person": None, "brief": True},
                {"t": 3.0, "type": "set", "team": 2, "person": 1},
                {"t": 4.0, "type": "dig", "team": 1, "person": 2},
                {"t": 5.0, "type": "floor", "team": 1, "person": None},
            ],
        }
        (tmp_path / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        assert unnamed(tmp_path, 50.0) == {100: "brief", 150: "unknown", 200: "unknown"}
        assert unnamed(tmp_path / "none", 50.0) == {}

    def test_doubtful_asks_them_with_their_reason(self):
        actions = [{"frame": "100", "type": "pass", "team": "1", "identity": "3", "gap": ""}]

        assert [(r["frame"], why) for r, why in doubtful(actions, [(0, 200)], {100: "brief"})][:1] == [("100", "brief")]


class TestAces:
    def test_asks_the_pages_aces_no_touch_follows_with_their_landing_and_rally(self):
        c = lambda f, kind, team, rally, result="play": {"f": f, "t": f / 10, "type": kind, "team": team, "rally": rally, "result": result}  # noqa: E731
        contacts = [c(10, "serve", 1, 0, "point"), c(30, "floor", 2, 0), c(100, "serve", 2, 1), c(200, "serve", 1, 2, "point"), c(210, "net", 1, 2), c(220, "pass", 2, 2, "error"), c(300, "serve", 2, 3, "point")]
        page = {"fps": 10, "contacts": contacts, "rallies": [{"key": 5}, {"key": 95}, {"key": 195}, {"key": 295}]}

        # The reception after the net touched the second ace: its own fault, no receiver to ask.
        assert aces(page) == [({"frame": 10, "team": 1}, {"frame": 30, "team": 2}, 5), ({"frame": 300, "team": 2}, None, 295)]
        assert aces(None) == []

    def test_the_receiver_is_the_players_said_or_no_one(self):
        ace = {"frame": 500, "team": 1}

        assert receiver_answer(ace, "player:1:3", {(1, 3): {"name": "Léa"}}) == {"receiver": [{"frame": 500, "team": 1, "identity": 3, "name": "Léa"}]}
        # A player of the other team than the one guessed: theirs is kept.
        assert receiver_answer(ace, "player:2:4", {(2, 4): {"name": "Tom"}}) == {"receiver": [{"frame": 500, "team": 2, "identity": 4, "name": "Tom"}]}
        assert receiver_answer(ace, "nobody", {}) == {"receiver": [{"frame": 500, "team": 1, "identity": None, "name": None}]}
        assert receiver_answer(ace, "not_play", {}) == {}
        assert receiver_answer(ace, "not_play", {}, 480) == {"rally": [{"start": 480, "play": False}]}
        assert receiver_answer(ace, "skip", {}) == {}


class TestComments:
    page = {"fps": 10, "rallies": [{"key": 100, "start": 10.0, "end": 20.0}, {"key": 400, "start": 40.0, "end": 60.0}]}

    def test_read_back_as_written(self, tmp_path):
        assert read_comments(tmp_path) == {}
        write_comments(tmp_path, {400: "à revoir", 100: "b"})
        assert read_comments(tmp_path) == {100: "b", 400: "à revoir"}

    def test_a_comment_on_a_rally_gone_goes_to_the_one_holding_its_start(self):
        comments = {100: "kept", 400: "first", 500: "joined to it", 900: "said no play"}
        assert commented(comments, self.page, []) == {100: "kept", 400: "first\njoined to it", 900: "said no play"}

    def test_a_comment_on_a_split_not_applied_yet_stays_its_own(self):
        assert commented({150: "second part"}, self.page, [{"split": [{"frame": 150}]}]) == {150: "second part"}

    def test_the_answers_leave_them_out(self, tmp_path):
        path = tmp_path / "identity_answers.json"
        write_comments(tmp_path, {100: "à revoir"})
        save(path, [])
        assert "à revoir" not in path.read_text()


class TestSave:
    def test_the_constraint_lists_follow_the_log(self, tmp_path):
        path = tmp_path / "identity_answers.json"
        log = [{"id": "a", "choice": "not_player", "not_player": [{"track": 1}]}, {"id": "b", "choice": "skip"}]

        save(path, log)

        assert json.loads(path.read_text()) == {"same": [], "different": [], "not_player": [{"track": 1}], "cut": [], "team": [], "touch": [], "rally": [], "receiver": [], "action": [], "winner": [], "added": [], "end": [], "join": [], "split": [], "pinned": [], "locked": [], "redo": [], "referee": [], "log": log}


class TestRange:
    def test_reads_byte_ranges_for_the_video_to_seek(self):
        assert range_of("bytes=0-99", 1000) == (0, 99)
        assert range_of("bytes=500-", 1000) == (500, 999)
        assert range_of("bytes=-100", 1000) == (900, 999)
        assert range_of("bytes=0-5000", 1000) == (0, 999)

    def test_has_no_range_without_a_header_or_past_the_end(self):
        assert range_of(None, 1000) is None
        assert range_of("bytes=2000-", 1000) is None


class TestNames:
    def test_names_an_identity_in_place_of_its_entries_and_unnames_it(self, tmp_path):
        questions = SimpleNamespace(table=[(1, 0, 10, 1, 3), (2, 0, 10, 1, 4)], ref=lambda team, number: {"track": 1 if number == 3 else 2, "frame": 5})

        set_name(tmp_path, questions, 1, 3, " Julie ", 7)
        set_name(tmp_path, questions, 1, 4, "Léa", None)
        set_name(tmp_path, questions, 1, 3, "Julia", None)

        assert read_names(tmp_path) == [{"ref": {"track": 1, "frame": 5}, "name": "Julia", "jersey": None}, {"ref": {"track": 2, "frame": 5}, "name": "Léa", "jersey": None}]
        set_name(tmp_path, questions, 1, 4, "", None)
        assert [e["name"] for e in read_names(tmp_path)] == ["Julia"]

    def test_keeps_another_persons_name_on_the_same_player(self, tmp_path):
        # Two applies joined Paul's and Jean's pieces: Paul's card, Jean's name kept for the conflict.
        questions = SimpleNamespace(table=[(1, 0, 10, 1, 5), (2, 0, 10, 1, 5)], ref=None)
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 5}, "name": "Paul", "jersey": None}, {"ref": {"track": 2, "frame": 5}, "name": "Jean", "jersey": 9}, {"ref": {"track": 1, "frame": 8}, "name": "Paul", "jersey": 4}])

        set_name(tmp_path, questions, 1, 5, "Paul", 7)

        assert [(e["name"], e["jersey"]) for e in read_names(tmp_path)] == [("Paul", 7), ("Jean", 9), ("Paul", None)]


class TestRoster:
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])

    def test_the_player_wearing_the_number_read_is_suggested_first(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": 7}, (1, 2): {"name": "Léa", "jersey": 25}}, {(1, 1): self.a, (1, 2): self.b}, ["ASPOM", None])
        roster = load_roster(path)
        assert [s["name"] for s in suggest(self.a, roster, "ASPOM")][0] == "Julie"
        assert [s["name"] for s in suggest(self.a, roster, "ASPOM", number=25)][0] == "Léa"

    def test_a_number_read_goes_to_the_player_with_most_of_its_readings(self):
        table = [(1, 0, 100, 1, 4), (2, 0, 100, 2, 6), (3, 0, 100, 1, 9), (4, 0, 100, 2, 0)]
        read = {(f, 1): 8 for f in range(25)} | {(f, 2): 8 for f in range(40)} | {(f, 3): 3 for f in range(10)} | {(f, 4): 5 for f in range(30)}
        # Each team's card holds its 8s; 1:9 has too few readings; a track without identity gives none.
        assert card_numbers(table, read) == {(1, 4): 8, (2, 6): 8}
        # Within a team, the card with most of them.
        assert card_numbers([(1, 0, 100, 2, 4), *table[1:]], read) == {(2, 6): 8}
        assert card_numbers(table, None) == {}

    def test_card_numbers_are_per_team_and_a_card_without_takes_its_pictures(self):
        table = [(1, 0, 100, 1, 1), (2, 0, 100, 2, 1), (3, 0, 100, 2, 2), (4, 0, 100, 2, 3), (5, 0, 100, 2, 4)]
        read = {(f, track): 38 for f in range(25) for track in (1, 2)}

        assert card_numbers(table, read) == {(1, 1): 38, (2, 1): 38}
        pictures = {(2, 2): Counter({7: 5, 30: 2}), (2, 3): Counter({38: 4}), (2, 4): Counter({9: 1})}
        assert card_numbers(table, read, pictures) == {(1, 1): 38, (2, 1): 38, (2, 2): 7}

    def named_match(self, outputs, name, teams, players):
        """A match folder whose `players` {(team, identity): name} each hold their own track."""
        folder = outputs / name
        folder.mkdir(parents=True)
        (folder / "teams.json").write_text(json.dumps({"teams": [{"name": t} for t in teams]}))
        rows = [f"{k},0,10,{team},{number}" for k, (team, number) in enumerate(players)]
        (folder / "identities.csv").write_text("\n".join(["track,start_frame,end_frame,team,identity", *rows]) + "\n")
        write_names(folder, [{"ref": {"track": k, "frame": 5}, "name": n, "jersey": None} for k, n in enumerate(players.values())])
        return folder

    def test_players_follow_their_team_s_new_name_however_it_changed(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": 7}, (2, 1): {"name": "Léa", "jersey": None}}, {(1, 1): self.a, (2, 1): self.b}, ["ASPOM 02", "AVIA"])
        remember(path, "m2", {(1, 1): {"name": "Julie", "jersey": None}}, {(1, 1): self.b}, ["ASPOM 02", "AVIA"])
        self.named_match(tmp_path, "m1", ["ASPOM 2", "AVIA"], {(1, 1): "Julie", (2, 1): "Léa"})
        follow_teams(path, tmp_path)
        found = {(p["team"], p["name"]): p for p in load_roster(path)}
        # m2's folder is gone: what it gave stays.
        assert sorted(found) == [("ASPOM 02", "Julie"), ("ASPOM 2", "Julie"), ("AVIA", "Léa")]
        assert list(found["ASPOM 2", "Julie"]["vectors"]) == ["m1"] and found["ASPOM 2", "Julie"]["jersey"] == 7
        # The rest of the team joins the player it now holds.
        self.named_match(tmp_path, "m2", ["ASPOM 2", "AVIA"], {(1, 1): "Julie"})
        follow_teams(path, tmp_path)
        found = {(p["team"], p["name"]): p for p in load_roster(path)}
        assert sorted(found) == [("ASPOM 2", "Julie"), ("AVIA", "Léa")]
        assert sorted(found["ASPOM 2", "Julie"]["vectors"]) == ["m1", "m2"]

    def test_a_name_in_both_teams_says_neither_and_a_roster_up_to_date_is_not_written(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": None}}, {(1, 1): self.a}, ["OLD", "AVIA"])
        self.named_match(tmp_path, "m1", ["NEW", "AVIA"], {(1, 1): "Julie", (2, 1): "Julie"})
        before = path.stat().st_mtime_ns
        follow_teams(path, tmp_path)
        assert [p["team"] for p in load_roster(path)] == ["OLD"] and path.stat().st_mtime_ns == before

    def test_remembers_the_named_players_and_suggests_those_who_look_most_alike(self, tmp_path):
        path = tmp_path / "roster.json"
        names = {(1, 1): {"name": "Julie", "jersey": 7}, (1, 2): {"name": "Léa", "jersey": None}, (2, 1): {"name": None, "jersey": 4}}

        remember(path, "m1", names, {(1, 1): self.a, (1, 2): self.b, (2, 1): self.a}, ["ASPOM", None])

        roster = load_roster(path)
        assert [(p["name"], p["team"], p["jersey"]) for p in roster] == [("Julie", "ASPOM", 7), ("Léa", "ASPOM", None)]
        assert [s["name"] for s in suggest(np.array([0.1, 0.9]), roster, "ASPOM")] == ["Léa", "Julie"]
        assert suggest(self.a, roster, "Other club") == []

    def test_a_match_applied_again_replaces_what_it_taught(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": 7}}, {(1, 1): self.a}, ["ASPOM", None])
        remember(path, "m2", {(1, 1): {"name": "Julie", "jersey": None}}, {(1, 1): self.b}, ["ASPOM", None])

        remember(path, "m1", {(1, 1): {"name": "Léa", "jersey": 3}}, {(1, 1): self.a}, ["ASPOM", None])

        assert [(p["name"], p["jersey"], list(p["vectors"])) for p in load_roster(path)] == [("Julie", 7, ["m2"]), ("Léa", 3, ["m1"])]

    def test_does_not_suggest_the_players_it_is_told_to_leave_out(self):
        roster = [{"name": "Julie", "team": "ASPOM", "vectors": {"m1": [1.0, 0.0]}}, {"name": "Léa", "team": "ASPOM", "vectors": {"m1": [0.0, 1.0]}}]

        assert [s["name"] for s in suggest(self.a, roster, "ASPOM", {"Julie"})] == ["Léa"]


class TestTogether:
    def test_names_the_named_players_of_the_team_on_court_during_more_than_a_share_of_the_card(self):
        questions = Questions.__new__(Questions)
        # Identity 1 on court 0-99; Paul 0-49, Jean 90-99, an unnamed player and Léa of the other team all along.
        questions.table = [(1, 0, 99, 1, 1), (2, 0, 49, 1, 2), (3, 90, 99, 1, 3), (4, 0, 99, 1, 4), (5, 0, 99, 2, 1)]
        names = {(1, 1): {"name": "Moi"}, (1, 2): {"name": "Paul"}, (1, 3): {"name": "Jean"}, (1, 4): {"name": None}, (2, 1): {"name": "Léa"}}

        assert questions.together(1, 1, names) == {"Paul"}


class TestWaiting:
    entry = {"id": "piece:1:0", "choice": "0", "same": [[{"track": 1, "frame": 5}, {"track": 2, "frame": 5}]], "applied": False}

    def test_counts_the_answers_saying_something_not_applied_yet(self, tmp_path):
        # Applied, saved before the flag (applied), not applied, and "I don't know".
        log = [{**self.entry, "applied": True}, {k: v for k, v in self.entry.items() if k != "applied"}, self.entry, {"id": "piece:3:0", "choice": "skip", "applied": False}]

        assert waiting(tmp_path, log)["pending"] == 1

    def test_tells_whether_the_answers_jersey_numbers_or_names_differ_from_what_the_identities_were_computed_from(self, tmp_path):
        log = [{**self.entry, "applied": True}]
        (tmp_path / APPLIED).write_text(json.dumps(state(tmp_path, log)))

        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": False, "corrections": {}, "films": {"players": {"total": 0, "stale": []}, "highlights": {"total": 0, "stale": []}}, "checked": [], "learned": False}
        assert waiting(tmp_path, [])["changed"]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 5}, "name": "Julie", "jersey": None}])
        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": True, "corrections": {}, "films": {"players": {"total": 0, "stale": []}, "highlights": {"total": 0, "stale": []}}, "checked": [], "learned": False}
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        assert waiting(tmp_path, log)["changed"]

    def test_a_timeout_given_since_the_last_apply_is_a_change(self, tmp_path):
        (tmp_path / APPLIED).write_text(json.dumps({k: v for k, v in state(tmp_path, []).items() if k != "timeouts"}))
        assert not waiting(tmp_path, [])["changed"]

        (tmp_path / "timeouts.json").write_text(json.dumps([{"start": 100, "end": 2000, "team": 1}]))
        assert waiting(tmp_path, [])["changed"]

    def test_learned_while_the_last_learning_run_saw_the_answers_as_they_stand(self, tmp_path):
        log = [{**self.entry, "applied": False}]
        assert not waiting(tmp_path, log)["learned"]

        (tmp_path / "learn.json").write_text(json.dumps([{"time": "2026-11-09 10:00", "answers": answers_stamp(log)}]))
        assert waiting(tmp_path, log)["learned"]
        # Applying changes nothing the run saw; another answer does.
        assert waiting(tmp_path, [{**self.entry, "applied": True}])["learned"]
        assert not waiting(tmp_path, log + [{"id": "piece:3:0", "choice": "skip"}])["learned"]

    def test_jersey_numbers_copied_through_the_server_to_the_second_are_no_change(self, tmp_path):
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        os.utime(tmp_path / "jerseys.csv", (1793733733.7316, 1793733733.7316))
        (tmp_path / APPLIED).write_text(json.dumps({**state(tmp_path, []), "jerseys": 1793733733.7316}))
        os.utime(tmp_path / "jerseys.csv", (1793733733.0, 1793733733.0))

        assert not waiting(tmp_path, [])["changed"]


class TestReportCorrections:
    def test_the_last_report_answer_since_the_page_was_built_carries_the_corrections_the_earlier_ones_emptied(self):
        shown = {"id": "report:a", "choice": "report", "touch": [{"frame": 1}], "changes": {"touches": [{"frame": 1}]}, "applied": False}
        before = {"id": "report:b", "choice": "report", "touch": [{"frame": 1}], "applied": False}
        later = {"id": "report:c", "choice": "report", "touch": [{"frame": 2}], "changes": {"touches": [{"frame": 2, "player": "none"}]}, "applied": False}
        log = [shown, before, later]

        out = superseded(log, {"report:a"})

        # In the page already, or saved before the answers kept their corrections: left as they are.
        assert out[:2] == [shown, before] and out[2] == {"id": "report:c", "choice": "report", "applied": False}
        assert log[2] is later and "touch" in later
        assert corrections(log, {"report:a"}) == {"touches": [{"frame": 2, "player": "none"}]}
        assert corrections(log, {"report:a", "report:c"}) == {}
        assert corrections(out, {"report:a"}) == {}


class TestChecked:
    def test_a_rally_stays_checked_until_unchecked_and_can_be_checked_again(self):
        log = [{"id": "edit:1", "checked": [100, 200]}, {"id": "edit:2", "unchecked": [100]}, {"id": "edit:3", "checked": [300]}]

        assert checked(log) == [200, 300]
        assert checked([*log, {"id": "edit:4", "checked": [100]}]) == [100, 200, 300]

    def test_a_match_is_reviewed_once_every_rally_is_checked(self):
        page = {"rallies": [{"key": 100}, {"key": 200}]}
        assert not reviewed(page, [{"id": "edit:1", "checked": [100]}])
        assert reviewed(page, [{"id": "edit:1", "checked": [100, 200, 300]}])
        assert not reviewed(None, [])

    def test_on_a_reviewed_match_only_a_piece_or_a_merge_that_may_mend_a_trained_touch_is_asked(self):
        # Player 2:5 touched at 100 with no track of theirs there, 2:9 being; 2:7 is twice at 300.
        lost, double = {100: ((2, 5), {(2, 9), (1, 3)})}, {300: (2, 7)}
        assert teaches(lost, double, 2, 50, 150, 5, 9)
        assert not teaches(lost, double, 2, 50, 150, 6, 9)
        assert not teaches(lost, double, 2, 150, 250, 5, 9)
        assert teaches(lost, double, 2, 250, 350, 8, 7)
        assert joins(lost, 2, 9, 5) and not joins(lost, 2, 9, 6)


class TestUndo:
    a, b = {"id": "piece:1:0", "same": [["x", "y"]], "applied": True}, {"id": "odd:1:0", "applied": False}

    def test_puts_back_the_answers_and_names_as_they_were_before_the_last_change(self):
        # A marking let go of a piece of an earlier answer and moved a name.
        names = [{"ref": {"track": 1, "frame": 5}, "name": "Julie"}]
        history = [{"log": [self.a], "names": names, "applied": False}]

        assert undo([{**self.a, "same": []}, self.b], history) == ([self.a], names, "odd:1:0", False)
        assert history == []

    def test_computes_the_identities_again_when_an_apply_followed_the_change(self):
        assert undo([self.a, self.b], [{"log": [self.a], "names": None, "applied": True}]) == ([self.a], None, "odd:1:0", True)

    def test_brings_back_a_forgotten_answer(self):
        assert undo([], [{"log": [self.a], "names": None, "applied": False}]) == ([self.a], None, None, False)

    def test_drops_the_last_answer_without_the_change_kept(self):
        # After a restart; answers saved before the flag count as applied.
        assert undo([self.a, self.b], []) == ([self.a], None, "odd:1:0", False)
        assert undo([{"id": "piece:2:0"}], []) == ([], None, "piece:2:0", True)



class TestWithReview:
    def test_loads_review_js_after_data_js_with_or_without_its_hash(self):
        for src in ("data.js", "data.js?v=1b236973b3"):
            html = f'<script defer src="{src}"></script><script defer src="./assets/index.js"></script>'

            assert with_review(html) == f'<script defer src="{src}"></script><script defer src="review.js"></script><script defer src="./assets/index.js"></script>'


class TestMarkOdd:
    a, b, c = {"track": 1, "frame": 10}, {"track": 2, "frame": 20}, {"track": 3, "frame": 30}

    def test_parts_each_odd_picture_from_each_other_one_but_not_the_odd_ones_from_each_other(self):
        log = mark_odd([], [self.b, self.c], [self.a])

        assert log == [{"id": "odd:1:10,2:20,3:30", "choice": "odd", "odd": [self.b, self.c], "to": [None, None], "rest": [self.a], "different": [[self.b, self.a], [self.c, self.a]], "applied": False}]

    def test_replaces_the_marks_of_the_same_pictures_and_clears_them(self):
        log = mark_odd([{"id": "piece:9:90"}], [self.b], [self.a, self.c])

        assert [e["id"] for e in mark_odd(log, [self.b, self.c], [self.a])] == ["piece:9:90", "odd:1:10,2:20,3:30"]
        assert mark_odd(log, [], [self.a, self.b, self.c]) == [{"id": "piece:9:90"}]

    def test_joins_an_odd_picture_to_the_player_it_is_said_to_be_that_player_first(self):
        paul = {"track": 8, "frame": 80}

        entry = mark_odd([], [self.b], [self.a], [paul])[0]

        assert entry["same"] == [[paul, self.b]] and entry["different"] == [[self.b, self.a]]

    def test_keeps_every_picture_marked_with_the_players_they_are(self):
        paul = {"track": 8, "frame": 80}

        entry = mark_odd([], [self.a, self.b], [], [paul, None])[0]

        assert entry["odd"] == [self.a, self.b] and entry["same"] == [[paul, self.a]] and entry["different"] == []

    def test_unmarking_a_picture_clears_its_mark_made_among_other_pictures(self):
        d = {"track": 4, "frame": 40}
        # b and c marked against a; an apply then shows b with d instead.
        log = mark_odd([], [self.b, self.c], [self.a])

        log = mark_odd(log, [], [self.b, d])

        assert [e["odd"] for e in log] == [[self.c]] and log[0]["different"] == [[self.c, self.a]]
        assert mark_odd(log, [], [self.c, d]) == []

    def test_a_picture_of_no_player_leaves_the_players(self):
        entry = mark_odd([], [self.b], [self.a], ["not_player"])[0]

        assert entry["not_player"] == [self.b] and "same" not in entry

    def test_keeps_the_earlier_marks_of_pictures_it_is_told_to(self):
        d = {"track": 4, "frame": 40}
        log = mark_odd([], [self.b, self.c], [self.a])

        log = mark_odd(log, [d], [self.b], keep=frozenset({"2:20"}))

        assert [e["odd"] for e in log] == [[self.b, self.c], [d]]


class TestSettled:
    a, b, c, paul = {"track": 1, "frame": 10}, {"track": 2, "frame": 20}, {"track": 3, "frame": 30}, {"track": 8, "frame": 80}

    def test_finds_the_pictures_an_apply_moved_as_marked(self):
        log = mark_odd([], [self.b, self.c], [self.a], [self.paul, None])
        where = {1: (1, 1), 2: (1, 5), 3: (1, 1), 8: (1, 5)}

        assert settled(log, lambda r: where[r["track"]]) == {"2:20"}
        where[3] = (1, 7)
        assert settled(log, lambda r: where[r["track"]]) == {"2:20", "3:30"}
        where[2] = (1, 7)
        assert settled(log, lambda r: where[r["track"]]) == {"3:30"}


class TestReanchor:
    wrong, kept, piece = {"track": 1, "frame": 15}, {"track": 2, "frame": 50}, {"track": 3, "frame": 70}
    # Pieces are tracks here; track 1's piece was shown as someone else.
    moved = {(1,): kept}

    @staticmethod
    def segment_of(ref):
        return (ref["track"],)

    def test_a_name_and_a_choice_pinned_on_a_wrong_picture_follow_the_player(self):
        log = [{"id": "piece:3:60", "choice": "0", "same": [[self.piece, self.wrong]], "different": [[self.piece, {"track": 9, "frame": 1}]]},
               {"id": "piece:3:61", "choice": "player:2:5", "same": [[self.wrong, self.piece]]}]

        log, names = reanchor(log, [{"ref": self.wrong, "name": "Laeticia"}], self.moved, self.segment_of)

        assert names == [{"ref": self.kept, "name": "Laeticia"}]
        assert log[0]["same"] == [[self.piece, self.kept]] and log[1]["same"] == [[self.kept, self.piece]]

    def test_the_player_confirmed_with_pictures_follows_too(self):
        log = [{"id": "more:2:5:0", "choice": "more", "pieces": [self.piece], "same": [[self.wrong, self.piece]], "different": [[self.piece, self.wrong]]}]

        log, _ = reanchor(log, [], self.moved, self.segment_of)

        assert log[0]["same"] == [[self.kept, self.piece]] and log[0]["different"] == [[self.piece, self.kept]]

    def test_the_marked_pictures_themselves_stay(self):
        log = mark_odd([], [self.wrong], [self.kept], [self.piece])

        assert reanchor(log, [], self.moved, self.segment_of)[0] == log


class TestChain:
    def test_gives_the_answers_on_the_shortest_path_between_two_names_pieces(self):
        # Laeticia's piece L, a mixed piece M said to be Josselin's piece J by answer "piece:9:1".
        links = {"L": [("M", "odd:x")], "M": [("L", "odd:x"), ("J", "piece:9:1")], "J": [("M", "piece:9:1")], "K": [("J", None)]}

        assert chain(links, {"L"}, {"J", "K"}) == ["odd:x", "piece:9:1"]
        assert chain(links, {"L"}, {"Z"}) == []


class TestMatchEnd:
    @staticmethod
    def questions():
        questions = Questions.__new__(Questions)
        questions.table = [(1, 0, 10, 2, 5), (1, 20, 90, 2, 5), (2, 100, 900, 2, 5), (3, 100, 200, 2, 6), (4, 100, 200, 0, 0)]
        return questions

    def test_moves_the_pins_past_it_to_the_players_longest_piece_before_it(self):
        assert self.questions().past_end(100) == {(2, 100, 900): {"track": 1, "frame": 55}}

    def test_saves_it_and_takes_it_away(self, tmp_path):
        files.write_text(tmp_path / "teams.json", json.dumps({"teams": []}))

        set_end(tmp_path, "78:10")
        assert match_end(tmp_path) == 4690.0
        set_end(tmp_path, " ")
        assert match_end(tmp_path) is None
        with pytest.raises(ValueError):
            set_end(tmp_path, "soon")

    def test_rallies_after_it_are_no_rallies(self, tmp_path):
        files.write_text(tmp_path / "teams.json", json.dumps({"teams": [], "end": "1:00"}))
        files.write_text(tmp_path / "rallies.csv", "start_frame,end_frame\n100,200\n3000,3100\n")

        assert web.no_rallies(tmp_path, 50.0) == {3000}


class TestToOtherTeam:
    def test_gives_each_piece_of_the_card_the_other_team(self):
        questions = Questions.__new__(Questions)
        questions.table = [(1, 0, 10, 1, 5), (2, 20, 90, 1, 5), (3, 0, 10, 1, 6)]

        entry = questions.to_other_team(1, 5)

        assert entry["team"] == [{"track": 2, "frame": 55, "team": 2}, {"track": 1, "frame": 5, "team": 2}]


class TestSeparated:
    anthony, josselin, good = {"track": 1, "frame": 5}, {"track": 2, "frame": 5}, {"track": 3, "frame": 5}
    names = [{"ref": anthony, "name": "Anthony"}, {"ref": josselin, "name": "Josselin"}]

    @staticmethod
    def questions():
        questions = Questions.__new__(Questions)
        questions.table = [(track, 0, 10, 2, 17) for track in (1, 2, 3)]
        return questions

    def test_takes_only_the_piece_a_more_answer_got_wrong(self):
        log = [{"id": "more:2:11:1", "choice": "more", "same": [[self.anthony, self.good, self.josselin]], "different": []}]

        assert self.questions().separated(log, self.names, 2, 17) == [
            {"id": "more:2:11:1", "choice": "more", "same": [[self.anthony, self.good]], "different": [[self.anthony, self.josselin]]}
        ]

    def test_forgets_any_other_answer_whole_and_keeps_the_rest(self):
        joining = {"id": "piece:3:0", "choice": "same", "same": [[self.anthony, self.good], [self.good, self.josselin]]}
        other = {"id": "pin", "choice": "pinned"}

        assert self.questions().separated([joining, other], self.names, 2, 17) == [other]

    def test_leaves_answers_joining_nobody(self):
        log = [{"id": "more:2:11:1", "choice": "more", "same": [[self.anthony, self.good]]}]

        assert self.questions().separated(log, self.names, 2, 17) == log


class TestNameMerges:
    josselin, laeticia, piece = {"track": 1, "frame": 10}, {"track": 2, "frame": 20}, {"track": 3, "frame": 30}
    names = [{"ref": josselin, "name": "Josselin"}, {"ref": laeticia, "name": "Laeticia"}]

    @staticmethod
    def segment_of(ref):
        return ref["track"]

    def test_finds_two_names_the_answers_join(self):
        log = [{"id": "a", "same": [[self.piece, self.josselin]]}, {"id": "b", "same": [[self.laeticia, self.piece]]}]

        assert name_merges(log, self.names, self.segment_of) == {frozenset({"Josselin", "Laeticia"})}
        assert name_merges(log[:1], self.names, self.segment_of) == set()


class TestLetGo:
    anna, ben, piece, other = {"track": 1, "frame": 5}, {"track": 2, "frame": 5}, {"track": 3, "frame": 5}, {"track": 4, "frame": 5}
    names = [{"ref": anna, "name": "Anna"}, {"ref": ben, "name": "Ben"}]

    @staticmethod
    def segment_of(ref):
        return ref["track"]

    def marks(self):
        return mark_odd([], [{"track": 3, "frame": 7}, self.other], [{"track": 9, "frame": 1}], [self.ben, self.ben])

    def test_a_new_answer_on_a_marked_piece_joins_nobody_and_keeps_the_other_marks(self):
        answer = {"id": "piece:3:0", "same": [[self.anna, self.piece]]}
        log = self.marks()
        assert name_merges([*log, answer], self.names, self.segment_of) == {frozenset({"Anna", "Ben"})}

        kept = let_go(log, self.piece, self.segment_of)

        assert name_merges([*kept, answer], self.names, self.segment_of) == set()
        assert kept[0]["odd"] == [self.other] and kept[0]["to"] == [self.ben]
        assert kept[0]["same"] == [[self.ben, self.other]]
        assert all(self.segment_of(a) != 3 for pair in kept[0]["different"] for a in pair)

    def test_a_mark_alone_goes_with_its_piece(self):
        log = mark_odd([], [{"track": 3, "frame": 7}], [{"track": 9, "frame": 1}], [self.ben])

        assert let_go(log, self.piece, self.segment_of) == []

    def test_another_answer_lets_go_of_the_piece_only(self):
        log = [{"id": "more:1", "choice": "more", "same": [[self.ben, self.piece, self.other]]}, {"id": "more:2", "choice": "more", "same": [[self.ben, self.piece]]}]

        assert let_go(log, self.piece, self.segment_of) == [{"id": "more:1", "choice": "more", "same": [[self.ben, self.other]]}, {"id": "more:2", "choice": "more", "same": []}]

    def test_a_name_pinned_on_the_piece_still_warns(self):
        names = [*self.names, {"ref": {"track": 3, "frame": 1}, "name": "Cleo"}]
        answer = {"id": "piece:3:0", "same": [[self.anna, self.piece]]}

        assert name_merges([*let_go([], self.piece, self.segment_of), answer], names, self.segment_of) == {frozenset({"Anna", "Cleo"})}


class TestPieceConflict:
    anna, ben, piece = {"track": 1, "frame": 5}, {"track": 2, "frame": 5}, {"track": 3, "frame": 5}
    names = [{"ref": anna, "name": "Anna"}, {"ref": ben, "name": "Ben"}]
    entry = {"id": "piece:3:0", "same": [[anna, piece]]}

    @staticmethod
    def segment_of(ref):
        return ref["track"]

    def test_names_both_players_of_a_piece_marked_as_the_other(self):
        log = mark_odd([], [{"track": 3, "frame": 7}], [{"track": 9, "frame": 1}], [self.ben])

        freed, earlier = piece_conflict(log, self.entry, self.piece, self.names, self.segment_of)

        assert earlier == ["Anna", "Ben"]
        assert freed == []

    def test_no_conflict_on_a_piece_nobody_said_anything_about(self):
        assert piece_conflict([], self.entry, self.piece, self.names, self.segment_of)[1] == []

    def test_no_conflict_with_the_same_player(self):
        log = mark_odd([], [{"track": 3, "frame": 7}], [{"track": 9, "frame": 1}], [self.anna])

        assert piece_conflict(log, self.entry, self.piece, self.names, self.segment_of)[1] == []

    def test_a_name_given_on_the_piece_is_a_real_merge_not_a_conflict_to_settle(self):
        names = [*self.names, {"ref": {"track": 3, "frame": 1}, "name": "Cleo"}]

        assert piece_conflict([], self.entry, self.piece, names, self.segment_of)[1] == []


class TestPooledRuns:
    @staticmethod
    def write(outputs, name, runs):
        (outputs / name).mkdir()
        (outputs / name / "learn.json").write_text(json.dumps([{"time": t, "commit": c, "scores": s} for t, c, s in runs]))

    def test_each_run_counts_every_match_at_its_latest_run_then(self, tmp_path):
        self.write(tmp_path, "a", [("2026-11-01 10:00", "a1", {"who": [1, 2]}), ("2026-11-03 10:00", "a2", {"who": [8, 10]})])
        self.write(tmp_path, "b", [("2026-11-02 10:00", "b1", {"who": [3, 4], "types": [1, 1]})])

        runs = pooled_runs(tmp_path)

        assert [r["commit"] for r in runs] == ["a1", "b1", "a2"]
        assert [r["match"] for r in runs] == ["a", "b", "a"]
        assert [r["scores"]["who"] for r in runs] == [[1, 2], [4, 6], [11, 14]]
        assert runs[-1]["scores"]["types"] == [1, 1]
        assert "types" not in runs[0]["scores"]

    def test_only_the_matches_with_runs_count(self, tmp_path):
        (tmp_path / "no-run").mkdir()
        (tmp_path / "file.txt").write_text("")

        assert pooled_runs(tmp_path) == []


class TestSupersede:
    landy, milenka, piece, other = {"track": 1, "frame": 10}, {"track": 2, "frame": 20}, {"track": 3, "frame": 30}, {"track": 4, "frame": 40}

    @staticmethod
    def segment_of(ref):
        return ref["track"]

    def test_an_earlier_answer_lets_go_of_a_piece_marked_in_its_players_card(self):
        log = [
            {"id": "piece:3:30", "same": [[self.piece, self.landy]]},
            {"id": "more:1:1:0", "same": [[self.landy, self.piece, self.other]]},
            {"id": "odd:x", "same": [[self.milenka, self.piece]]},
        ]

        log = supersede(log, [self.piece], "odd:x", lambda r: r["track"] == 1, self.segment_of)

        assert [e["same"] for e in log] == [[], [[self.landy, self.other]], [[self.milenka, self.piece]]]


class TestMeeting:
    def test_finds_the_piece_two_answers_claim(self):
        # Manon's pin M, a card saying piece P is Manon, another card saying P is Quentin (pin Q).
        links = {"M": [("P", "odd:a")], "P": [("M", "odd:a"), ("Q", "odd:b")], "Q": [("P", "odd:b")]}

        assert meeting(path(links, {"M"}, {"Q"})) == ["P"]


class TestSetTeam:
    def test_names_and_colours_a_team_its_jersey_colour_back_without_one(self, tmp_path):
        (tmp_path / "teams.json").write_text(json.dumps({"teams": [{"name": "A", "colour": None, "jersey": "#151515"}, {"name": "B", "colour": None, "jersey": "#151515"}]}))

        set_team(tmp_path, 2, " Les Rouges ", "rouge")
        assert json.loads((tmp_path / "teams.json").read_text())["teams"][1] == {"name": "Les Rouges", "colour": "#d22630", "jersey": "#151515"}
        set_team(tmp_path, 2, "", None)
        assert json.loads((tmp_path / "teams.json").read_text())["teams"][1] == {"name": None, "colour": None, "jersey": "#151515"}
        with pytest.raises(ValueError):
            set_team(tmp_path, 1, "A", "not a colour")


class TestSetPhoto:
    def test_keeps_the_picture_picked_by_the_players_name(self, tmp_path):
        table = [(1, 0, 30, 2, 5)]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 10}, "name": "Maeva", "jersey": None}])

        set_photo(tmp_path, table, 2, 5, 12, [1, 2, 3, 4])

        assert json.loads((tmp_path / "photo_choices.json").read_text()) == {"Maeva": {"frame": 12, "box": [1, 2, 3, 4]}}

    def test_keeps_it_on_the_card_of_a_player_without_a_name(self, tmp_path):
        set_photo(tmp_path, [(1, 0, 30, 2, 5)], 2, 5, 12, [1, 2, 3, 4])

        assert json.loads((tmp_path / "photo_choices.json").read_text()) == {"2:5": {"frame": 12, "box": [1, 2, 3, 4]}}


class TestLastComparison:
    def test_the_last_run_against_what_it_replaced(self, tmp_path):
        (tmp_path / "learn.json").write_text(json.dumps([{"scores": {"who": [1, 2]}}, {"scores": {"who": [2, 2]}, "before": {"who": [1, 2]}}]))
        assert last_comparison(tmp_path) == {"before": {"who": [1, 2]}, "after": {"who": [2, 2]}}

    def test_none_when_the_last_run_measured_nothing_before_it(self, tmp_path):
        assert last_comparison(tmp_path) is None
        (tmp_path / "learn.json").write_text(json.dumps([{"scores": {}, "before": {}}, {"scores": {}}]))
        assert last_comparison(tmp_path) is None


class TestNotOver:
    @staticmethod
    def page(kind="attack", result="point"):
        rally = {"key": 100, "start": 2.0, "end": 8.0, "set": 1}
        return {"fps": 50.0, "rallies": [rally], "contacts": [{"t": 4.0, "f": 200, "type": kind, "team": 1, "rally": 0, "result": result}, {"t": 5.0, "f": 250, "type": "floor", "team": None, "rally": 0, "result": "play"}]}

    def test_a_point_with_no_crossing_after_it_is_reported(self):
        assert [(r["kind"], r["time"]) for r in review_module.not_over(self.page(), [100, 201])] == [("auto.notOver", 4.0)]

    def test_a_crossing_up_to_a_second_after_the_end_is_enough(self):
        assert review_module.not_over(self.page(), [449]) == []

    def test_neither_a_block_a_fault_a_rally_to_replay_nor_one_checked(self):
        assert review_module.not_over(self.page("block"), []) == []
        assert review_module.not_over(self.page(result="error"), []) == []
        assert review_module.not_over(self.page(), [], {100}) == []
        page = self.page()
        page["rallies"][0]["redo"] = True
        assert review_module.not_over(page, []) == []


class TestServer:
    def test_is_quiet_when_a_page_goes_and_reports_any_other_error(self, capsys):
        server = review_module.Server(("127.0.0.1", 0), review_module.BaseHTTPRequestHandler)
        try:
            for error in (BrokenPipeError(), ConnectionResetError()):
                try:
                    raise error
                except OSError:
                    server.handle_error(None, ("127.0.0.1", 1))
            assert capsys.readouterr().err == ""
            try:
                raise ValueError("bad answer")
            except ValueError:
                server.handle_error(None, ("127.0.0.1", 1))
            assert "bad answer" in capsys.readouterr().err
        finally:
            server.server_close()


class TestPageStamp:
    @staticmethod
    def page(tmp_path, data: dict):
        site = tmp_path / "review"
        site.mkdir(exist_ok=True)
        (site / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")
        (site / "index.html").write_text(f'<script src="data.js?v={data["v"]}"></script>')
        return site

    def test_the_same_page_patched_with_the_same_pictures_is_no_change(self, tmp_path):
        from volleyball_stats import review, web

        site = self.page(tmp_path, {"name": "m", "people": {"1": {"photo": "players/a.webp?v=1"}}, "v": "01e892555b"})
        first = review.page_stamp(tmp_path)
        # What a restart does: the page rebuilt, then the pictures patched in, moving its `v`.
        web.patch_people(site, {"1": {"photo": "players/a.webp?v=1"}})

        assert review.page_data(site)["v"] != "01e892555b"
        assert review.page_stamp(tmp_path) == first

    def test_the_order_of_the_datas_keys_is_no_change_its_content_is(self, tmp_path):
        from volleyball_stats import review

        self.page(tmp_path, {"name": "m", "people": {}, "v": "a"})
        first = review.page_stamp(tmp_path)
        self.page(tmp_path, {"people": {}, "v": "b", "name": "m"})
        assert review.page_stamp(tmp_path) == first
        self.page(tmp_path, {"people": {}, "v": "b", "name": "n"})
        assert review.page_stamp(tmp_path) != first


class TestPageChanges:
    def test_each_changed_part_with_how_many_of_its_items_then_the_code(self):
        from volleyball_stats.review import page_changes

        sent = {"data": {"contacts": [{"f": 1}, {"f": 2}, {"f": 3}], "people": {"1": {"name": "Ana"}, "2": {"name": "Bob"}}, "ball3d": True, "club": {"name": "A"}, "positions": {"step": 1}, "name": "m"}, "code": {"page": "a", "list": "c"}}
        now = {"data": {"contacts": [{"f": 1}, {"f": 2, "type": "set"}, {"f": 3}, {"f": 4}], "people": {"1": {"name": "Ana"}, "2": {"name": "Bobby"}, "3": {}}, "ball3d": False, "club": {"name": "A", "favicon": "x"}, "positions": {"step": 2}, "name": "m"}, "code": {"page": "b", "list": "c"}}

        assert page_changes(sent, now) == [
            {"part": "ball3d", "count": None},
            {"part": "club", "count": 1, "keys": ["favicon"]},
            {"part": "contacts", "count": 2},
            {"part": "people", "count": 2, "keys": ["Bobby", "3"]},
            {"part": "positions", "count": 1},
            {"part": "code", "count": None, "keys": ["page"]},
        ]
        assert page_changes(sent, sent) == []

    def test_an_upload_older_than_the_stamps_by_page_says_only_the_code_changed(self):
        from volleyball_stats.review import page_changes

        assert page_changes({"data": {}, "code": "a"}, {"data": {}, "code": {"page": "b", "list": "c"}}) == [{"part": "code", "count": None}]

    def test_a_late_page_says_what_changed_since_the_upload(self, tmp_path):
        from volleyball_stats import review

        TestPageStamp.page(tmp_path, {"name": "m", "contacts": [{"f": 1}], "v": "a"})
        review.record_hosted(tmp_path)
        assert review.read_hosted(tmp_path)["changes"] is None
        TestPageStamp.page(tmp_path, {"name": "m", "contacts": [{"f": 1}, {"f": 2}], "v": "b"})

        state = review.read_hosted(tmp_path)
        assert state["behind"] and state["changes"] == [{"part": "contacts", "count": 1}]

    def test_a_new_3d_view_makes_the_page_late(self, tmp_path, monkeypatch):
        from volleyball_stats import review

        scene = tmp_path / "scene3d.js"
        scene.write_text("a")
        monkeypatch.setitem(review.CODE_PAGES, "3d", scene)
        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        review.record_hosted(tmp_path)
        assert not review.read_hosted(tmp_path)["behind"]
        scene.write_text("b")

        state = review.read_hosted(tmp_path)
        assert state["behind"] and state["changes"] == [{"part": "code", "count": None, "keys": ["3d"]}]

    def test_an_upload_from_before_the_3d_views_stamp_is_judged_without_it(self, tmp_path, monkeypatch):
        from volleyball_stats import review

        scene = tmp_path / "scene3d.js"
        scene.write_text("a")
        monkeypatch.setitem(review.CODE_PAGES, "3d", scene)
        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        sent = review.page_content(tmp_path)
        del sent["code"]["3d"]
        (tmp_path / review.HOSTED_PAGE).write_text(json.dumps(sent))
        (tmp_path / review.HOSTED).write_text(json.dumps({"at": "2026-11-10T23:01:11", "stamp": review.page_stamp(tmp_path, review.OLD_STAMPED), "code": "x"}))
        scene.write_text("b")

        assert not review.read_hosted(tmp_path)["behind"]
        TestPageStamp.page(tmp_path, {"name": "n", "v": "b"})
        assert review.read_hosted(tmp_path)["changes"] == [{"part": "name", "count": None}]


    def test_a_page_rebuilt_by_the_uploads_code_is_not_late(self, tmp_path):
        from volleyball_stats import review

        # Uploaded with every match: the review's page as an older code built it, the upload by this one.
        TestPageStamp.page(tmp_path, {"name": "m", "brand": "x", "v": "a"})
        review.record_hosted(tmp_path)
        before = review.page_stamp(tmp_path)
        # Opened: the page rebuilt by this code.
        TestPageStamp.page(tmp_path, {"name": "m", "club": "x", "timeouts": [], "v": "b"})
        assert review.read_hosted(tmp_path)["behind"]

        review.restamp(tmp_path, before)
        assert not review.read_hosted(tmp_path)["behind"]

    def test_a_page_rebuilt_by_other_code_than_the_uploads_stays_late(self, tmp_path):
        from volleyball_stats import review

        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        review.record_hosted(tmp_path)
        saved = json.loads((tmp_path / review.HOSTED).read_text())
        (tmp_path / review.HOSTED).write_text(json.dumps({**saved, "code": "older"}))
        before = review.page_stamp(tmp_path)
        TestPageStamp.page(tmp_path, {"name": "m", "timeouts": [], "v": "b"})

        review.restamp(tmp_path, before)
        assert review.read_hosted(tmp_path)["behind"]

    def test_a_change_since_the_upload_stays_late(self, tmp_path):
        from volleyball_stats import review

        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        review.record_hosted(tmp_path)
        # An answer since: the page rebuilt then, its stamp no longer the upload's.
        TestPageStamp.page(tmp_path, {"name": "n", "v": "b"})
        before = review.page_stamp(tmp_path)
        TestPageStamp.page(tmp_path, {"name": "n", "timeouts": [], "v": "c"})

        review.restamp(tmp_path, before)
        assert review.read_hosted(tmp_path)["behind"]


class TestMore:
    def test_only_pieces_as_like_the_card_as_more_like_are_offered(self, tmp_path):
        from volleyball_stats.review import MORE_LIKE, Questions

        q = object.__new__(Questions)
        q.match, q.fps, q.avoid = tmp_path, 50.0, set()
        # The card (identity 1) and two pieces of identity 2, after it: one alike, one not.
        q.table = [(1, 0, 99, 1, 1), (2, 200, 299, 1, 2), (3, 200, 299, 1, 2)]
        q.clear = lambda track, start, end: start
        q.crop = lambda track, frame: f"{track}"
        far = np.cos(np.arccos(MORE_LIKE) + 0.05)
        vectors = np.array([[1.0, 0.0], [0.99, np.sqrt(1 - 0.99**2)], [far, np.sqrt(1 - far**2)]])
        np.savez(tmp_path / "embeddings.npz", keys=np.array([[1, 0, 99], [2, 200, 299], [3, 200, 299]]), vectors=vectors)

        assert [p["track"] for p in q.more(1, 1, set())] == [2]


class TestSetStart:
    @staticmethod
    def match(tmp_path):
        # Rallies at 0-20 s, 60-80 s, 300-320 s and 400-420 s (50 fps); a set start typed at 2:30, its score 25-20.
        files.write_text(tmp_path / "teams.json", json.dumps({"teams": [], "sets": ["0:00", "2:30"], "scores": [None, [25, 20]]}))
        files.write_text(tmp_path / "rallies.csv", "start_frame,end_frame\n0,1000\n3000,4000\n15000,16000\n20000,21000\n")
        return tmp_path

    def test_starts_a_set_in_the_break_before_the_rally_playing_or_the_next(self, tmp_path):
        match = self.match(tmp_path)

        set_start(match, 50.0, add=70.0)
        assert json.loads((match / "teams.json").read_text())["sets"] == ["0:00", "0:40", "2:30"]
        set_start(match, 50.0, add=330.0)
        assert json.loads((match / "teams.json").read_text())["sets"] == ["0:00", "0:40", "2:30", "6:00"]

    def test_one_start_a_break_and_the_scores_follow_their_sets(self, tmp_path):
        match = self.match(tmp_path)

        # 2:30 and the break's middle, 3:10, start the same rallies: the new one takes its place.
        set_start(match, 50.0, add=200.0)
        saved = json.loads((match / "teams.json").read_text())
        assert saved["sets"] == ["0:00", "3:10"] and saved["scores"] == [None, None]
        set_start(match, 50.0, add=70.0)
        set_start(match, 50.0, remove="3:10")
        saved = json.loads((match / "teams.json").read_text())
        assert saved["sets"] == ["0:00", "0:40"] and saved["scores"] == [None, None]

    def test_keeps_a_kept_sets_score(self, tmp_path):
        match = self.match(tmp_path)

        set_start(match, 50.0, add=70.0)
        assert json.loads((match / "teams.json").read_text())["scores"] == [None, None, [25, 20]]

    def test_refuses_the_first_set_and_a_moment_after_the_last_rally(self, tmp_path):
        match = self.match(tmp_path)

        for change in ({"add": 5.0}, {"add": 500.0}, {"remove": "0:00"}, {"remove": "1:00"}):
            with pytest.raises(ValueError):
                set_start(match, 50.0, **change)
