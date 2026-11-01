import json

import numpy as np
from volleyball_stats.attribution import CROSS_M, FAR, GAP_S, REACH, SIDE_M, WRIST_CONF, attribute, box_at, by_wrists, distance, gap_to_next, ranked, read_players, unreached, wrist_distance, wrist_order
from volleyball_stats.players import Row, write_csv

FPS = 30.0


def row(frame: int, track: int, box: tuple[float, float, float, float], team: str = "left", x: float = 0.0) -> Row:
    return Row(frame, track, box, 0.9, ((box[0] + box[2]) / 2, box[3]), (x, 0.0), team)


class TestDistance:
    def test_is_zero_inside_and_in_box_heights_outside(self):
        box = (100.0, 200.0, 140.0, 300.0)

        assert distance((120.0, 250.0), box) == 0
        assert distance((160.0, 250.0), box) == 0.2

    def test_the_reach_extends_the_box_upward_only(self):
        box = (100.0, 200.0, 140.0, 300.0)

        assert distance((120.0, 160.0), box, 0.5) == 0
        assert distance((120.0, 140.0), box, 0.5) == 0.1
        assert distance((120.0, 320.0), box, 0.5) == 0.2


class TestBoxAt:
    BOXES = {10: (0.0, 0.0, 10.0, 20.0), 14: (8.0, 0.0, 18.0, 20.0)}

    def test_takes_the_track_s_own_box(self):
        assert box_at(self.BOXES, 10, 5) == (0.0, 0.0, 10.0, 20.0)

    def test_interpolates_over_a_gap_and_holds_the_nearest_box_at_an_end(self):
        assert box_at(self.BOXES, 12, 5) == (4.0, 0.0, 14.0, 20.0)
        assert box_at(self.BOXES, 17, 5) == (8.0, 0.0, 18.0, 20.0)

    def test_is_none_beyond_the_gap(self):
        assert box_at(self.BOXES, 20, 5) is None


class TestAttribute:
    def test_picks_the_nearest_box_of_the_contact_s_side(self):
        # The opponent across the net is nearer to the ball in the image.
        rows = [row(50, 1, (100, 200, 140, 300)), row(50, 2, (200, 200, 240, 300)), row(50, 3, (150, 200, 190, 300), "right")]

        assert attribute([(50, 170, 250, "dig", "left"), (50, 170, 250, "dig", "right")], rows, FPS) == [1, 3]

    def test_floor_net_and_uncovered_contacts_have_no_player(self):
        rows = [row(50, 1, (100, 200, 140, 300))]

        typed = [(50, 120, 250, "floor", "left"), (50, 120, 250, "net", "left"), (50, 120, 250, "set", "right"), (200, 120, 250, "set", "left")]

        assert attribute(typed, rows, FPS) == [None, None, None, None]

    def test_an_attack_goes_to_the_player_under_the_ball_and_a_set_to_the_nearest_box(self):
        # The hitter's arm is outside her box: the ball is 0.3 heights above it. A teammate's box
        # top is level with the ball, 15 px to the side.
        hitter, teammate = row(50, 1, (100, 200, 140, 300)), row(50, 2, (145, 170, 185, 270))
        ball = (130, 170)

        assert 0.3 < REACH
        assert attribute([(50, *ball, "attack", "left"), (50, *ball, "set", "left")], [hitter, teammate], FPS) == [1, 2]

    def test_keeps_a_track_missing_at_the_contact_frame(self):
        # The toucher is lost 3 frames on each side of the contact, a teammate stands 1 height away.
        gap = round(GAP_S * FPS)
        rows = [row(f, 1, (100, 200, 140, 300)) for f in (47, 53)] + [row(f, 2, (240, 200, 280, 300)) for f in range(40, 60)]

        assert gap >= 3
        assert attribute([(50, 120, 250, "pass", "left")], rows, FPS) == [1]


    def test_leaves_out_a_track_standing_past_the_net_at_the_contact_frame(self):
        # Track 1 kept the left side of the player it followed first; it now shows a player of the
        # right side, at the net.
        rows = [row(50, 1, (100, 200, 140, 300), x=SIDE_M + 0.1), row(50, 2, (150, 200, 190, 300), x=-0.3)]

        assert attribute([(50, 120, 250, "block", "left")], rows, FPS) == [2]

    def test_takes_a_track_of_the_other_side_standing_well_inside_the_contact_side(self):
        # Track 2 kept the right side of the player it followed first; it now shows a left player.
        rows = [row(50, 1, (100, 200, 140, 300), x=-3.0), row(50, 2, (150, 200, 190, 300), "right", x=-CROSS_M - 0.5), row(50, 3, (195, 200, 235, 300), "right", x=-0.5)]

        assert attribute([(50, 170, 250, "set", "left")], rows, FPS) == [2]
        assert attribute([(50, 215, 250, "set", "left")], rows, FPS) == [2]

    def test_a_ball_inside_two_boxes_goes_to_the_bigger_one(self):
        # Track 2, nearer the camera, stands in front of track 1 and its box holds track 1's.
        rows = [row(50, 1, (100, 200, 140, 300)), row(50, 2, (90, 180, 160, 340))]

        assert attribute([(50, 120, 250, "pass", "left")], rows, FPS) == [2]

    def test_the_gap_to_the_next_candidate_measures_the_doubt(self):
        rows = [row(50, 1, (100, 200, 140, 300)), row(50, 2, (150, 200, 190, 300))]

        near, alone = ranked([(50, 145, 250, "set", "left"), (50, 120, 250, "set", "right")], rows + [row(50, 3, (0, 200, 40, 300), "right")], FPS)

        assert [round(d, 2) for d, _, _ in near] == [0.05, 0.05] and round(gap_to_next(near), 2) == 0.0
        assert gap_to_next(alone) is None


