import json
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from volleyball_stats import files, review_answers
from volleyball_stats.identity import read_names
from volleyball_stats.review_answers import (
    card_numbers,
    chain,
    checked,
    constraints,
    corrections,
    follow_teams,
    let_go,
    load_roster,
    mark_odd,
    meeting,
    name_merges,
    path,
    piece_conflict,
    rally_answer,
    reanchor,
    remember,
    restorable,
    reviewed,
    save,
    set_name,
    set_photo,
    set_start,
    set_team,
    settled,
    suggest,
    supersede,
    superseded,
    touch_answer,
    write_names,
)
from volleyball_stats.review_questions import joins, teaches


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


class TestSave:
    def test_the_constraint_lists_follow_the_log(self, tmp_path):
        path = tmp_path / "identity_answers.json"
        log = [{"id": "a", "choice": "not_player", "not_player": [{"track": 1}]}, {"id": "b", "choice": "skip"}]

        save(path, log)

        assert json.loads(path.read_text(encoding="utf-8")) == {"same": [], "different": [], "not_player": [{"track": 1}], "cut": [], "team": [], "touch": [], "rally": [], "receiver": [], "partner": [], "action": [], "winner": [], "added": [], "end": [], "join": [], "split": [], "pinned": [], "locked": [], "redo": [], "referee": [], "wrong": [], "log": log}


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


    def test_a_name_removed_or_proposal_cleared_is_absent_until_given_again(self, tmp_path):
        table = [(1, 0, 10, 1, 3), (2, 0, 10, 1, 4)]
        write_names(tmp_path, [{"ref": {"track": 2, "frame": 5}, "name": "Léa", "jersey": None}])

        review_answers.name_absent(tmp_path, table, 1, None, "Anthony")
        review_answers.name_absent(tmp_path, table, 1, None, "anthony ")
        # Léa still named on another card: removing her from one says nothing.
        review_answers.name_absent(tmp_path, table, 1, None, "Léa")
        assert review_answers.read_absent(tmp_path) == [(1, "Anthony")]

        review_answers.name_absent(tmp_path, table, 1, "ANTHONY", None)
        assert review_answers.read_absent(tmp_path) == []


class TestRoster:
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])

    def test_the_player_wearing_the_number_read_is_suggested_first(self, tmp_path):
        path = tmp_path / "roster.json"
        remember(path, "m1", {(1, 1): {"name": "Julie", "jersey": 7}, (1, 2): {"name": "Léa", "jersey": 25}}, {(1, 1): self.a, (1, 2): self.b}, ["ASPOM", None])
        roster = load_roster(path)
        assert [s["name"] for s in suggest(self.a, roster, "ASPOM")][0] == "Julie"
        assert [s["name"] for s in suggest(self.a, roster, "ASPOM", number=25)][0] == "Léa"

    def test_proposes_each_roster_player_on_one_card_the_number_read_first(self):
        julie, lea = {"name": "Julie", "team": "ASPOM", "jersey": 7, "vectors": {"m1": [1.0, 0.0]}}, {"name": "Léa", "team": "ASPOM", "jersey": None, "vectors": {"m1": [0.0, 1.0]}}
        near = np.array([0.8, 0.6])
        # Both cards look most like Julie: the one wearing her number takes her, the other Léa.
        got = review_answers.propose({(1, 1): near, (1, 2): self.a}, {(1, 2): 7}, [julie, lea], ["ASPOM", None])
        assert got == {(1, 2): {"name": "Julie", "jersey": 7}, (1, 1): {"name": "Léa", "jersey": None}}

    def test_a_card_reading_another_number_than_a_player_wore_is_not_them_and_a_number_alone_names_it(self):
        julie = {"name": "Julie", "team": "ASPOM", "jersey": 7, "vectors": {"m1": [1.0, 0.0]}}
        assert review_answers.propose({(1, 1): self.a}, {(1, 1): 16}, [julie], ["ASPOM", None]) == {(1, 1): {"name": "Joueur 16", "jersey": 16}}
        assert review_answers.propose({(1, 1): self.a}, {}, [julie], ["ASPOM", None], taken={(1, "julie")}) == {}
        assert review_answers.propose({(1, 1): self.a}, {}, [julie], ["ASPOM", None], unless={(1, 1): {"Julie"}}) == {}
        assert review_answers.propose({(2, 1): self.a}, {}, [julie], ["ASPOM", "Other"]) == {}

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
        (folder / "teams.json").write_text(json.dumps({"teams": [{"name": t} for t in teams]}), encoding="utf-8")
        rows = [f"{k},0,10,{team},{number}" for k, (team, number) in enumerate(players)]
        (folder / "identities.csv").write_text("\n".join(["track,start_frame,end_frame,team,identity", *rows]) + "\n", encoding="utf-8")
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

    def test_a_rally_unchecked_by_an_edit_can_be_put_back_until_checked_or_applied(self):
        was = {"from": 90, "to": 190, "touches": [{"frame": 120, "player": "1:2"}]}
        log = [
            {"id": "edit:1", "checked": [100, 200], "applied": True},
            {"id": "edit:2", "unchecked": [100, 200], "was": {"100": was}, "applied": False},
        ]

        assert restorable(log) == {"100": was}
        assert restorable([*log, {"id": "edit:3", "choice": "report", "applied": False}]) == {"100": was}
        assert restorable([*log, {"id": "edit:3", "checked": [100], "applied": False}]) == {}
        assert restorable([*log, {"id": "edit:3", "unchecked": [100], "applied": False}]) == {}
        assert restorable([log[0], {**log[1], "applied": True}]) == {}

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
        (tmp_path / "teams.json").write_text(json.dumps({"teams": [{"name": "A", "colour": None, "jersey": "#151515"}, {"name": "B", "colour": None, "jersey": "#151515"}]}), encoding="utf-8")

        set_team(tmp_path, 2, " Les Rouges ", "rouge")
        assert json.loads((tmp_path / "teams.json").read_text(encoding="utf-8"))["teams"][1] == {"name": "Les Rouges", "colour": "#d22630", "jersey": "#151515"}
        set_team(tmp_path, 2, "", None)
        assert json.loads((tmp_path / "teams.json").read_text(encoding="utf-8"))["teams"][1] == {"name": None, "colour": None, "jersey": "#151515"}
        with pytest.raises(ValueError):
            set_team(tmp_path, 1, "A", "not a colour")


