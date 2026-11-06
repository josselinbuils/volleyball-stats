import base64
import json
import struct
from pathlib import Path

import cv2
import numpy as np
import pytest

from volleyball_stats.court import Calibration
from volleyball_stats import web
from volleyball_stats.teams import COLOURS
from volleyball_stats.web import acted, credited, frames_index, labelled, followed, served_next, ball_near, ball_track, crossed, ended, brand, brief, contacts, rewon, drop_rallies, merge_rallies, split_rallies, match_data, people, photos, player_samples, playing_time, publish, receivers, result, settle, spot, touched, track_feet, with_added, write_site, zone, zone_cells

# Pixels are court metres.
IDENTITY = Calibration(np.eye(3))


class TestSpot:
    boxes = np.array([[100.0, 50.0, 140.0, 200.0], [300.0, 80.0, 330.0, 180.0], [105.0, 120.0, 135.0, 160.0]])
    feet = np.array([[-3.0, 1.0], [2.0, -2.0], [-4.0, -3.0]])

    def test_places_a_floor_contact_at_the_balls_floor_projection(self):
        assert spot("floor", (1.5, -2.0), self.boxes, self.feet, IDENTITY, 15) == (1.5, -2.0)

    def test_takes_the_feet_of_the_player_under_the_ball_whose_head_is_nearest(self):
        assert spot("attack", (120.0, 40.0), self.boxes, self.feet, IDENTITY, 15) == (-3.0, 1.0)
        assert spot("dig", (120.0, 125.0), self.boxes, self.feet, IDENTITY, 15) == (-4.0, -3.0)

    def test_takes_the_nearest_player_horizontally_when_none_is_under_the_ball(self):
        assert spot("serve", (250.0, 60.0), self.boxes, self.feet, IDENTITY, 15) == (2.0, -2.0)

    def test_has_no_position_without_players(self):
        assert spot("set", (120.0, 40.0), np.empty((0, 4)), np.empty((0, 2)), IDENTITY, 15) is None


class TestTrackFeet:
    players = {
        10: [{"track": "4", "court_x": "1.0", "court_y": "2.0"}, {"track": "5", "court_x": "-3.0", "court_y": "0.0"}],
        14: [{"track": "4", "court_x": "3.0", "court_y": "4.0"}],
    }

    def test_takes_the_tracks_feet_at_the_frame(self):
        assert track_feet(4, 10, self.players, 2) == (1.0, 2.0)

    def test_interpolates_over_a_detection_gap(self):
        assert track_feet(4, 12, self.players, 2) == (2.0, 3.0)

    def test_has_no_position_when_the_track_is_not_that_close(self):
        assert track_feet(5, 13, self.players, 2) is None
        assert track_feet(7, 10, self.players, 2) is None


class TestZone:
    def test_numbers_the_left_half_from_its_end_line(self):
        # Facing the net, the left team's left hand is toward the far sideline (y < 0).
        assert [zone(-1.5, y) for y in (-3, 0, 3)] == [4, 3, 2]
        assert [zone(-6.0, y) for y in (-3, 0, 3)] == [5, 6, 1]

    def test_mirrors_the_right_half(self):
        assert [zone(1.5, y) for y in (-3, 0, 3)] == [2, 3, 4]
        assert [zone(6.0, y) for y in (-3, 0, 3)] == [1, 6, 5]

    def test_puts_points_off_the_court_in_the_nearest_zone(self):
        assert zone(-11.0, 5.5) == 1  # a server behind the end line, near corner
        assert zone(10.5, -6.0) == 1

    def test_cells_cover_both_halves_with_each_zone_once(self):
        cells = zone_cells()
        assert sorted(c["zone"] for c in cells if c["x"] < 0) == [1, 2, 3, 4, 5, 6]
        assert sorted(c["zone"] for c in cells if c["x"] >= 0) == [1, 2, 3, 4, 5, 6]
        assert sum(c["w"] * c["h"] for c in cells) == 18 * 9


class TestResult:
    attack = {"type": "attack", "side": "right"}

    def landing(self, side: str, x: float, y: float = 0.0) -> dict:
        return {"type": "floor", "side": side, "x": x, "y": y}

    def test_is_a_point_when_the_ball_lands_in_the_other_court_the_line_included_as_in_the_score(self):
        assert result(self.attack, self.landing("left", -5.0, 2.0)) == "point"
        assert result(self.attack, self.landing("left", -9.2)) == "point"

    def test_is_an_error_when_the_ball_lands_out_on_its_own_side_at_the_foot_of_the_net_or_in_it(self):
        assert result(self.attack, self.landing("left", -9.5)) == "error"
        assert result(self.attack, self.landing("left", -5.0, 4.9)) == "error"
        assert result(self.attack, self.landing("right", 4.0)) == "error"
        assert result(self.attack, self.landing("left", -0.8)) == "error"
        assert result(self.attack, {"type": "net", "side": "right", "x": 0.5, "y": 0.0}) == "error"

    def test_a_block_dropping_at_the_foot_of_the_net_is_its_point_as_in_the_score(self):
        assert result({"type": "block", "side": "left"}, self.landing("right", 0.5)) == "point"

    def test_is_in_play_when_the_ball_is_played_again_or_the_rally_ends(self):
        assert result(self.attack, {"type": "dig", "side": "left", "x": -6.0, "y": 0.0}) == "play"
        assert result(self.attack, None) == "play"
        # The rally goes on after it: no landing, a serve brushing the net on its way over.
        assert result({"type": "serve", "side": "left"}, {"type": "net", "side": "left", "x": -0.5, "y": 0.0}, played=True) == "play"


