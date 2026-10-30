import numpy as np

from volleyball_stats.identity import (
    CORE_S,
    LONGEST_S,
    Segment,
    cannot_links,
    covers,
    group,
    hold,
    jersey_links,
    lookup,
    name_links,
    named,
    number,
    resolve,
    sharpen,
    split,
)
from volleyball_stats.players import Row

FPS = 10.0


def row(frame: int, track: int, box=(0.0, 0.0, 10.0, 20.0), court=(0.0, 0.0)) -> Row:
    return Row(frame, track, box, 0.9, (0.0, 0.0), court)


class TestSplit:
    def test_cuts_a_track_in_the_middle_of_each_crowd_episode(self):
        # Track 2 stands in front of track 1 over frames 10-19.
        rows = [row(f, 1) for f in range(30)] + [row(f, 2) for f in range(10, 20)]

        segments = split(rows, covers(rows))

        assert [(s.track, s.start, s.end) for s in segments] == [(1, 0, 14), (2, 10, 14), (1, 15, 29), (2, 15, 19)]

    def test_keeps_a_track_whole_when_nobody_covers_it(self):
        rows = [row(f, 1) for f in range(30)] + [row(f, 2, (50.0, 0.0, 60.0, 20.0)) for f in range(30)]

        assert [(s.track, s.start, s.end) for s in split(rows, covers(rows))] == [(1, 0, 29), (2, 0, 29)]

    def test_cuts_a_track_after_a_frame_the_user_gave(self):
        rows = [row(f, 1) for f in range(30)]

        assert [(s.track, s.start, s.end) for s in split(rows, covers(rows), {1: [11]})] == [(1, 0, 11), (1, 12, 29)]


class TestCannotLinks:
    def test_blocks_teammates_seen_together_and_runs_too_fast(self):
        segments = [
            Segment(1, list(range(0, 20)), [(0.0, 0.0)] * 20, team=1),
            Segment(2, list(range(10, 30)), [(1.0, 0.0)] * 20, team=1),  # seen with 1
            Segment(3, list(range(25, 40)), [(0.5, 0.0)] * 15, team=1),  # 1 could run there, not 2
            Segment(4, list(range(25, 40)), [(-9.0, 4.0)] * 15, team=1),  # 9.8 m in 0.5 s from 1
            Segment(5, list(range(50, 60)), [(0.0, 0.0)] * 10, team=2),
        ]

        cannot = cannot_links(segments, FPS)

        # The other team's segment is never compared: teams are grouped apart.
        assert cannot == [{1, 3}, {0, 2, 3}, {1, 3}, {0, 1, 2}, set()]


class TestGroup:
    def test_two_players_split_into_pieces_become_two_identities(self):
        # Players A and B, seen together, lost, then seen together again; long pieces.
        rng = np.random.default_rng(0)
        a, b = np.eye(8)[0], np.eye(8)[1]
        v = np.array([a, b, a, b]) + 0.05 * rng.standard_normal((4, 8))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        length = int(LONGEST_S * FPS) + 20
        starts = np.array([0, 0, 2 * length, 2 * length])
        cannot = [{1}, {0}, {3}, {2}]

        found = group(v, np.ones(4), np.full(4, float(length)), starts, cannot, [], np.full(4, -1), FPS)

        assert found[0] == found[2] != found[1] == found[3]

    def test_must_links_join_pieces_the_embedding_keeps_apart(self):
        a, b = np.eye(8)[0], np.eye(8)[1]
        v = np.array([a, b])
        length = int(max(CORE_S, LONGEST_S) * FPS) + 20

        found = group(v, np.ones(2), np.full(2, float(length)), np.array([0, 2 * length]), [set(), set()], [(0, 1)], np.full(2, -1), FPS)

        assert found[0] == found[1] == 0

    def test_identities_too_short_get_none(self):
        v = np.eye(8)[:1]

        assert group(v, np.ones(1), np.array([LONGEST_S * FPS - 1]), np.array([0]), [set()], [], np.array([-1]), FPS).tolist() == [-1]


class TestNumber:
    @staticmethod
    def segments() -> list[Segment]:
        # Team 1 on the left at the serve (frame 0): back right (zone 1) and front right (zone 2),
        # a third player coming in later.
        return [
            Segment(1, [0, 1], [(-1.0, 3.0)] * 2, team=1, identity=7),
            Segment(2, [0, 1], [(-7.0, 3.0)] * 2, team=1, identity=4),
            Segment(3, [50, 51], [(-5.0, 0.0)] * 2, team=1, identity=9),
            Segment(4, [60, 61], [(-5.0, 0.0)] * 2, team=1, identity=7),
        ]

    def test_numbers_the_serving_line_up_by_zone_then_the_others_by_first_appearance(self):
        segments = self.segments()

        number(segments, 0, FPS)

        assert [s.identity for s in segments] == [2, 1, 3, 2]

    def test_a_rerun_keeps_the_previous_numbers(self):
        segments = self.segments()
        previous = {(0, 1): (1, 5), (1, 1): (1, 5)}

        number(segments, 0, FPS, previous)

        # The previous 5 stays; the others come after it.
        assert [s.identity for s in segments] == [5, 6, 7, 5]


