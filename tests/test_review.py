import json
from types import SimpleNamespace

import numpy as np
import pytest

from volleyball_stats.identity import read_names
from volleyball_stats.review import APPLIED, Questions, aces, report_answer, report_question, reports, unnamed, chain, constraints, doubtful, rally_answer, meeting, path, name_merges, supersede, load_roster, mark_odd, range_of, reanchor, receiver_answer, remember, save, set_name, set_photo, set_team, settled, state, suggest, touch_answer, undo, waiting, with_review, write_names


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
        assert ref == {"start": 2000, "touches": {"2050": 2, "2100": 1}}
        assert report_question({"time": 100.0, "clip": {"time": 12.0}}, self.page, 50.0)[1]["start"] == 500

    def test_corrections_become_touch_action_rally_and_winner_answers(self):
        ref = {"start": 2000, "touches": {"2050": 2, "2100": 1}}
        changes = {"touches": [{"frame": 2050, "player": "none"}, {"frame": 2100, "player": "1:4", "result": "play", "type": "bogus"}], "winner": 1, "play": False}

        out = report_answer(ref, changes, {(1, 4): {"name": "Léa"}})

        assert out["touch"] == [{"frame": 2050, "team": 2, "identity": None, "name": None}, {"frame": 2100, "team": 1, "identity": 4, "name": "Léa"}]
        assert out["action"] == [{"frame": 2100, "result": "play"}]
        assert (out["rally"], out["winner"]) == ([{"start": 2000, "play": False}], [{"start": 2000, "winner": 1}])
        assert report_answer({"start": None, "touches": {}}, {"winner": 2, "touches": [{"frame": 1, "type": "set"}]}, {}) == {}


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
        assert receiver_answer(ace, "skip", {}) == {}


class TestSave:
    def test_the_constraint_lists_follow_the_log(self, tmp_path):
        path = tmp_path / "identity_answers.json"
        log = [{"id": "a", "choice": "not_player", "not_player": [{"track": 1}]}, {"id": "b", "choice": "skip"}]

        save(path, log)

        assert json.loads(path.read_text()) == {"same": [], "different": [], "not_player": [{"track": 1}], "cut": [], "touch": [], "rally": [], "receiver": [], "action": [], "winner": [], "log": log}


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

        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": False}
        assert waiting(tmp_path, [])["changed"]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 5}, "name": "Julie", "jersey": None}])
        assert waiting(tmp_path, log) == {"pending": 0, "changed": False, "namesPending": True}
        (tmp_path / "jerseys.csv").write_text("frame,track,number\n")
        assert waiting(tmp_path, log)["changed"]


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