class TestContacts:
    def test_builds_the_rallies_contacts_with_positions_zones_and_results(self):
        typed = [
            {"frame": "8", "x": "-10", "y": "3", "type": "serve", "side": "left"},  # in the window's lead
            {"frame": "40", "x": "6", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "45", "x": "7", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "100", "x": "8", "y": "0", "type": "serve", "side": "right"},
        ]
        players = {8: [{"x1": "-10.5", "y1": "1", "x2": "-9.5", "y2": "3", "court_x": "-10.4", "court_y": "3.1"}]}

        out = contacts(typed, [(10, 60), (100, 130)], players, 10.0, IDENTITY, 15)

        assert [(c["t"], c["rally"], c["type"]) for c in out] == [(0.8, 0, "serve"), (4.0, 0, "floor"), (4.5, 0, "floor"), (10.0, 1, "serve")]
        assert (out[0]["x"], out[0]["y"], out[0]["zone"]) == (-10.4, 3.1, 1)
        # The floor contact is the ball's floor projection; the dead ball after it has no position.
        assert (out[1]["x"], out[1]["y"]) == (6.0, -1.0)
        assert out[2]["x"] is None and out[2]["zone"] is None
        assert out[3]["x"] is None  # no player at that frame
        assert [c["result"] for c in out] == ["point", "play", "play", "play"]
        assert [c["person"] for c in out] == [None, None, None, None]
        assert [c["team"] for c in out] == [None, None, None, None]

    def test_an_ace_names_the_receiver_nearest_to_where_it_lands(self):
        typed = [
            {"frame": "10", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
            {"frame": "30", "x": "5", "y": "2", "type": "floor", "side": "right"},
        ]
        feet = lambda track, x, y: {"x1": "0", "y1": "0", "x2": "1", "y2": "1", "court_x": str(x), "court_y": str(y), "track": str(track)}
        players = {10: [feet(1, -8.0, 0.0)], 30: [feet(1, -2.0, 2.0), feet(5, 7.0, -3.0), feet(6, 4.0, 3.0)]}

        out = contacts(typed, [(5, 40)], players, 10.0, IDENTITY, 15)
        receivers(out, typed, players)

        assert out[0]["result"] == "point"
        assert out[0]["receiver"] == 6
        assert "receiver" not in out[1]

    def test_an_ace_without_a_landing_across_the_net_has_the_receiver_the_review_said_else_none_known(self):
        typed = [
            {"frame": "10", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
            {"frame": "20", "x": "-4", "y": "2", "type": "net", "side": "left"},
            {"frame": "50", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
        ]
        players = {20: [{"x1": "0", "y1": "0", "x2": "1", "y2": "1", "court_x": "-3.0", "court_y": "2.0", "track": "1"}]}
        out = contacts(typed, [(5, 40), (45, 80)], players, 10.0, IDENTITY, 15)
        # The points step made both serves aces: each was its rally's last touch and won it.
        out[0]["result"] = out[2]["result"] = "point"
        said = lambda track, frame, given=None: given[1] if given else track  # noqa: E731

        receivers(out, typed, players, said, {50: (2, 4)})
        assert "receiver" not in out[0]
        assert out[2]["receiver"] == 4

        receivers(out, typed, players, said, {10: None})
        assert out[0]["receiver"] is None

    def test_the_review_s_winners_count_their_set_s_score_again(self):
        rallies = [{"key": 100, "set": 1, "winner": 1, "score": [1, 0]}, {"key": 300, "set": 1, "winner": 1, "score": [2, 0]}, {"key": 500, "set": 2, "winner": 2, "score": [0, 1]}]

        rewon(rallies, {100: 2, 500: 2})

        assert [(r["winner"], r["score"]) for r in rallies] == [(2, [0, 1]), (1, [1, 1]), (2, [0, 1])]

    def test_an_attack_or_a_block_the_other_team_loses_is_a_point_an_attack_blocked_for_one_a_fault(self):
        def c(kind, team, rally, result="play"):
            return {"type": kind, "team": team, "rally": rally, "result": result}

        found = [
            c("attack", 1, 0), c("dig", 2, 0, "error"),  # the dig lets it go
            c("attack", 1, 1), c("block", 2, 1, "error"),  # off the block
            c("block", 1, 2), c("dig", 2, 2, "error"),  # the block's ball lost
            c("attack", 1, 3), c("block", 2, 3, "point"),  # blocked
            c("attack", 1, 4), c("dig", 2, 4), c("floor", None, 4),  # kept in play
            c("attack", 1, 5), c("dig", 2, 5, "error"),  # in play in the review: the same
            c("attack", 1, 6, "error"), c("dig", 2, 6, "error"),  # a fault in the review stays
            c("attack", 1, 7), c("block", 2, 7, "point"),  # in play in the review: the same
            c("attack", 1, 8), c("dig", 2, 8, "error"), c("set", 2, 8, "error"),  # touches after it
            c("attack", 1, 9), c("attack", 2, 9, "error"),  # the other team's own attack
            c("serve", 2, 10), c("pass", 1, 10, "error"),  # the first receiver loses it: an ace
            c("serve", 2, 11), c("pass", 1, 11, "error"), c("set", 1, 11, "error"),  # another touch after it: no ace
            c("serve", 2, 12), c("pass", 1, 12), c("floor", None, 12),  # kept in play
        ]
        typed = [{"frame": str(k)} for k in range(len(found))]

        credited(found, typed)

        assert [x["result"] for x in found if x["type"] in ("attack", "serve") or x["team"] == 1 and x["type"] == "block"] == [
            "point", "point", "point", "error", "play", "point", "error", "error", "play", "play", "error", "point", "play", "play",
        ]
        # The labels stay what happened.
        assert {labelled(x) for x in found if x["type"] == "attack" and x["rally"] in (1, 3, 5, 7)} == {"play"}
        assert labelled(next(x for x in found if x["type"] == "attack" and x["rally"] == 6)) == "error"

    def test_the_review_s_types_and_results_replace_the_touches(self):
        found = [{"type": "serve", "result": "point"}, {"type": "pass", "result": "play"}]

        acted(found, [{"frame": "10"}, {"frame": "20"}], {10: {"type": "pass", "result": "error"}})

        assert found == [{"type": "pass", "result": "error"}, {"type": "pass", "result": "play"}]

    def test_a_player_on_the_court_only_seconds_in_a_set_touches_nothing_known_there(self):
        table = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": 4}, 2: {"team": 1, "number": None}}
        times = {0: {"1": 7.0, "2": 300.0}, 1: {"1": 280.0}}
        found = [
            {"person": 0, "set": 1},  # 7 s in set 1: a slip
            {"person": 0, "set": 2},
            {"person": 0, "set": 1},  # the review said who touched it
            {"person": 2, "set": 1},  # a track without identity: already nobody's
            {"person": 1, "set": 1, "receiver": 0},  # an ace missed by the slip
        ]
        typed = [{"frame": str(f)} for f in (10, 20, 30, 40, 50)]

        brief(found, typed, table, times, {30: (1, 3)}, {})

        assert [(c["person"], c.get("brief")) for c in found] == [(None, True), (0, None), (0, None), (2, None), (1, None)]
        assert "receiver" not in found[4]
        brief(found, typed, table, {}, {}, {})  # without players' times, nothing changes
        assert found[1]["person"] == 0

    def test_a_receiver_of_the_serve_s_own_team_makes_it_their_missed_reception(self):
        # The window started late: its first touch, the left team's, was taken for a serve.
        typed = [{"frame": "10", "x": "-5", "y": "0", "type": "serve", "side": "left", "track": "1", "team": "2"}]
        out = contacts(typed, [(5, 40)], {}, 10.0, IDENTITY, 15)
        out[0]["result"] = "point"
        said = lambda track, frame, given=None: given[1] if given else track  # noqa: E731

        receivers(out, typed, {}, said, {10: (2, 7)})

        assert (out[0]["type"], out[0]["result"], out[0]["person"]) == ("pass", "error", 7)
        assert "receiver" not in out[0]

    def test_places_an_attributed_contact_at_its_players_feet_else_under_the_ball(self):
        typed = [
            {"frame": "10", "x": "0", "y": "0", "type": "attack", "side": "left", "track": "7"},
            {"frame": "20", "x": "0", "y": "0", "type": "dig", "side": "right", "track": "9", "team": "2"},  # track not found
        ]
        under = {"x1": "-1", "y1": "-1", "x2": "1", "y2": "1", "court_x": "-1.0", "court_y": "0.5", "track": "8"}
        players = {
            10: [under, {"x1": "5", "y1": "5", "x2": "6", "y2": "7", "court_x": "-4.0", "court_y": "2.0", "track": "7"}],
            20: [{**under, "court_x": "2.0"}],
        }

        out = contacts(typed, [(5, 30)], players, 10.0, IDENTITY, 15)

        assert [(c["x"], c["y"], c["person"], c["team"]) for c in out] == [(-4.0, 2.0, 7, None), (2.0, 0.5, 9, 2)]


class TestPlayerSamples:
    def test_keeps_every_steps_frame_of_the_video_as_track_and_feet_rounded_to_the_centimetre(self):
        rows = [
            {"frame": "3", "track": "5", "court_x": "3.14159", "court_y": "-1.005"},
            {"frame": "3", "track": "2", "court_x": "-2.0", "court_y": "1.234"},
            {"frame": "4", "track": "2", "court_x": "-2.1", "court_y": "1.2"},
            {"frame": "9", "track": "2", "court_x": "-4.0", "court_y": "0.0"},
        ]

        assert player_samples(rows, 3, 10) == [[], [5, 3.14, -1.0, 2, -2.0, 1.23], [], [2, -4.0, 0.0]]


class TestPeople:
    def test_one_player_per_identity_across_its_tracks_and_one_per_track_without_identity(self):
        # Track 1 is identity 3 then, past a crowd at frame 50, identity 4; track 2 continues 4.
        identities = [(1, 0, 49, 1, 3), (1, 51, 90, 1, 4), (2, 100, 200, 1, 4)]

        who, table = people({1: 1, 2: 1, 5: 2}, identities)

        assert [who(1, 10), who(1, 60), who(2, 150), who(5, 10), who(None, 10)] == [0, 1, 1, 2, None]
        assert table == {
            0: {"team": 1, "number": 3, "jersey": None, "name": None},
            1: {"team": 1, "number": 4, "jersey": None, "name": None},
            2: {"team": 2, "number": None, "jersey": None, "name": None},
        }

    def test_an_identity_takes_the_name_and_jersey_number_the_user_gave_it(self):
        who, table = people({1: 1}, [(1, 0, 49, 1, 3)], {(1, 3): {"name": "Julie", "jersey": 7}})

        assert who(1, 10) == 0
        assert who(None, 80, (1, 3)) == 0
        assert table == {0: {"team": 1, "number": 3, "jersey": 7, "name": "Julie"}}

    def test_a_touch_goes_to_the_player_the_review_named_by_name_else_by_number(self, tmp_path):
        touches = [{"frame": 5, "team": 2, "identity": 3, "name": "Julie"}, {"frame": 9, "team": 1, "identity": 4, "name": None}, {"frame": 12, "team": 1, "identity": None, "name": None}]
        (tmp_path / "identity_answers.json").write_text(json.dumps({"touch": touches}))

        assert touched(tmp_path, {(2, 7): {"name": "Julie", "jersey": None}}) == {5: (2, 7), 9: (1, 4), 12: None}


class TestPlayingTime:
    def test_counts_each_players_time_on_the_court_in_the_rallies_by_set(self):
        # 10 fps, a sample every 5 frames: frames 0, 5, 10, 15, 20.
        samples = [[1, 0.0, 0.0], [1, 11.5, 0.0, 2, 0.0, 6.0], [1, 0.0, 0.0, 2, 3.0, 4.0], [1, 13.0, 0.0], [2, 0.0, 0.0]]

        # Rallies over frames 3-12 (set 1) and 18-20 (set 2): player 1 serving 2.5 m behind the end
        # line counts, 4 m behind does not; player 2 on the bench 1.5 m out does not.
        found = playing_time(samples, 5, [(3, 12), (18, 20)], [1, 2], 10.0)

        assert found == {1: {"1": 1.0}, 2: {"1": 0.5, "2": 0.5}}


class TestBallTrack:
    def test_keeps_the_balls_place_seen_in_the_rallies_every_step(self, tmp_path):
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n20,40\n")
        rows = [f"{f},{int(f != 32)},{f * 10},{f * 5}" for f in range(0, 60, 2)]
        (tmp_path / "ball.csv").write_text("frame,visible,x,y\n" + "\n".join(rows) + "\n")

        # 10 fps: every frame, the rally from 3 frames before its start; frame 32 unseen.
        found = ball_track(tmp_path, (1000, 500), 10.0)

        frames = found["samples"][::3]
        assert frames == [18, 20, 22, 24, 26, 28, 30, 34, 36, 38, 40]
        assert found["samples"][:3] == [18, 0.18, 0.18] and found["fps"] == 10.0


class TestEnded:
    def test_a_window_ends_where_the_review_said(self):
        assert ended([(100, 200), (300, 400)], [{"start": 300, "end": 450}, {"start": 999, "end": 1}]) == [(100, 200), (300, 450)]


class TestCrossed:
    def test_a_touch_given_to_the_other_team_changes_sides_without_its_track(self):
        row = {"frame": "10", "team": "1", "side": "left", "track": "3", "identity": "4"}

        assert crossed(row, (2, 5)) == {"frame": "10", "team": "2", "side": "right", "track": "", "identity": ""}
        assert crossed(row, (1, 5)) is row and crossed(row, None) is row
        assert crossed({"frame": "10", "team": "", "side": "left"}, (2, 5))["side"] == "left"


class TestWithAdded:
    def test_a_touch_added_is_a_row_at_the_ball_on_its_team_s_side_its_window_lasting_to_it(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n148,1,10,20\n150,0,,\n153,1,30,40\n260,1,50,60\n")
        windows, rows = [(100, 200), (300, 400)], [{"left": "2"}, {"left": ""}]
        typed = [{"frame": "120", "type": "serve"}, {"frame": "330", "type": "serve"}]
        added = [
            {"start": 100, "frame": 150, "team": 1, "type": "pass"},
            {"start": 100, "frame": 260, "team": 2, "type": "attack"},
            {"start": 300, "frame": 380, "team": 1, "type": "set"},
            {"start": 300, "frame": 250, "team": 1, "type": "set"},
            {"start": 500, "frame": 520, "team": 1, "type": "set"},
            {"start": 100, "frame": 120, "team": 1, "type": "set"},
        ]

        w, rows_out = with_added(windows, rows, typed, added, ball, 5)

        # Past its window's end or before its start the touch stretches it; in a window gone, or
        # where a touch was already found, it is left out.
        assert w == [(100, 260), (250, 400)]
        assert [(r["frame"], r["type"], r.get("side"), r.get("x"), r.get("y")) for r in rows_out] == [
            ("120", "serve", None, None, None),
            ("150", "pass", "right", "10", "20"),
            ("250", "set", "left", "", ""),
            ("260", "attack", "left", "50", "60"),
            ("330", "serve", None, None, None),
            ("380", "set", "left", "", ""),
        ]

    def test_a_touch_goes_for_one_added_near_it_by_the_team_the_review_gave_it(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        typed = [{"frame": "120", "type": "attack", "team": "2"}]
        added = [{"start": 100, "frame": 126, "team": 2, "type": "dig"}]

        _, rows = with_added([(100, 200)], [{"left": "2"}], typed, added, ball, 5, 20, 10)
        assert [r["type"] for r in rows] == ["dig"]

        # The attack is the other team's: the dig does not take its place.
        _, rows = with_added([(100, 200)], [{"left": "2"}], typed, added, ball, 5, 20, 10, said={120: 1})
        assert [r["type"] for r in rows] == ["attack", "dig"]


    def test_a_row_at_a_frame_the_review_gave_stays_near_an_older_answer(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        typed = [{"frame": "120", "x": "1", "y": "2", "type": "serve", "side": "left", "track": "", "gap": "", "team": "1", "identity": ""}]
        added = [{"start": 130, "frame": 122, "team": 1, "type": "serve"}, {"start": 130, "frame": 120, "team": 1, "type": "serve"}]

        _, rows = with_added([(130, 200)], [{"left": "1"}], typed, added, ball, 5, 20, 10, 16)

        assert "120" in [str(r["frame"]) for r in rows]

    def test_a_serve_added_after_a_split_stays_in_the_rally_it_names(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        # A floor row just before the split, in the part before it and in the lead of the one after it.
        typed = [{"frame": "552", "x": "1", "y": "2", "type": "net", "side": "left", "track": "", "gap": "", "team": "1", "identity": ""}]
        added = [{"start": 554, "frame": 556, "team": 1, "type": "serve"}]

        windows, rows = with_added([(61, 553), (554, 687)], [{"left": "1"}, {"left": "1"}], typed, added, ball, 5, 20, 10, 16)

        assert windows == [(61, 553), (554, 687)]
        assert [(r["frame"], r["type"]) for r in rows] == [("556", "serve")]

    def test_a_block_and_a_touch_added_right_after_or_before_it_are_two(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        windows, rows = [(100, 200)], [{"left": "2"}]

        def kept(typed, added, **said):
            return [(r["frame"], r["type"]) for r in with_added(windows, rows, typed, added, ball, 5, 20, 10, **said)[1]]

        block = [{"frame": "120", "type": "block", "team": "1"}]
        assert kept(block, [{"start": 100, "frame": 126, "team": 1, "type": "dig"}]) == [("120", "block"), ("126", "dig")]
        dig = [{"frame": "126", "type": "dig", "team": "1"}]
        assert kept(dig, [{"start": 100, "frame": 120, "team": 1, "type": "block"}]) == [("120", "block"), ("126", "dig")]
        # The block found again stays one touch; a type the review set counts.
        assert kept(block, [{"start": 100, "frame": 126, "team": 1, "type": "block"}]) == [("126", "block")]
        found_as_dig = [{"frame": "120", "type": "dig", "team": "1"}]
        assert kept(found_as_dig, [{"start": 100, "frame": 126, "team": 1, "type": "dig"}], kinds={120: "block"}) == [("120", "dig"), ("126", "dig")]

    def test_a_serve_added_stays_in_the_rally_named_when_the_one_it_replaces_starts_another(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        # A rally started on the serve the pipeline found, the next one 16 frames later (a lead of 16).
        windows, rows = [(100, 100), (116, 300)], [{"left": "2"}, {"left": "2"}]
        typed = [{"frame": "100", "type": "serve", "team": "2"}, {"frame": "150", "type": "pass", "team": "1"}]
        added = [{"start": 100, "frame": 40, "team": 1, "type": "serve"}, {"start": 116, "frame": 108, "team": 2, "type": "serve"}]

        w, out = with_added(windows, rows, typed, added, ball, 5, 20, 10, 16)

        assert w == [(40, 100), (108, 300)]
        assert [r["frame"] for r in out] == ["40", "108", "150"]

    def test_two_touches_named_as_different_players_stay_two(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        typed = [{"frame": "120", "type": "block", "team": "1"}]
        added = [{"start": 100, "frame": 126, "team": 1, "type": "block"}]

        def kept(**named):
            return [r["frame"] for r in with_added([(100, 200)], [{"left": "2"}], typed, added, ball, 5, 20, 10, **named)[1]]

        assert kept(named={120: "Léa", 126: "Anaïs"}) == ["120", "126"]
        # The same player, or one touch not named: the same touch found again.
        assert kept(named={120: "Léa", 126: "Léa"}) == ["126"]
        assert kept(named={126: "Anaïs"}) == ["126"]

    def test_a_playing_fault_added_replaces_no_touch_found_near_it(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n")
        typed = [{"frame": "120", "type": "dig", "team": "1"}, {"frame": "125", "type": "floor"}]
        added = [{"start": 100, "frame": 110, "team": 1, "type": "fault"}]

        _, rows = with_added([(100, 200)], [{"left": "2"}], typed, added, ball, 5, 20, 10)

        assert [(r["frame"], r["type"]) for r in rows] == [("110", "fault"), ("120", "dig"), ("125", "floor")]

    def test_a_touch_added_twice_is_the_last_answers(self, tmp_path):
        added = [{"start": 100, "frame": 150, "team": 1, "type": "pass"}, {"start": 100, "frame": 150, "team": 2, "type": "dig"}]

        _, rows_out = with_added([(100, 200)], [{"left": "1"}], [], added, tmp_path / "none.csv", 5)

        assert [(r["frame"], r["type"], r["team"]) for r in rows_out] == [("150", "dig", "2")]

    def test_a_touch_found_again_near_an_added_one_goes(self, tmp_path):
        typed = [
            {"frame": "118", "type": "serve", "team": "1"},
            {"frame": "152", "type": "floor", "team": "2"},
            {"frame": "160", "type": "block", "team": "2"},
            {"frame": "300", "type": "set", "team": "1"},
        ]
        added = [{"start": 100, "frame": 110, "team": 1, "type": "serve"}, {"start": 100, "frame": 150, "team": 1, "type": "attack"}]

        _, rows_out = with_added([(100, 400)], [{"left": "1"}], typed, added, tmp_path / "none.csv", 5, 10, 3)

        # The serve and the floor were the added touches; the block is the other team's.
        assert [r["frame"] for r in rows_out] == ["110", "150", "160", "300"]

    def test_a_touch_added_takes_the_window_of_the_row_it_replaces(self, tmp_path):
        # Added to the first window before a rerun; the rerun found it at the second's start.
        typed = [{"frame": "305", "type": "serve", "team": "2"}]
        added = [{"start": 100, "frame": 298, "team": 2, "type": "serve"}]

        w, rows_out = with_added([(100, 299), (310, 400)], [{"left": "1"}, {"left": "1"}], typed, added, tmp_path / "none.csv", 5, 10, 3, 6)

        assert w == [(100, 299), (298, 400)]
        assert [r["frame"] for r in rows_out] == ["298"]

    def test_a_rally_is_won_by_the_next_server_when_it_soon_follows(self):
        rallies = [{"set": 1, "start": 0.0, "end": 10.0, "winner": 1}, {"set": 1, "start": 30.0, "end": 40.0, "winner": 1}, {"set": 1, "start": 100.0, "end": 110.0, "winner": 1}]
        found = [{"type": "serve", "team": 2, "rally": 1}, {"type": "serve", "team": 2, "rally": 2}]

        served_next(rallies, found, 40.0)

        # The third serve comes 60 s later: a rally may have been missed in between.
        assert [r["winner"] for r in rallies] == [2, 1, 1]

    def test_ball_near_takes_the_nearest_place_seen(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n97,1,1,1\n99,0,,\n102,1,2,2\n")

        assert ball_near(ball, [100, 200], 3) == {100: ("2", "2")}
        assert ball_near(tmp_path / "none.csv", [100], 3) == {}


class TestDropRallies:
    def test_a_rally_said_to_be_none_goes_with_its_contacts_and_points_found_by_its_key(self):
        # The second one's start moved back to a serve added.
        windows = [(100, 200), (280, 400), (500, 600), (700, 800)]
        rows = [{"set": "1", "start_frame": "100"}, {"set": "1", "start_frame": "300"}, {"set": "1", "start_frame": "500"}, {"set": "2", "start_frame": "700"}]
        scores = [
            {"winner": "1", "score_1": "1", "score_2": "0"},
            {"winner": "2", "score_1": "1", "score_2": "1"},
            {"winner": "1", "score_1": "2", "score_2": "1"},
            {"winner": "2", "score_1": "0", "score_2": "1"},
        ]
        actions = [{"frame": "150"}, {"frame": "290"}, {"frame": "350"}, {"frame": "550"}]

        w, r, s, a = drop_rallies(windows, rows, scores, actions, {300}, 20)

        assert w == [(100, 200), (500, 600), (700, 800)] and len(r) == 3
        assert [(p["score_1"], p["score_2"]) for p in s] == [("1", "0"), ("2", "0"), ("0", "1")]
        assert [x["frame"] for x in a] == ["150", "550"]


class TestMergeRallies:
    def test_a_window_said_to_join_the_next_one_of_its_set_takes_its_end_and_point(self):
        windows = [(100, 200), (300, 400), (500, 600), (700, 800)]
        rows = [{"set": "1", "start_frame": "100"}, {"set": "1", "start_frame": "300"}, {"set": "1", "start_frame": "500"}, {"set": "2", "start_frame": "700"}]
        scores = [
            {"winner": "1", "score_1": "1", "score_2": "0"},
            {"winner": "2", "score_1": "1", "score_2": "1"},
            {"winner": "1", "score_1": "2", "score_2": "1"},
            {"winner": "2", "score_1": "0", "score_2": "1"},
        ]

        w, r, s = merge_rallies(windows, rows, scores, {100, 500})

        assert w == [(100, 400), (500, 600), (700, 800)]
        assert [x["set"] for x in r] == ["1", "1", "2"]
        assert [(p["winner"], p["score_1"], p["score_2"]) for p in s] == [("2", "0", "1"), ("1", "1", "1"), ("2", "0", "1")]


class TestBallNear:
    def test_a_ball_frame_near_two_touches_places_both(self, tmp_path):
        ball = tmp_path / "ball.csv"
        ball.write_text("frame,visible,x,y\n100,1,10,20\n130,0,0,0\n")

        assert ball_near(ball, [95, 105], 10) == {95: ("10", "20"), 105: ("10", "20")}


class TestFollowed:
    def test_a_rallys_last_touch_gives_its_winner_and_the_score_follows(self):
        rallies = [{"set": 1, "winner": 2}, {"set": 1, "winner": 2}, {"set": 1, "winner": 1}, {"set": 2, "winner": None}]
        found = [
            {"rally": 0, "type": "attack", "team": 1, "result": "play"},
            {"rally": 0, "type": "block", "team": 2, "result": "error"},  # the blockers' fault, whatever was said
            {"rally": 0, "type": "floor", "team": None, "result": "play"},
            {"rally": 1, "type": "dig", "team": 1, "result": "play"},  # in play: its own winner stands
            {"rally": 2, "type": "attack", "team": 2, "result": "point"},
        ]

        followed(rallies, found)

        assert [r["winner"] for r in rallies] == [1, 2, 2, None]
        assert [r.get("score") for r in rallies] == [[1, 0], [1, 1], [1, 2], [0, 0]]

    def test_a_rally_the_referee_got_wrong_keeps_the_point_given_whatever_its_last_touch_says(self):
        rallies = [{"key": 100, "set": 1, "winner": 2}, {"key": 200, "set": 1, "winner": None}]
        found = [{"rally": 0, "type": "attack", "team": 1, "result": "point"}]

        followed(rallies, found, wrong={100, 200})

        assert [(r["winner"], r.get("wrongCall"), r["score"]) for r in rallies] == [(2, True, [0, 1]), (None, None, [0, 1])]
        assert found[0]["result"] == "point"

    def test_a_rally_to_replay_gives_nobody_a_point_and_its_touches_stay_in_play(self):
        rallies = [{"key": 100, "set": 1, "winner": 1}, {"key": 200, "set": 1, "winner": 2}, {"key": 300, "set": 1, "winner": 1}]
        found = [
            {"rally": 0, "type": "attack", "team": 1, "result": "point"},
            {"rally": 1, "type": "dig", "team": 1, "result": "play"},
            {"rally": 1, "type": "attack", "team": 2, "result": "error"},
            {"rally": 2, "type": "attack", "team": 1, "result": "point"},
        ]

        followed(rallies, found, {200})

        assert [(r["winner"], r.get("redo"), r["score"]) for r in rallies] == [(1, None, [1, 0]), (None, True, [1, 0]), (1, None, [2, 0])]
        assert [c["result"] for c in found] == ["point", "play", "play", "point"]


class TestSplitRallies:
    def test_a_rally_starts_inside_one_or_between_two_where_the_review_says(self):
        rows = [{"set": "1", "left": "2", "start_frame": "100", "end_frame": "200"}, {"set": "2", "left": "1", "start_frame": "500", "end_frame": "600"}]
        scores = [{"winner": "1"}, {"winner": "2"}]

        r, s = split_rallies(rows, scores, [150, 300, 500, 50])

        # Inside: the second part keeps the point; between: the sides and set of the one before; at a start: nothing.
        assert [(x["start_frame"], x["end_frame"], x["set"], x["left"]) for x in r] == [
            ("50", "50", "1", "2"),
            ("100", "149", "1", "2"),
            ("150", "200", "1", "2"),
            ("300", "300", "1", "2"),
            ("500", "600", "2", "1"),
        ]
        assert s == [{}, {}, {"winner": "1"}, {}, {"winner": "2"}]


class TestSettle:
    def test_a_rallys_last_touch_wins_or_loses_it_as_its_winner_says(self):
        def c(rally, kind, team, result="play"):
            return {"rally": rally, "type": kind, "team": team, "result": result}

        found = [c(0, "serve", 1), c(0, "attack", 2), c(0, "floor", None), c(1, "serve", 2), c(1, "dig", 1, "error"), c(2, "serve", 1)]

        settle(found, [2, 2, None])

        assert [x["result"] for x in found] == ["play", "point", "play", "play", "error", "play"]


class TestBrand:
    def test_copies_a_themes_logo_into_the_site_shrunk_and_lists_the_themes_for_an_unknown_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web, "BRANDING", tmp_path / "branding")
        theme = tmp_path / "branding" / "club"
        theme.mkdir(parents=True)
        cv2.imwrite(str(theme / "logo.png"), np.zeros((500, 400, 4), np.uint8))
        (theme / "sponsors").mkdir()
        cv2.imwrite(str(theme / "sponsors" / "sponsor.png"), np.zeros((320, 200, 4), np.uint8))
        (theme / "sponsors" / "sponsors.json").write_text('[{"name": "Shop", "logo": "sponsor.png"}, {"name": "Bakery"}]')
        (theme / "brand.json").write_text('{"name": "Club", "logo": "logo.png", "light": {}, "dark": {}}')

        data = brand("club", tmp_path / "site")

        assert data["logo"] == "brand/logo.webp"
        assert cv2.imread(str(tmp_path / "site" / "brand" / "logo.webp"), cv2.IMREAD_UNCHANGED).shape == (128, 102, 4)
        inlined = base64.b64decode(data["sponsors"][0]["logo"].removeprefix("data:image/webp;base64,"))
        assert cv2.imdecode(np.frombuffer(inlined, np.uint8), cv2.IMREAD_UNCHANGED).shape == (160, 100, 4)
        assert data["sponsors"][1] == {"name": "Bakery"}
        assert brand("none", tmp_path / "site") is None
        with pytest.raises(SystemExit, match="club, none"):
            brand("other", tmp_path / "site")


class TestMatchData:
    def test_reads_a_hand_edited_date_and_colour_and_refuses_what_it_cannot(self, tmp_path):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        writer.write(np.zeros((48, 64, 3), np.uint8))
        writer.release()
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n")
        (tmp_path / "actions.csv").write_text("frame,x,y,type,side,track\n")
        (tmp_path / "tracks.csv").write_text("track,team\n")
        teams = {"date": "25/10/2026", "teams": [{"name": "A", "colour": " Rouge", "jersey": "#ffffff"}, {"name": "B", "colour": None, "jersey": "#000080"}]}
        (tmp_path / "teams.json").write_text(json.dumps(teams))

        data, _ = match_data(tmp_path, video, IDENTITY)

        assert data["date"] == "2026-10-25" and [t["colour"] for t in data["teams"]] == [COLOURS["red"], "#000080"]
        teams["date"] = "25 octobre"
        (tmp_path / "teams.json").write_text(json.dumps(teams))
        with pytest.raises(ValueError, match="25 octobre"):
            match_data(tmp_path, video, IDENTITY)
        teams["date"], teams["teams"][0]["colour"] = "2026-10-25", "sparkly"
        (tmp_path / "teams.json").write_text(json.dumps(teams))
        with pytest.raises(ValueError, match="sparkly"):
            match_data(tmp_path, video, IDENTITY)


class TestWriteSite:
    def test_copies_the_page_next_to_data_js_and_the_video(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"not a video")
        site = tmp_path / "site"
        (site / "assets").mkdir(parents=True)
        (site / "assets" / "old.js").write_text("")

        write_site({"fps": 25.0, "rallies": [], "name": "Bègles"}, {"step": 3, "samples": [[]]}, video, site, copy=True)

        version = (site / "index.html").read_text().split('src="data.js?v=')[1].split('"')[0]
        assert len(version) == 10
        assert not (site / "assets" / "old.js").exists()
        assert (site / "data.js").read_text() == f'window.MATCH = {{"fps":25.0,"rallies":[],"name":"Bègles","video":"match.mp4","positions":{{"step":3,"every":2500,"files":1,"cm":2}},"contacts":[],"v":"{version}"}};\n'
        assert (site / "positions" / "0.js").read_text() == "window.MATCH_POSITIONS(0,[1,[]]);\n"

        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)

        assert f'src="data.js?v={version}"' not in (site / "index.html").read_text()

        assert not (site / "positions").exists()
        assert (site / "match.mp4").read_bytes() == b"not a video"
        assert not (site / "poster.webp").exists()

    def test_offers_an_av1_and_a_small_copy_beside_the_video_all_keeping_their_dates(self, tmp_path):
        video, av1, small = tmp_path / "match.mp4", tmp_path / "match_av1.mp4", tmp_path / "match_720p.mp4"
        video.write_bytes(b"h264")
        av1.write_bytes(b"av1")
        small.write_bytes(b"720p")
        site = tmp_path / "site"

        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True, av1=av1, small=small)

        assert '"video":"match.mp4","av1":"match_av1.mp4","small":"match_720p.mp4"' in (site / "data.js").read_text()
        assert (site / "match_av1.mp4").read_bytes() == b"av1"
        assert (site / "match_720p.mp4").read_bytes() == b"720p"
        assert (site / "match.mp4").stat().st_mtime == video.stat().st_mtime
        assert (site / "match.mp4").stat().st_ino == video.stat().st_ino

    def test_leaves_the_video_out_and_removes_a_previous_one(self, tmp_path):
        # The camera names its files in capitals; a symlinked one too.
        video, other = tmp_path / "DJI_0001.MP4", tmp_path / "clip.mov"
        video.write_bytes(b"not a video")
        other.write_bytes(b"not a video")
        site = tmp_path / "site"
        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)
        (site / other.name).symlink_to(other)

        write_site({"fps": 25.0, "rallies": []}, None, None, site, copy=True)

        assert not (site / video.name).exists() and not (site / other.name).is_symlink()
        assert '"video":null' in (site / "data.js").read_text()


class TestFramesIndex:
    def test_where_each_moment_of_the_video_is_in_the_file(self, tmp_path):
        def box(kind: bytes, *content: bytes) -> bytes:
            return struct.pack(">I4s", 8 + sum(map(len, content)), kind) + b"".join(content)

        def full(kind: bytes, *content: bytes) -> bytes:
            return box(kind, bytes(4), *content)

        # 250 samples at 10 a second, 10 to a chunk: 25 chunks of 1 s, 100 bytes apart from byte 1000.
        stbl = box(
            b"stbl",
            full(b"stts", struct.pack(">III", 1, 250, 1)),
            full(b"stsc", struct.pack(">IIII", 1, 1, 10, 1)),
            full(b"stco", struct.pack(">I", 25), *(struct.pack(">I", 1000 + 100 * k) for k in range(25))),
        )
        mdia = box(b"mdia", full(b"mdhd", bytes(8), struct.pack(">I", 10), bytes(8)), full(b"hdlr", bytes(4), b"vide", bytes(12)), box(b"minf", stbl))
        head = box(b"ftyp", b"isom") + box(b"moov", box(b"trak", mdia))
        path = tmp_path / "copy.mp4"
        path.write_bytes(head + box(b"mdat", bytes(4000 - len(head) - 8)))

        # A point every 10 s and the last chunk, at its share of the 4000 bytes.
        assert frames_index(path) == [[0.0, 0.25], [10.0, 0.5], [20.0, 0.75], [24.0, 0.85]]

    def test_none_for_a_file_without_video(self, tmp_path):
        path = tmp_path / "copy.mp4"
        path.write_bytes(b"not a video")

        assert frames_index(path) is None


class TestPhotos:
    def test_saves_a_picture_of_each_numbered_player_from_their_longest_piece(self, tmp_path, monkeypatch):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(20):
            writer.write(np.full((48, 64, 3), 128, np.uint8))
        writer.release()
        rows = [f"{f},1,left,10,10,20,40,0.9,15,40,-3,0" for f in range(20)]
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "\n".join(rows) + "\n")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n1,0,19,1,3,,1.0\n")
        (tmp_path / "identity_candidates.json").write_text('{"segments": [], "merges": []}')
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n0,19\n")
        people = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": None}}

        # The picture as cut, without the upscaler.
        monkeypatch.setattr(web, "upscaler", lambda: None)
        photos(tmp_path, video, people, tmp_path / "players")

        assert people[0]["photo"].startswith("players/0.webp?v=")
        # The 10x30 box from a little above its top down to its waist (55 %), 3 wide for 4 tall.
        assert cv2.imread(str(tmp_path / "players" / "0.webp")).shape[:2] == (17, 13)
        assert "photo" not in people[1]


class TestPublish:
    def test_keeps_the_previous_choices_each_given_one_replacing_its_own(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[4:]) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "blur-opponents", "club": 1, "pictures": True})
        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": None, "pictures": False})

        # copy, theme, footage, club, pictured teams
        assert built == [(False, "aspom", "blur-opponents", 1, {1}), (False, "aspom", "blur-opponents", 1, set())]

    def test_a_page_to_host_shows_only_what_it_is_given_and_saves_nothing(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[4:]) or {})
        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "full", "club": 1, "pictures": True})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": 1}, tmp_path / "hosted")

        assert built[1] == (False, "aspom", "none", 1, set())
        assert json.loads((tmp_path / "page.json").read_text())["footage"] == "full"

    def test_plays_a_lighter_copy_of_the_full_footage_only(self, tmp_path, monkeypatch):
        with pytest.raises(ValueError):
            web.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", tmp_path / "site", footage="blur-all", light=tmp_path / "v_1080p.mp4")
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(kwargs) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "full", "light": "v_1080p.mp4", "link": None}, tmp_path / "hosted")

        assert built == [{"light": Path("v_1080p.mp4"), "link": None, "feedback": None, "av1": None, "small": None}]

    def test_pictures_both_teams_of_the_club(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[8]) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": "both", "pictures": True}, tmp_path / "hosted")

        assert built == [{1, 2}]
        with pytest.raises(ValueError):
            publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": "both", "footage": "blur-opponents"}, tmp_path / "hosted")

    def test_refuses_pictures_or_a_blurred_opponent_without_a_club(self, tmp_path):
        with pytest.raises(ValueError):
            publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"pictures": True})


