import json
from types import SimpleNamespace

import numpy as np

from volleyball_stats.identity import read_names
from volleyball_stats.review import chain, constraints, meeting, path, name_merges, supersede, load_roster, mark_odd, range_of, reanchor, remember, save, set_name, suggest, with_review


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


class TestSave:
    def test_the_constraint_lists_follow_the_log(self, tmp_path):
        path = tmp_path / "identity_answers.json"
        log = [{"id": "a", "choice": "not_player", "not_player": [{"track": 1}]}, {"id": "b", "choice": "skip"}]

        save(path, log)

        assert json.loads(path.read_text()) == {"same": [], "different": [], "not_player": [{"track": 1}], "cut": [], "log": log}


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

        assert read_names(tmp_path) == [{"ref": {"track": 2, "frame": 5}, "name": "Léa", "jersey": None}, {"ref": {"track": 1, "frame": 5}, "name": "Julia", "jersey": None}]
        set_name(tmp_path, questions, 1, 4, "", None)
        assert [e["name"] for e in read_names(tmp_path)] == ["Julia"]


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
