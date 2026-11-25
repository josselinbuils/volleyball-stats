import json
import os
from datetime import date

import pytest

from volleyball_stats import analysis, review, review_answers, web
from volleyball_stats.hosted import hosted_state
from volleyball_stats.review import (
    APPLIED,
    answers_stamp,
    applied_too,
    commented,
    due,
    eta,
    last_comparison,
    learned,
    locked,
    pinned,
    pooled_runs,
    read_comments,
    to_apply,
    undo,
    unlocked,
    waiting,
    write_comments,
)
from volleyball_stats.review_answers import report_answer, save, state, write_names
from volleyball_stats.review_questions import report_question, reports, rotation_slips, unusual


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

    def test_a_report_without_a_clip_keeps_its_own_time_not_what_its_page_named(self):
        question, _ = report_question({"time": 52.0, "clip": None, "kind": "player", "shown": "Échange 2 · 1:10", "comment": ""}, self.page, 50.0)

        assert (question["reports"][0]["shown"], question["reports"][0]["time"]) == (None, 52.0)
        assert report_question({"time": 100.0, "clip": {"time": 12.0}, "shown": "Service"}, self.page, 50.0)[0]["reports"][0]["shown"] == "Service"

    def test_the_review_s_own_check_keeps_its_value(self):
        question, _ = report_question({"time": 52.0, "kind": "auto.record.jump", "shown": "71 cm", "comment": None}, self.page, 50.0)

        assert question["reports"][0]["shown"] == "71 cm"

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

    def test_a_relance_as_first_touch_is_reported(self):
        def c(t, kind, team):
            return {"t": t, "type": kind, "team": team, "side": "left" if team == 1 else "right", "rally": 0, "result": "play"}

        page = {"teams": [{}, {}], "rallies": [{"start": 0.0, "end": 5.0, "set": 1, "winner": 1}], "contacts": [c(0.1, "serve", 1), c(1.0, "pass", 2), c(1.8, "set", 2), c(2.6, "relance", 2)]}
        assert unusual(page) == []
        page["contacts"].append(c(3.5, "relance", 1))
        assert [r["kind"] for r in unusual(page)] == ["auto.relanceFirst"]
        # A team's 2nd touch with both hands: a set when its team plays on, a relance when the other team plays next.
        page["contacts"][2]["type"] = "relance"
        assert [r["kind"] for r in unusual(page)] == ["auto.relanceSecond", "auto.relanceFirst"]
        page["contacts"][2:] = [c(1.8, "set", 2), c(2.6, "dig", 1)]
        assert unusual(page) == []
        page["rallies"][0]["key"] = 5
        assert [r["kind"] for r in unusual(page, done={5})] == ["auto.setOver"]
        page["contacts"][2]["type"] = "relance"
        assert unusual(page) == []

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

    def test_a_fault_shared_with_a_second_player_becomes_a_partner_answer(self):
        changes = {
            "touches": [{"frame": 2100, "partner": "1:4"}, {"frame": 3050, "partner": "none"}],
            "added": [{"frame": 2150, "team": 1, "type": "missed", "result": "error", "partner": "2:7"}],
        }

        out = report_answer(changes, self.teams, self.windows, {(1, 4): {"name": "Léa"}}, 20)

        assert out["added"] == [{"start": 2000, "frame": 2150, "team": 1, "type": "missed"}]
        assert out["partner"] == [
            {"frame": 2150, "team": 2, "identity": 7, "name": None}, {"frame": 2100, "team": 1, "identity": 4, "name": "Léa"}, {"frame": 3050, "team": 1, "identity": None, "name": None},
        ]
        assert "partner" not in report_answer({"touches": [{"frame": 2100, "result": "error"}]}, self.teams, self.windows, {}, 20)

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

        # 100 s of the wrists' 400 spent, nothing counted: the bar holds at the training's share; the teams and the review to come.
        held = eta(run, took, 600.0)
        assert {k: held[k] for k in ("left", "late", "part")} == {"left": 300.0 + 500.0 + 10.0, "late": False, "part": None}
        assert held["fraction"] == pytest.approx(100.0 / 1010.0)
        late = eta(run, took, 1000.0)
        assert (late["left"], late["late"]) == (510.0, True)
        # Before its first stage, a step counts as a whole.
        assert eta({**run, "stage": None, "done": 0, "since": 0.0}, took, 40.0)["left"] == 60.0 + 900.0 + 10.0

    def test_counted_work_moves_the_share_and_sets_the_pace(self):
        took = {"players": 40.0, "review": 10.0}
        run = {"steps": ["players", "review"], "done": 0, "started": 0.0, "since": 0.0, "own": 0.25}

        # A quarter counted in 30 s: 90 s more, though the last run took 40 in all.
        found = eta(run, took, 30.0)
        assert (found["part"], found["left"], found["late"]) == (0.25, 90.0 + 10.0, True)
        assert found["fraction"] == pytest.approx(10.0 / 50.0)
        # The run's own weights, not the durations it already recorded.
        assert eta({**run, "weights": {"players": 10.0, "review": 10.0}}, took, 30.0)["fraction"] == pytest.approx(2.5 / 20.0)
        # The stages finished count as done within the step.
        staged = {"steps": ["films"], "done": 0, "started": 0.0, "since": 0.0, "stage": "filmsRender", "stage_since": 10.0, "own": 0.5, "passed": 10.0}
        assert eta(staged, {"films": 110.0, "films:filmsBall": 10.0, "films:filmsRender": 100.0}, 20.0)["fraction"] == pytest.approx(60.0 / 110.0)

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