class TestPositionFiles:
    def test_keeps_each_persons_runs_and_moves_each_file_on_its_own(self):
        players = {"step": 25, "samples": [[1, -5.8, 3.32, 2, 1.53, -0.07], [1, -5.79, 3.31], [], [2, 1.5, -0.02, 1, -5.77, 3.31]]}

        # At 25 fps a sample a second: three to a file of 3 s.
        web.POSITIONS_S, kept = 3, web.POSITIONS_S
        web.POSITION_CM, kept_cm = 5, web.POSITION_CM
        try:
            assert web.position_files(players, 25.0) == [
                "window.MATCH_POSITIONS(0,[3,[[1,[0,2],[-116,0],[66,0]],[2,[0,1],[31],[-1]]]]);\n",
                "window.MATCH_POSITIONS(1,[1,[[1,[0,1],[-115],[66]],[2,[0,1],[30],[0]]]]);\n",
            ]
        finally:
            web.POSITIONS_S = kept
            web.POSITION_CM = kept_cm


class TestFilms:
    def films(self, tmp_path):
        folder = tmp_path / "films"
        folder.mkdir()
        (folder / "1-ana.mp4").write_bytes(b"film")
        (folder / "manifest.json").write_text(json.dumps({"Ana": {"hash": "abc", "file": "1-ana.mp4"}}))
        return folder

    def test_goes_beside_a_page_with_the_video(self, tmp_path):
        site, video = tmp_path / "site", tmp_path / "match.mp4"
        video.write_bytes(b"video")

        web.write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True, films=self.films(tmp_path))

        assert (site / "films" / "1-ana.mp4").read_bytes() == b"film"
        assert '"films":{"Ana":"films/1-ana.mp4?v=abc"}' in (site / "data.js").read_text()

    def test_never_beside_a_page_without_it_even_where_one_was(self, tmp_path):
        site, video = tmp_path / "site", tmp_path / "match.mp4"
        video.write_bytes(b"video")
        web.write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True, films=self.films(tmp_path))

        web.write_site({"fps": 25.0, "rallies": []}, None, None, site, copy=False, films=tmp_path / "films")

        assert not (site / "films").exists()
        assert "films" not in (site / "data.js").read_text()

    def test_leaves_a_film_unchanged_in_place_and_drops_those_gone(self, tmp_path):
        folder, site = self.films(tmp_path), tmp_path / "site"
        site.mkdir()
        web.copy_films(folder, site)
        kept = (site / "films" / "1-ana.mp4").stat().st_mtime_ns
        (site / "films" / "2-gone.mp4").write_bytes(b"old")

        web.copy_films(folder, site)

        assert (site / "films" / "1-ana.mp4").stat().st_mtime_ns == kept
        assert not (site / "films" / "2-gone.mp4").exists()


