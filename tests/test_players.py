import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.players import END_MARGIN, MIN_FRAMES, SIDE_MARGIN, TRACK_END_MARGIN, TRACK_SIDE_MARGIN, Row, feet, finish, on_court, stitch, track_frames

FPS = 30.0


def row(frame: int, track: int, x: float, y: float = 0.0) -> Row:
    return Row(frame, track, (0.0, 0.0, 1.0, 1.0), 0.9, (0.0, 0.0), (x, y))


def walk(track: int, frames: range, x0: float, dx: float = 0.0, y: float = 0.0) -> list[Row]:
    return [row(f, track, x0 + dx * (f - frames.start), y) for f in frames]


class TestCourtFilter:
    def test_feet_are_the_bottom_center_of_the_boxes(self):
        assert feet(np.array([[10.0, 20.0, 30.0, 80.0, 0.9]])).tolist() == [[20.0, 80.0]]

    def test_keeps_servers_and_players_chasing_a_ball_and_drops_referees_benches_and_spectators(self):
        court = np.array([
            [0.0, 0.0],  # mid-court
            [-9.0 - END_MARGIN + 0.1, 2.0],  # server
            [5.0, 4.5 + SIDE_MARGIN - 0.1],  # chasing a ball past the near sideline
            [0.0, 4.5 + SIDE_MARGIN + 0.5],  # first referee's stand by the near post
            [11.5 + END_MARGIN, -3.0],  # bench beyond the right end
            [-3.0, -9.0],  # spectators along the far wall
        ])

        assert on_court(court).tolist() == [True, True, True, False, False, False]


class TestStitch:
    def test_joins_a_track_resumed_within_reach_after_an_occlusion(self):
        rows = walk(1, range(0, 30), -3.0, 0.02) + walk(2, range(45, 80), -2.0, 0.02)

        assert {r.track for r in stitch(rows, FPS)} == {1}

    def test_keeps_apart_tracks_too_far_to_be_one_player_or_too_long_apart(self):
        # 6 m in 0.5 s is faster than a player runs; the third track starts 3 s later.
        rows = walk(1, range(0, 30), -6.0) + walk(2, range(45, 80), 0.0) + walk(3, range(170, 200), -6.0)

        assert sorted({r.track for r in stitch(rows, FPS)}) == [1, 2, 3]

    def test_an_end_goes_to_the_closest_start_and_each_start_is_taken_once(self):
        # Two players lost together: each continues where it was.
        rows = walk(1, range(0, 30), -3.0, y=1.0) + walk(2, range(0, 30), -3.0, y=-1.0)
        rows += walk(3, range(40, 70), -3.0, y=-1.1) + walk(4, range(40, 70), -3.0, y=1.1)

        stitched = stitch(rows, FPS)

        assert {r.track for r in stitched if r.frame >= 40 and r.court[1] > 0} == {1}
        assert {r.track for r in stitched if r.frame >= 40 and r.court[1] < 0} == {2}

    def test_chains_three_pieces(self):
        rows = walk(5, range(0, 20), 1.0) + walk(7, range(30, 50), 1.2) + walk(9, range(60, 80), 1.4)

        assert {r.track for r in stitch(rows, FPS)} == {5}


class TestFinish:
    def test_drops_short_tracks_and_names_teams_by_side_of_the_net(self):
        rows = walk(1, range(0, 40), -2.0, 0.1) + walk(2, range(0, 40), 3.0) + walk(3, range(0, MIN_FRAMES - 1), 6.0, y=3.0)

        finished = finish(rows, FPS)

        # Track 1 ends past the net (x = 1.9): its median side is still the left.
        assert {(r.track, r.team) for r in finished} == {(1, "left"), (2, "right")}
        assert [r.frame for r in finished] == sorted(r.frame for r in finished)

    def test_drops_tracks_standing_by_the_court_and_keeps_a_player_running_out(self):
        # A coach 1 m outside the near sideline, a retriever behind the right end line, and a player
        # chasing a ball 1.5 m past the far sideline for 10 frames.
        coach = walk(1, range(0, 60), 5.0, y=4.5 + TRACK_SIDE_MARGIN + 0.5)
        retriever = walk(2, range(0, 60), 9.0 + TRACK_END_MARGIN + 1.0, y=-2.0)
        player = walk(3, range(0, 50), -4.0, y=-3.0) + walk(3, range(50, 60), -4.0, y=-6.0)

        assert {r.track for r in finish(coach + retriever + player, FPS)} == {3}


class TestTrackFrames:
    class FakeModel:
        """Two players walking right, and a spectator by the far wall that the court filter drops."""

        def predict(self, frame, **kwargs):
            import torch

            i = float(frame[0, 0, 0])

            class Result:
                boxes = type("Boxes", (), {"data": torch.tensor([
                    [100 + 5 * i, 150, 140 + 5 * i, 250, 0.9, 0],
                    [400 + 5 * i, 170, 440 + 5 * i, 270, 0.8, 0],
                    [600, 0, 630, 40, 0.9, 0],
                ])})

            return [Result()]

    def test_keeps_on_court_players_with_stable_ids(self):
        # 50 px per meter, court center at (300, 400): the players' feet land at y = -3 and -2.6 m,
        # the spectator's at -7.2 m.
        calibration = Calibration(np.array([[50.0, 0, 300], [0, 50, 400], [0, 0, 1]]))
        frames = [np.full((360, 640, 3), i, np.uint8) for i in range(6)]

        rows = [r for frame_rows in track_frames(frames, calibration, self.FakeModel(), "cpu") for r in frame_rows]

        tracks = {}
        for r in rows:
            tracks.setdefault(r.track, []).append(r.feet[0])
        assert len(tracks) == 2
        assert sorted(xs[0] for xs in tracks.values()) == [120.0, 420.0]
        assert all(np.all(np.diff(xs) == 5) for xs in tracks.values())