class TestWaiting:
    entry = {"id": "piece:1:0", "choice": "0", "same": [[{"track": 1, "frame": 5}, {"track": 2, "frame": 5}]], "applied": False}

    def test_counts_the_answers_saying_something_not_applied_yet(self, tmp_path):
        # Applied, saved before the flag (applied), not applied, and "I don't know".
        log = [{**self.entry, "applied": True}, {k: v for k, v in self.entry.items() if k != "applied"}, self.entry, {"id": "piece:3:0", "choice": "skip", "applied": False}]

        assert waiting(tmp_path, log)["pending"] == 1

    def test_tells_whether_the_answers_jersey_numbers_or_names_differ_from_what_the_identities_were_computed_from(self, tmp_path):
        log = [{**self.entry, "applied": True}]
        (tmp_path / APPLIED).write_text(json.dumps(state(tmp_path, log)))

        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": False, "toApply": [], "corrections": {}, "films": {"players": {"total": 0, "stale": []}, "highlights": {"total": 0, "stale": []}}, "checked": [], "due": None}
        assert waiting(tmp_path, [])["changed"]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 5}, "name": "Julie", "jersey": None}])
        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": True, "toApply": [["names", None]], "corrections": {}, "films": {"players": {"total": 0, "stale": []}, "highlights": {"total": 0, "stale": []}}, "checked": [], "due": None}
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        assert waiting(tmp_path, log)["changed"]

    def test_a_timeout_given_since_the_last_apply_is_a_change(self, tmp_path):
        (tmp_path / APPLIED).write_text(json.dumps({k: v for k, v in state(tmp_path, []).items() if k != "timeouts"}))
        assert not waiting(tmp_path, [])["changed"]

        (tmp_path / "timeouts.json").write_text(json.dumps([{"start": 100, "end": 2000, "team": 1}]))
        assert waiting(tmp_path, [])["changed"]

    def test_learned_while_the_last_learning_run_saw_the_answers_as_they_stand(self, tmp_path):
        log = [{**self.entry, "applied": False}]
        assert not learned(tmp_path, log)

        (tmp_path / "learn.json").write_text(json.dumps([{"time": "2026-11-09 10:00", "answers": answers_stamp(log)}]))
        assert learned(tmp_path, log)
        # Applying changes nothing the run saw; another answer does.
        assert learned(tmp_path, [{**self.entry, "applied": True}])
        assert not learned(tmp_path, log + [{"id": "piece:3:0", "choice": "skip"}])
        # A report marked handled as its rally stood teaches nothing; one with a correction or checking a rally does.
        handled = {"id": "report:8d49e5f29622", "choice": "report", "changes": {"touches": []}, "applied": False}
        assert learned(tmp_path, log + [handled, {"id": "report:a", "choice": "report", "applied": True}])
        assert not learned(tmp_path, log + [{**handled, "changes": {"touches": [{"frame": 5, "type": "pass"}]}}])
        assert not learned(tmp_path, log + [{**handled, "checked": [2000]}])
        assert not learned(tmp_path, log + [handled, {"id": "piece:3:0", "choice": "skip"}])

    def test_a_kind_of_answer_added_since_the_last_apply_with_nothing_said_is_no_change(self, tmp_path):
        applied = state(tmp_path, [])
        del applied["answers"]["partner"]
        (tmp_path / APPLIED).write_text(json.dumps(applied))

        assert not waiting(tmp_path, [])["changed"]
        assert waiting(tmp_path, [{"id": "touch:5", "partner": [{"frame": 5}], "applied": True}])["changed"]

    def test_says_what_an_apply_takes_in_by_what_its_answers_are_about(self, tmp_path):
        log = [
            self.entry,
            {"id": "report:a", "choice": "report", "action": [{"frame": 1}], "touch": [{"frame": 1}], "applied": False},
            {"id": "touch:5", "choice": "player:1:4", "touch": [{"frame": 5}], "applied": False},
            {"id": "touch:6", "choice": "player:1:4", "touch": [{"frame": 6}], "applied": True},
            {"id": "piece:3:0", "choice": "skip", "applied": False},
        ]

        assert to_apply(log, {"answers": True, "jerseys": False, "timeouts": True, "names": False}) == [["players", 1], ["touches", 2], ["timeouts", None]]
        # Answers changed with none to apply, as after an undo: said so.
        assert to_apply([], {"answers": True, "jerseys": True, "timeouts": False, "names": True}) == [["answers", None], ["jerseys", None], ["names", None]]

    def test_rallies_checked_locked_at_the_start_are_no_change(self, tmp_path):
        log = [{**self.entry, "applied": True}]
        (tmp_path / APPLIED).write_text(json.dumps(state(tmp_path, log)))
        lock = [{"id": "lock", "choice": "locked", "action": [{"frame": 5, "type": "serve", "result": "play"}], "locked": [{"start": 1, "touches": []}], "applied": True}]

        assert waiting(tmp_path, lock + log)["changed"]
        applied_too(tmp_path, lock)
        assert not waiting(tmp_path, lock + log)["changed"]
        applied_too(tmp_path / "none", lock)

    def test_jersey_numbers_copied_through_the_server_to_the_second_are_no_change(self, tmp_path):
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        os.utime(tmp_path / "jerseys.csv", (1793733733.7316, 1793733733.7316))
        (tmp_path / APPLIED).write_text(json.dumps({**state(tmp_path, []), "jerseys": 1793733733.7316}))
        os.utime(tmp_path / "jerseys.csv", (1793733733.0, 1793733733.0))

        assert not waiting(tmp_path, [])["changed"]


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


