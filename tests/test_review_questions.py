import json

import numpy as np
import pytest

from volleyball_stats import files, review_questions, web
from volleyball_stats.review_answers import receiver_answer, set_end
from volleyball_stats.review_questions import Questions, aces, doubtful, records, unnamed
from volleyball_stats.teams import match_end


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


class TestTogether:
    def test_names_the_named_players_of_the_team_on_court_during_more_than_a_share_of_the_card(self):
        questions = Questions.__new__(Questions)
        # Identity 1 on court 0-99; Paul 0-49, Jean 90-99, an unnamed player and Léa of the other team all along.
        questions.table = [(1, 0, 99, 1, 1), (2, 0, 49, 1, 2), (3, 90, 99, 1, 3), (4, 0, 99, 1, 4), (5, 0, 99, 2, 1)]
        names = {(1, 1): {"name": "Moi"}, (1, 2): {"name": "Paul"}, (1, 3): {"name": "Jean"}, (1, 4): {"name": None}, (2, 1): {"name": "Léa"}}

        assert questions.together(1, 1, names) == {"Paul"}


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


class TestNotOver:
    @staticmethod
    def page(kind="attack", result="point"):
        rally = {"key": 100, "start": 2.0, "end": 8.0, "set": 1}
        return {"fps": 50.0, "rallies": [rally], "contacts": [{"t": 4.0, "f": 200, "type": kind, "team": 1, "rally": 0, "result": result}, {"t": 5.0, "f": 250, "type": "floor", "team": None, "rally": 0, "result": "play"}]}

    def test_a_point_with_no_crossing_after_it_is_reported(self):
        assert [(r["kind"], r["time"]) for r in review_questions.not_over(self.page(), [100, 201])] == [("auto.notOver", 4.0)]

    def test_a_crossing_up_to_a_second_after_the_end_is_enough(self):
        assert review_questions.not_over(self.page(), [449]) == []

    def test_neither_a_block_a_fault_a_rally_to_replay_nor_one_checked(self):
        assert review_questions.not_over(self.page("block"), []) == []
        assert review_questions.not_over(self.page(result="error"), []) == []
        assert review_questions.not_over(self.page(), [], {100}) == []
        page = self.page()
        page["rallies"][0]["redo"] = True
        assert review_questions.not_over(page, []) == []


class TestMore:
    def test_only_pieces_as_like_the_card_as_more_like_are_offered(self, tmp_path):
        from volleyball_stats.review_questions import MORE_LIKE, Questions

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


class TestRecords:
    def test_each_trophy_s_record_is_a_report_to_confirm_on_its_touch_from_5_measured(self):
        def c(kind, t, **measure):
            return {"type": kind, "t": t, "f": round(t * 50), "person": 1, "rally": 0, **measure}

        jumps = [c("attack", k, jump=0.3 + k / 100) for k in range(5)]
        page = {"fps": 50, "contacts": [*jumps, c("serve", 10, speed=60), c("attack", 20, attackSpeed=70, jump=None)]}
        found = records(page)
        assert [(r["kind"], r["shown"], r["record"]) for r in found] == [("auto.record.jump", "34 cm", {"key": "jump", "frame": 200})]
        assert found[0]["time"] == 4 and found[0]["id"] == "auto:record:jump:200:34"


class TestNearest:
    def test_names_the_players_nearest_the_ball_nearest_first_on_both_sides(self):
        q = Questions.__new__(Questions)
        q.fps = 50.0
        # Frame 10: track 1 (identity 4 of team 1) beside the ball, track 2 (team 2's 7) farther, track 3 unnamed.
        q.frame_of = np.array([10, 10, 10])
        q.track_of = np.array([1, 2, 3])
        q.box_of = np.array([[100, 100, 150, 300], [400, 100, 450, 300], [120, 100, 170, 300]])
        q.court_of = np.array([[-3.0, 2.0], [3.0, 2.0], [-2.0, 2.0]])
        q.left_of = np.array([True, False, True])
        q.table = [(1, 0, 99, 1, 4), (2, 0, 99, 2, 7), (3, 0, 99, 1, 0)]
        q.ball = (np.array([5, 40]), np.array([[160.0, 200.0], [0.0, 0.0]]))

        assert q.nearest(10, "pass") == ["1:4", "2:7"]
        # No ball seen near the frame: no one.
        assert q.nearest(25, "pass") == []
