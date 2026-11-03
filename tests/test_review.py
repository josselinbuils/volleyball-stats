import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from volleyball_stats.identity import read_names
from volleyball_stats import files
from volleyball_stats.review import hosted_state, APPLIED, Questions, aces, missed_points, rotation_slips, checked, commented, corrections, read_comments, write_comments, eta, locked, pinned, unlocked, report_answer, superseded, unusual, report_question, reports, unnamed, chain, constraints, doubtful, rally_answer, meeting, path, name_merges, supersede, load_roster, mark_odd, range_of, reanchor, receiver_answer, remember, retitle, save, set_name, set_photo, set_team, settled, state, suggest, touch_answer, undo, waiting, with_review, write_names, list_page, match_list, reopening


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

        assert str(tmp_path / "done") in command and "--no-browser" in command
        for name in ("running", "nothing", "../done"):
            with pytest.raises(LookupError):
                reopening(name, tmp_path, "aspom", 8765, tmp_path / "roster.json")

    def test_the_page_lists_them_for_the_review_and_serves_only_its_own_files(self, tmp_path):
        self.folder(tmp_path, "m", "2026-10-29")

        html, kind = list_page("/matches/", tmp_path, "none")

        assert b"matches.js" in html and kind.startswith("text/html")
        body, _ = list_page("/matches/matches.js", tmp_path, "none")
        assert b'"review": true' in body and b'"path": "m"' in body
        assert list_page("/matches/../../secret", tmp_path, "none") is None
        assert list_page("/matches/nothing.js", tmp_path, "none") is None


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
        (tmp_path / "feedback.log").write_text(line(mine) + "\n" + line(other) + "\n")
        (tmp_path / "feedback-copy.log").write_text(line(mine) + "\n")
        (tmp_path / "m").mkdir()

        found = reports(tmp_path / "m")

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
            (4.0, "auto.noWinner"),
            (5.0, "auto.afterFault"),
            (6.0, "auto.samePlayer"),
            (7.0, "auto.afterPoint"),
        ]
        assert found[0]["key"] == unusual(page)[0]["key"]
        # The set's last rally ends off the final score given; its report comes back once the score moves.
        page["rallies"][-1]["score"] = [5, 2]
        off = [r for r in unusual(page) if r["kind"] == "auto.scoreOff"]
        assert [r["time"] for r in off] == [7.0]
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

    def test_a_set_off_its_score_lists_the_ball_in_play_outside_its_rallies(self, tmp_path):
        calibration = SimpleNamespace(to_image=lambda points: np.array([[1000.0, 0.0], [0.0, 0.0], [1800.0, 0.0]]))
        ball = tmp_path / "ball.csv"
        rows = ["frame,visible,x,y"]
        # A rally the pipeline missed from frame 200, fast and over the net; a ball rolling on one side from frame 500.
        rows += [f"{f},1,{200 + (f - 200) * 25},0" for f in range(200, 260)]
        rows += [f"{f},1,{200 + (f - 500)},0" for f in range(500, 900)]
        ball.write_text("\n".join(rows))
        page = {"fps": 50.0, "duration": 30.0, "scores": ["2-1"], "rallies": [{"start": 0.0, "end": 1.0, "set": 1, "score": [1, 1]}], "contacts": []}

        found = missed_points(page, ball, calibration)

        assert [(r["kind"], r["time"]) for r in found] == [("auto.missedPoint", 4.0)]
        page["rallies"][0]["score"] = [2, 1]
        assert missed_points(page, ball, calibration) == []

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
        assert eta(run, took, 600.0) == {"steps": run["steps"], "done": 1, "stage": "wrists", "elapsed": 600.0, "left": 300.0 + 500.0 + 10.0, "late": False}
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
    def test_asks_the_serves_that_end_a_rally_their_team_won_with_their_landing(self):
        row = lambda frame, kind, team="": {"frame": str(frame), "type": kind, "team": team}  # noqa: E731
        actions = [row(10, "serve", "1"), row(30, "floor"), row(100, "serve", "2"), row(200, "serve", "1"), row(220, "pass", "2"), row(300, "serve", "2")]

        found = aces(actions, [(0, 50), (90, 150), (190, 250), (290, 350)], ["1", "1", "2", None])

        assert [(s["frame"], l and l["frame"]) for s, l in found] == [("10", "30")]

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

        assert json.loads(path.read_text()) == {"same": [], "different": [], "not_player": [{"track": 1}], "cut": [], "touch": [], "rally": [], "receiver": [], "action": [], "winner": [], "added": [], "end": [], "join": [], "split": [], "pinned": [], "locked": [], "redo": [], "referee": [], "log": log}


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

    def test_a_team_renamed_takes_its_players_of_that_match_with_it(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": 7}, (2, 1): {"name": "Léa", "jersey": None}}, {(1, 1): self.a, (2, 1): self.b}, ["ASPOM 02", "AVIA"])
        remember(path, "m2", {(1, 1): {"name": "Julie", "jersey": None}}, {(1, 1): self.b}, ["ASPOM 02", "AVIA"])
        retitle(path, "m1", "ASPOM 02", "ASPOM 2")
        found = {(p["team"], p["name"]): p for p in load_roster(path)}
        assert sorted(found) == [("ASPOM 02", "Julie"), ("ASPOM 2", "Julie"), ("AVIA", "Léa")]
        assert list(found["ASPOM 2", "Julie"]["vectors"]) == ["m1"] and found["ASPOM 2", "Julie"]["jersey"] == 7
        assert list(found["ASPOM 02", "Julie"]["vectors"]) == ["m2"]
        # The rest of the team joins the player it now holds.
        retitle(path, "m2", "ASPOM 02", "ASPOM 2")
        found = {(p["team"], p["name"]): p for p in load_roster(path)}
        assert sorted(found) == [("ASPOM 2", "Julie"), ("AVIA", "Léa")]
        assert sorted(found["ASPOM 2", "Julie"]["vectors"]) == ["m1", "m2"]

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

        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": False, "corrections": {}, "films": {"total": 0, "stale": 0}, "checked": []}
        assert waiting(tmp_path, [])["changed"]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 5}, "name": "Julie", "jersey": None}])
        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": True, "corrections": {}, "films": {"total": 0, "stale": 0}, "checked": []}
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        assert waiting(tmp_path, log)["changed"]


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
        with pytest.raises(ValueError):
            set_photo(tmp_path, table, 2, 6, 12, [1, 2, 3, 4])