class TestNaturalMotion:
    @staticmethod
    def track(places):
        return [[] if place is None else [1, *place] for place in places]

    @staticmethod
    def places(samples):
        return [flat[1:3] if flat else None for flat in samples]

    def test_leaves_a_steady_run_where_it_is(self):
        run = [(k * 0.3, 2.0) for k in range(40)]
        found = self.places(web.natural_motion(self.track(run), 0.1, {}))
        # The ends lean inward: the middle stays on the line.
        for k in range(10, 30):
            assert found[k] == pytest.approx(run[k], abs=0.01)

    def test_drops_a_place_far_from_those_around_it(self):
        places = [(1.0, 2.0)] * 21
        places[10] = (1.0, 5.0)
        found = self.places(web.natural_motion(self.track(places), 0.1, {}))
        assert found[10] == pytest.approx((1.0, 2.0), abs=0.01)

    def test_fills_a_hole_they_could_have_walked_only(self):
        walked = [(0.0, 0.0)] * 5 + [None] * 10 + [(3.0, 0.0)] * 5
        assert all(place is not None for place in self.places(web.natural_motion(self.track(walked), 0.1, {})))
        too_fast = [(0.0, 0.0)] * 5 + [None] * 10 + [(9.0, 0.0)] * 5
        assert self.places(web.natural_motion(self.track(too_fast), 0.1, {}))[10] is None
        too_long = [(0.0, 0.0)] * 5 + [None] * 60 + [(1.0, 0.0)] * 5
        assert self.places(web.natural_motion(self.track(too_long), 0.1, {}))[30] is None

    def test_leaves_a_hole_open_when_the_team_already_has_six_there(self):
        # Five teammates stand all along, and a sixth comes only during the hole of person 1.
        others = [[p, float(p), 0.0] for p in range(2, 7)]
        samples = [[1, 0.0, 0.0, *sum(others, [])] if k < 5 or k >= 15 else [*sum(others, []), *([7, 8.0, 8.0] if 8 <= k < 12 else [])] for k in range(20)]
        teams = {p: 1 for p in range(1, 8)}

        found = web.natural_motion(samples, 0.1, teams)
        assert 1 not in found[10][0::3]
        # Without that sixth, the hole fills.
        alone = [[flat[i] for i in range(len(flat)) if flat[i - i % 3] != 7] for flat in samples]
        assert 1 in web.natural_motion(alone, 0.1, teams)[10][0::3]

    def test_keeps_a_track_shorter_than_its_smoothing_at_its_places(self):
        found = web.natural_motion([[], [7, 2.0, 3.0], [7, 2.0, 3.0], []], 0.1, {})
        assert found == [[], [7, 2.0, 3.0], [7, 2.0, 3.0], []]