class TestLastComparison:
    @staticmethod
    def runs(folder, runs):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "learn.json").write_text(json.dumps(runs))

    def test_the_last_run_against_what_it_replaced(self, tmp_path):
        self.runs(tmp_path / "a", [{"time": "1", "scores": {"who": [1, 2]}}, {"time": "2", "scores": {"who": [2, 2]}, "before": {"who": [1, 2]}}])
        assert last_comparison(tmp_path) == {"before": {"who": [1, 2]}, "after": {"who": [2, 2]}}

    def test_the_last_update_summed_over_its_matches(self, tmp_path):
        self.runs(tmp_path / "a", [{"time": "2", "update": "u2", "scores": {"who": [2, 2]}, "before": {"who": [1, 2]}}])
        self.runs(tmp_path / "b", [{"time": "3", "update": "u2", "scores": {"who": [3, 4]}, "before": {"who": [3, 4]}}])
        # An older update's run is not the last one's.
        self.runs(tmp_path / "c", [{"time": "1", "update": "u1", "scores": {"who": [9, 9]}, "before": {"who": [0, 9]}}])

        assert last_comparison(tmp_path) == {"before": {"who": [4, 6]}, "after": {"who": [5, 6]}}

    def test_none_when_the_last_run_measured_nothing_before_it(self, tmp_path):
        assert last_comparison(tmp_path) is None
        self.runs(tmp_path / "a", [{"time": "1", "scores": {}, "before": {}}, {"time": "2", "scores": {}}])
        assert last_comparison(tmp_path) is None