class TestHold:
    def test_each_track_holds_one_number_through_a_rally(self):
        def piece(track: int, start: int, end: int, number_: int) -> Segment:
            return Segment(track, list(range(start, end + 1)), [(0.0, 0.0)] * (end - start + 1), team=1, identity=number_)

        segments = [
            piece(1, 0, 19, 3),
            piece(1, 20, 24, 5),
            piece(1, 25, 49, 3),
            # Track 2's 3 is track 1's, seen at the same time with more frames: track 2 holds its 4.
            piece(2, 10, 21, 3),
            piece(2, 22, 29, 4),
            # Track 3 takes over from track 2: it keeps the same 4.
            piece(3, 34, 39, 4),
        ]

        held = sorted(hold(segments, [(10, 39)]), key=lambda s: (s.start, s.track))

        assert [(s.track, s.start, s.end, s.identity) for s in held] == [
            (1, 0, 9, 3), (1, 10, 19, 3), (2, 10, 21, 4), (1, 20, 24, 3), (2, 22, 29, 4), (1, 25, 39, 3), (3, 34, 39, 4), (1, 40, 49, 3),
        ]


class TestAnswers:
    segments = [
        Segment(1, list(range(0, 10)), [(0.0, 0.0)] * 10, team=1),
        Segment(1, list(range(20, 30)), [(0.0, 0.0)] * 10, team=1),
        Segment(2, list(range(0, 10)), [(0.0, 0.0)] * 10, team=1),
    ]

    def test_refers_to_a_track_a_piece_of_it_or_a_previous_identity(self):
        before = [(1, 3), None, (1, 3)]

        assert resolve({"track": 1}, self.segments, before) == [0, 1]
        assert resolve({"track": 1, "frame": 18}, self.segments, before) == [1]
        assert resolve({"team": 1, "identity": 3}, self.segments, before) == [0, 2]

    def test_jersey_numbers_join_the_same_number_and_part_two_numbers(self):
        jerseys = {(5, 1): 12, (25, 1): 12, (5, 2): 7}

        assert jersey_links(self.segments, jerseys) == ([[0, 1]], [[[2], [0, 1]]])


    def test_names_join_the_same_name_whatever_the_case_and_part_two_names(self):
        names = [({"track": 1, "frame": 5}, "Julie"), ({"track": 1, "frame": 25}, "julie "), ({"track": 2, "frame": 5}, "Léa")]

        assert name_links(self.segments, names, [None] * 3) == ([[0, 1]], [[[0, 1], [2]]])


class TestNamed:
    def test_names_the_identity_holding_each_entrys_piece_the_first_entry_winning(self):
        table = [(1, 0, 10, 1, 3), (1, 11, 30, 1, 5), (2, 0, 30, 2, 1)]
        names = [
            {"ref": {"track": 1, "frame": 20}, "name": "Julie", "jersey": 7},
            {"ref": {"track": 1, "frame": 25}, "name": "Léa", "jersey": None},
            {"ref": {"track": 2, "frame": 5}, "name": None, "jersey": 4},
        ]

        assert named(table, names) == {(1, 5): {"name": "Julie", "jersey": 7}, (2, 1): {"name": None, "jersey": 4}}


class TestLookup:
    def test_takes_the_segment_holding_the_frame_else_the_nearest(self):
        table = [(1, 0, 10, 1, 3), (1, 11, 30, 1, 5), (1, 31, 50, 1, 0), (2, 0, 30, 2, 1)]

        assert lookup(table, 1, 15) == (1, 5)
        assert lookup(table, 2, 40) == (2, 1)
        assert lookup(table, 3, 15) is None

    def test_a_segment_without_identity_lends_no_neighbours_number(self):
        table = [(1, 0, 10, 1, 3), (1, 11, 30, 1, 0)]

        assert lookup(table, 1, 20) is None


class TestSharpen:
    def test_weights_the_direction_telling_confirmed_players_apart(self):
        # Two players confirmed by answers differ along x; everyone varies as much along y.
        v = np.array([[1.0, 1.0], [1.0, -1.0], [-1.0, 1.0], [-1.0, -1.0], [0.0, 1.0]]) / np.sqrt(2)
        sharp = sharpen(v, np.ones(5), [(0, 1), (2, 3)], share=0.5)

        assert abs(sharp[0, 0]) > abs(sharp[0, 1])
        assert np.allclose(np.linalg.norm(sharp, axis=1), 1)

    def test_leaves_the_vectors_without_two_confirmed_players(self):
        v = np.eye(3)

        assert np.array_equal(sharpen(v, np.ones(3), [(0, 1)]), v)