class TestSetPhoto:
    def test_keeps_the_picture_picked_by_the_players_name(self, tmp_path):
        table = [(1, 0, 30, 2, 5)]
        write_names(tmp_path, [{"ref": {"track": 1, "frame": 10}, "name": "Maeva", "jersey": None}])

        set_photo(tmp_path, table, 2, 5, 12, [1, 2, 3, 4])

        assert json.loads((tmp_path / "photo_choices.json").read_text(encoding="utf-8")) == {"Maeva": {"frame": 12, "box": [1, 2, 3, 4]}}

    def test_keeps_it_on_the_card_of_a_player_without_a_name(self, tmp_path):
        set_photo(tmp_path, [(1, 0, 30, 2, 5)], 2, 5, 12, [1, 2, 3, 4])

        assert json.loads((tmp_path / "photo_choices.json").read_text(encoding="utf-8")) == {"2:5": {"frame": 12, "box": [1, 2, 3, 4]}}


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
        assert json.loads((match / "teams.json").read_text(encoding="utf-8"))["sets"] == ["0:00", "0:40", "2:30"]
        set_start(match, 50.0, add=330.0)
        assert json.loads((match / "teams.json").read_text(encoding="utf-8"))["sets"] == ["0:00", "0:40", "2:30", "6:00"]

    def test_one_start_a_break_and_the_scores_follow_their_sets(self, tmp_path):
        match = self.match(tmp_path)

        # 2:30 and the break's middle, 3:10, start the same rallies: the new one takes its place.
        set_start(match, 50.0, add=200.0)
        saved = json.loads((match / "teams.json").read_text(encoding="utf-8"))
        assert saved["sets"] == ["0:00", "3:10"] and saved["scores"] == [None, None]
        set_start(match, 50.0, add=70.0)
        set_start(match, 50.0, remove="3:10")
        saved = json.loads((match / "teams.json").read_text(encoding="utf-8"))
        assert saved["sets"] == ["0:00", "0:40"] and saved["scores"] == [None, None]

    def test_keeps_a_kept_sets_score(self, tmp_path):
        match = self.match(tmp_path)

        set_start(match, 50.0, add=70.0)
        assert json.loads((match / "teams.json").read_text(encoding="utf-8"))["scores"] == [None, None, [25, 20]]

    def test_refuses_the_first_set_and_a_moment_after_the_last_rally(self, tmp_path):
        match = self.match(tmp_path)

        for change in ({"add": 5.0}, {"add": 500.0}, {"remove": "0:00"}, {"remove": "1:00"}):
            with pytest.raises(ValueError):
                set_start(match, 50.0, **change)