class TestDue:
    entry = {"id": "piece:1:0", "choice": "0", "applied": True}

    def test_answers_since_its_last_learning_then_other_code(self, tmp_path):
        assert due(tmp_path, [self.entry]) is None
        (tmp_path / "report.md").touch()
        assert due(tmp_path, [self.entry]) == "answers"

        (tmp_path / "learn.json").write_text(json.dumps([{"time": "1", "answers": answers_stamp([self.entry])}]))
        assert due(tmp_path, [self.entry]) == "rules"
        analysis.write(tmp_path, analysis.fingerprint(tmp_path))
        assert due(tmp_path, [self.entry]) is None
        analysis.write(tmp_path, "older")
        assert due(tmp_path, []) == "rules"

    def test_a_fully_checked_match_waits_only_for_new_answers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review, "reviewed", lambda page, log: True)
        (tmp_path / "report.md").touch()
        assert due(tmp_path, []) is None
        assert due(tmp_path, [self.entry]) == "answers"


class TestPageStamp:
    @staticmethod
    def page(tmp_path, data: dict):
        site = tmp_path / "review"
        site.mkdir(exist_ok=True)
        (site / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")
        (site / "index.html").write_text(f'<script src="data.js?v={data["v"]}"></script>')
        return site

    def test_the_same_page_patched_with_the_same_pictures_is_no_change(self, tmp_path):
        from volleyball_stats import hosted, web

        site = self.page(tmp_path, {"name": "m", "people": {"1": {"photo": "players/a.webp?v=1"}}, "v": "01e892555b"})
        first = hosted.page_stamp(tmp_path)
        # What a restart does: the page rebuilt, then the pictures patched in, moving its `v`.
        web.patch_people(site, {"1": {"photo": "players/a.webp?v=1"}})

        assert web.page_data(site)["v"] != "01e892555b"
        assert hosted.page_stamp(tmp_path) == first

    def test_the_order_of_the_datas_keys_is_no_change_its_content_is(self, tmp_path):
        from volleyball_stats import hosted

        self.page(tmp_path, {"name": "m", "people": {}, "v": "a"})
        first = hosted.page_stamp(tmp_path)
        self.page(tmp_path, {"people": {}, "v": "b", "name": "m"})
        assert hosted.page_stamp(tmp_path) == first
        self.page(tmp_path, {"people": {}, "v": "b", "name": "n"})
        assert hosted.page_stamp(tmp_path) != first


def test_a_look_set_by_name_shows_on_the_players_other_matches_whose_hosted_copy_goes_late(tmp_path, monkeypatch):
    from volleyball_stats import hosted, identity, likeness

    def page(match, people):
        site = match / "review"
        site.mkdir(parents=True)
        (site / "data.js").write_text(f"window.MATCH = {json.dumps({'people': people, 'v': 'a'})};\n")
        (site / "index.html").write_text('<script src="data.js?v=a"></script>')

    a, b, c = (tmp_path / n for n in "abc")
    page(a, {"1": {"team": 1, "number": 3, "name": "Landy", "look": {"hair": "dark"}}})
    page(b, {"4": {"team": 2, "number": 7, "name": "Landy", "look": {"hair": "dark", "skin": 2}}, "5": {"team": 2, "number": 8, "name": "Zoé"}})
    page(c, {"1": {"team": 1, "number": 3, "name": "Zoé"}})
    (b / likeness.CHOICES).write_text(json.dumps({"Landy": {"hair": "dark"}}))
    hosted.record_hosted(b)
    hosted.record_hosted(c)
    monkeypatch.setattr(identity, "read_names", lambda match: {})
    monkeypatch.setattr(identity, "named", lambda table, names: {(1, 3): {"name": "Landy"}})

    review_answers.set_look(a, [], 1, 3, "hair", "red")

    assert web.page_data(b / "review")["people"]["4"]["look"] == {"hair": "red", "skin": 2}
    assert "look" not in web.page_data(b / "review")["people"]["5"]
    # Its own choice follows, a rebuild keeping it; the match without the player is untouched.
    assert likeness.chosen(b)["Landy"]["hair"] == "red"
    assert hosted.read_hosted(b)["behind"] and not hosted.read_hosted(c)["behind"]

    # A name from the jersey number alone is another player in each match.
    page(tmp_path / "d", {"1": {"team": 1, "number": 4, "name": "Joueur 9"}})
    page(tmp_path / "e", {"1": {"team": 2, "number": 2, "name": "Joueur 9"}})
    monkeypatch.setattr(identity, "named", lambda table, names: {(1, 4): {"name": "Joueur 9"}})
    review_answers.set_look(tmp_path / "d", [], 1, 4, "hair", "bald")
    assert web.page_data(tmp_path / "d" / "review")["people"]["1"]["look"] == {"hair": "bald"}
    assert "look" not in web.page_data(tmp_path / "e" / "review")["people"]["1"]


def test_a_change_made_while_an_upload_runs_leaves_its_page_late(tmp_path):
    from volleyball_stats import hosted, web

    site = tmp_path / "review"
    site.mkdir()
    (site / "data.js").write_text(f"window.MATCH = {json.dumps({'people': {'1': {'team': 1, 'number': 3}}, 'v': 'a'})};\n")
    (site / "index.html").write_text('<script src="data.js?v=a"></script>')
    taken = hosted.page_taken(tmp_path)
    web.patch_people(site, {"1": {"team": 1, "number": 3, "look": {"hair": "red"}}})

    hosted.record_hosted(tmp_path, taken)

    state = hosted.read_hosted(tmp_path)
    assert state["behind"] and state["changes"]


def test_the_commentary_an_upload_makes_leaves_its_page_on_time(tmp_path, monkeypatch):
    from volleyball_stats import hosted, speech

    site = tmp_path / "review"
    site.mkdir()
    (site / "data.js").write_text(f"window.MATCH = {json.dumps({'people': {'1': {'team': 1, 'number': 3}}, 'v': 'a'})};\n")
    taken = hosted.page_taken(tmp_path)
    # The upload's voice made, the review's next build takes it.
    monkeypatch.setattr(speech, "voice_index", lambda match, data, walls=(): {"lines": [[1.0, "a.mp3"]], "replay": {}, "folder": match})

    hosted.record_hosted(tmp_path, taken)
    (site / "data.js").write_text(f"window.MATCH = {json.dumps({'people': {'1': {'team': 1, 'number': 3}}, 'voice': True, 'v': 'b'})};\n")

    assert not hosted.read_hosted(tmp_path)["behind"]


class TestPageChanges:
    def test_each_changed_part_with_how_many_of_its_items(self):
        from volleyball_stats.hosted import page_changes

        sent = {"data": {"contacts": [{"f": 1}, {"f": 2}, {"f": 3}], "people": {"1": {"name": "Ana"}, "2": {"name": "Bob"}}, "ball3d": True, "club": {"name": "A"}, "positions": {"step": 1}, "name": "m"}, "code": {"page": "a", "list": "c"}}
        now = {"data": {"contacts": [{"f": 1}, {"f": 2, "type": "set"}, {"f": 3}, {"f": 4}], "people": {"1": {"name": "Ana"}, "2": {"name": "Bobby"}, "3": {}}, "ball3d": False, "club": {"name": "A", "favicon": "x"}, "positions": {"step": 2}, "name": "m"}, "code": {"page": "b", "list": "c"}}

        assert page_changes(sent, now) == [
            {"part": "ball3d", "count": None},
            {"part": "club", "count": 1, "keys": ["favicon"]},
            {"part": "contacts", "count": 2},
            {"part": "people", "count": 1, "keys": ["Bobby"]},
            {"part": "positions", "count": 1},
        ]
        assert page_changes(sent, sent) == []

    def test_the_tracks_without_a_name_renumbered_are_the_positions(self):
        from volleyball_stats.hosted import page_changes

        sent = {"data": {"people": {"1": {"name": "Ana"}, "2": {"team": 1}, "3": {"team": 2}}}, "code": "a"}
        now = {"data": {"people": {"1": {"name": "Ana"}, "2": {"team": 2}, "3": {"team": 1}}}, "code": "a"}

        assert page_changes(sent, now) == [{"part": "positions", "count": None}]

    def test_data_sent_before_its_format_was_written_is_format_1(self):
        from volleyball_stats.hosted import page_changes

        assert page_changes({"data": {"name": "m"}, "code": {}}, {"data": {"name": "m", "format": 1}, "code": {}}) == []
        assert page_changes({"data": {"name": "m"}, "code": {}}, {"data": {"name": "m", "format": 2}, "code": {}}) == [{"part": "format", "count": None}]

    def test_the_code_an_older_upload_recorded_is_no_change_of_its_page(self):
        from volleyball_stats.hosted import page_changes

        assert page_changes({"data": {}, "code": "a"}, {"data": {}, "code": {"page": "b", "list": "c"}}) == []

    def test_the_code_comes_with_the_commits_that_changed_it_once_each_at_most_five(self, monkeypatch):
        from volleyball_stats import git_check, hosted

        found = {"a": [(5, "e"), (3, "c")], "b": [(6, "f"), (5, "e"), (4, "d"), (2, "b"), (1, "a")]}
        monkeypatch.setattr(git_check, "commits_since", lambda path, since, now: found.get(since))

        assert hosted.code_commits({"page": "a", "list": "b"}, {"page": "x", "list": "y"}) == ["f", "e", "d", "c", "+2"]
        found["a"] = None
        assert hosted.code_commits({"page": "a", "list": "b"}, {"page": "x", "list": "y"}) is None

    def test_a_late_page_says_what_changed_since_the_upload(self, tmp_path):
        from volleyball_stats import hosted

        TestPageStamp.page(tmp_path, {"name": "m", "contacts": [{"f": 1}], "v": "a"})
        hosted.record_hosted(tmp_path)
        assert hosted.read_hosted(tmp_path)["changes"] is None
        TestPageStamp.page(tmp_path, {"name": "m", "contacts": [{"f": 1}, {"f": 2}], "v": "b"})

        state = hosted.read_hosted(tmp_path)
        assert state["behind"] and state["changes"] == [{"part": "contacts", "count": 1}]

    def test_the_code_no_longer_makes_a_page_late_the_site_s_code_does(self, tmp_path, monkeypatch):
        from volleyball_stats import hosted, matches

        scene = tmp_path / "scene3d.js"
        scene.write_text("a")
        monkeypatch.setitem(hosted.CODE_PAGES, "3d", scene)
        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        site = tmp_path / "site"
        site.mkdir()
        (tmp_path / matches.PUBLISH).write_text(json.dumps({"site": str(site)}))
        (site / matches.CODE).write_text(json.dumps({"code": matches.code_stamps()}))
        hosted.record_hosted(tmp_path)
        assert not hosted.read_hosted(tmp_path)["behind"]
        scene.write_text("b")

        assert not hosted.read_hosted(tmp_path, code=False)["behind"]
        state = hosted.read_hosted(tmp_path)
        assert state["behind"] and state["changes"] == [{"part": "siteCode", "count": None, "keys": ["3d"]}]
        assert hosted.site_code(site)["change"] == {"part": "code", "count": None, "keys": ["3d"]}

    def test_an_upload_recorded_with_the_code_of_each_page_is_late_only_for_its_data(self, tmp_path, monkeypatch):
        from volleyball_stats import hosted

        scene = tmp_path / "scene3d.js"
        scene.write_text("a")
        monkeypatch.setitem(hosted.CODE_PAGES, "3d", scene)
        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        pages = ("list", "page", "3d")
        (tmp_path / hosted.HOSTED_PAGE).write_text(json.dumps(hosted.page_content(tmp_path)))
        (tmp_path / hosted.HOSTED).write_text(json.dumps({"at": "2026-11-20T23:01:11", "stamp": hosted.page_stamp(tmp_path, pages), "pages": list(pages), "code": "x"}))
        assert not hosted.read_hosted(tmp_path)["behind"]
        scene.write_text("b")

        assert not hosted.read_hosted(tmp_path)["behind"]
        TestPageStamp.page(tmp_path, {"name": "n", "v": "b"})
        state = hosted.read_hosted(tmp_path)
        assert state["behind"] and state["changes"] == [{"part": "name", "count": None}]

    def test_an_upload_from_before_the_3d_views_stamp_is_judged_without_it(self, tmp_path, monkeypatch):
        from volleyball_stats import hosted

        scene = tmp_path / "scene3d.js"
        scene.write_text("a")
        monkeypatch.setitem(hosted.CODE_PAGES, "3d", scene)
        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        sent = hosted.page_content(tmp_path)
        del sent["code"]["3d"]
        (tmp_path / hosted.HOSTED_PAGE).write_text(json.dumps(sent))
        (tmp_path / hosted.HOSTED).write_text(json.dumps({"at": "2026-11-10T23:01:11", "stamp": hosted.page_stamp(tmp_path, hosted.OLD_STAMPED), "code": "x"}))
        scene.write_text("b")

        assert not hosted.read_hosted(tmp_path)["behind"]
        TestPageStamp.page(tmp_path, {"name": "n", "v": "b"})
        assert hosted.read_hosted(tmp_path)["changes"] == [{"part": "name", "count": None}]


    def test_a_page_rebuilt_by_the_uploads_code_is_not_late(self, tmp_path):
        from volleyball_stats import hosted

        # Uploaded with every match: the review's page as an older code built it, the upload by this one.
        TestPageStamp.page(tmp_path, {"name": "m", "brand": "x", "v": "a"})
        hosted.record_hosted(tmp_path)
        before = hosted.page_stamp(tmp_path)
        # Opened: the page rebuilt by this code.
        TestPageStamp.page(tmp_path, {"name": "m", "club": "x", "timeouts": [], "v": "b"})
        assert hosted.read_hosted(tmp_path)["behind"]

        hosted.restamp(tmp_path, before)
        assert not hosted.read_hosted(tmp_path)["behind"]

    def test_a_page_rebuilt_by_other_code_than_the_uploads_stays_late(self, tmp_path):
        from volleyball_stats import hosted

        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        hosted.record_hosted(tmp_path)
        saved = json.loads((tmp_path / hosted.HOSTED).read_text())
        (tmp_path / hosted.HOSTED).write_text(json.dumps({**saved, "code": "older"}))
        before = hosted.page_stamp(tmp_path)
        TestPageStamp.page(tmp_path, {"name": "m", "timeouts": [], "v": "b"})

        hosted.restamp(tmp_path, before)
        assert hosted.read_hosted(tmp_path)["behind"]

    def test_a_change_since_the_upload_stays_late(self, tmp_path):
        from volleyball_stats import hosted

        TestPageStamp.page(tmp_path, {"name": "m", "v": "a"})
        hosted.record_hosted(tmp_path)
        # An answer since: the page rebuilt then, its stamp no longer the upload's.
        TestPageStamp.page(tmp_path, {"name": "n", "v": "b"})
        before = hosted.page_stamp(tmp_path)
        TestPageStamp.page(tmp_path, {"name": "n", "timeouts": [], "v": "c"})

        hosted.restamp(tmp_path, before)
        assert hosted.read_hosted(tmp_path)["behind"]