class TestWithLandings:
    players = {"step": 1, "samples": [[1, 1.0, 1.0, 2, 2.0, 2.0], [1, 3.0, 3.0], [2, 9.0, 9.0]]}

    @staticmethod
    def contact(kind: str, rally: int = 0, t: float = 0.2, result: str = "play", x: float | None = 1.0) -> dict:
        return {"type": kind, "rally": rally, "t": t, "result": result, "x": x, "y": 1.0}

    def test_gives_a_landing_after_a_point_the_players_there_each_at_their_last_place(self):
        found = web.with_landings([self.contact("attack", result="point"), self.contact("floor")], self.players, 10.0)

        assert found[1]["around"] == [2, 9.0, 9.0, 1, 3.0, 3.0]
        assert "around" not in found[0]

    def test_leaves_a_landing_without_a_point_before_it_in_its_rally_or_a_place(self):
        for contacts in (
            [self.contact("attack"), self.contact("floor")],
            [self.contact("attack", rally=1, result="point"), self.contact("floor")],
            [self.contact("attack", result="point"), self.contact("floor", x=None)],
            [self.contact("floor")],
        ):
            assert "around" not in web.with_landings(contacts, self.players, 10.0)[-1]

    def test_holds_a_player_no_longer_than_half_a_second(self):
        samples = [[1, 1.0, 1.0], [], [], [], [], [], [2, 2.0, 2.0]]
        found = web.with_landings([self.contact("attack", result="point"), self.contact("floor", t=0.6)], {"step": 1, "samples": samples}, 10.0)
        assert found[1]["around"] == [2, 2.0, 2.0]


class TestKeptPhotos:
    def test_keeps_a_players_picture_unless_its_file_is_gone(self, tmp_path):
        people = {"0": {"team": 1, "number": 3, "photo": "players/0.webp?v=a"}, "1": {"team": 2, "number": 4, "photo": "players/1.webp?v=b"}}
        (tmp_path / "data.js").write_text(f"window.MATCH = {json.dumps({'people': people})};\n")
        (tmp_path / "players").mkdir()
        (tmp_path / "players" / "0.webp").write_bytes(b"x")
        built = {5: {"team": 1, "number": 3}, 6: {"team": 2, "number": 4}, 7: {"team": 2, "number": 9}}

        web.kept_photos(built, tmp_path)

        assert built == {5: {"team": 1, "number": 3, "photo": "players/0.webp?v=a"}, 6: {"team": 2, "number": 4}, 7: {"team": 2, "number": 9}}