class TestUnreached:
    def test_a_touch_with_no_player_at_the_ball_is_none(self):
        rows = [row(50, 1, (100, 200, 140, 300)), row(60, 1, (100, 200, 140, 300))]
        # The ball 0.2 box heights to the side of the player, then high above the box and its reach.
        typed = [(50, 160, 250, "set", "left"), (60, 120, 200 - (REACH + FAR + 0.1) * 100, "attack", "left"), (60, 120, 50, "floor", "left")]

        assert unreached(typed, rows, FPS) == {60}


class TestReadPlayers:
    def test_reads_back_what_players_writes(self, tmp_path):
        rows = [Row(7, 3, (10.5, 20.0, 30.0, 80.0), 0.912, (20.2, 80.0), (-2.5, 1.25), "left")]
        write_csv(rows, tmp_path / "players.csv")

        assert read_players(tmp_path / "players.csv") == rows


class TestWristDistance:
    def test_the_nearest_confident_wrist_of_the_matching_pose_in_box_heights(self):
        box = (100.0, 200.0, 140.0, 300.0)
        keypoints = np.zeros((17, 3))
        # Left wrist 20 px from the ball, right wrist 10 px but unsure.
        keypoints[9], keypoints[10] = (120, 270, WRIST_CONF), (120, 260, WRIST_CONF - 0.1)
        other = np.zeros((17, 3))
        other[9] = (120, 250, 1.0)

        assert wrist_distance((120, 250), box, [[(box, keypoints), ((300, 200, 340, 300), other)]]) == 0.2
        assert wrist_distance((120, 250), box, [[((300, 200, 340, 300), other)]]) is None


class TestWristOrder:
    def test_wrists_reorder_the_close_candidates_and_a_veto_sends_one_last(self):
        found = [(0.05, 0.05, 1), (0.1, 0.1, 2), (0.15, 0.15, 3), (0.9, 0.9, 4)]

        assert [c[2] for c in wrist_order(found, {1: 0.3, 2: 0.1, 3: None, 4: 0.0})] == [2, 1, 3, 4]
        assert [c[2] for c in wrist_order(found, {1: 0.6, 2: None, 3: 0.2, 4: None})] == [3, 2, 4, 1]

    def test_keeps_the_box_holding_the_ball_when_its_wrists_are_not_seen(self):
        found = [(0.0, 0.0, 1), (0.1, 0.1, 2)]

        assert [c[2] for c in wrist_order(found, {1: None, 2: 0.05})] == [1, 2]
        assert [c[2] for c in wrist_order(found, {1: 0.6, 2: 0.7})] == [1, 2]


class TestByWrists:
    def test_poses_kept_in_the_cache_reorder_without_the_video(self, tmp_path):
        rows = [Row(10, 1, (100.0, 200.0, 140.0, 300.0), 0.9, (120.0, 300.0), (-2.0, 0.0), "left"), Row(10, 2, (130.0, 200.0, 170.0, 300.0), 0.9, (150.0, 300.0), (-1.0, 0.0), "left")]
        far, near = np.zeros((17, 3)), np.zeros((17, 3))
        far[9], near[9] = (60, 250, 1.0), (151, 250, 1.0)
        cache = tmp_path / "wrists.json"
        cache.write_text(json.dumps({"10:135:250": [[[list(rows[0].box), far.tolist()], [list(rows[1].box), near.tolist()]]]}))

        out = by_wrists(tmp_path / "none.mp4", [(10, 135, 250, "pass", "left")], [[(0.0, 0.0, 1), (0.0, 0.0, 2)]], rows, 50.0, cache)

        assert [c[2] for c in out[0]] == [2, 1]
