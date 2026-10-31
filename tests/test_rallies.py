import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.rallies import FFT_SIZE, SAMPLE_RATE, ball_runs, runs, segment, served, whistles, with_serves

FPS = 30.0


def flight(frames: int, x0: float, dx: float, y: float = 200.0) -> np.ndarray:
    return np.column_stack([x0 + dx * np.arange(frames), np.full(frames, y)])


def tone(seconds: float, hz: float, level: float = 0.3) -> np.ndarray:
    t = np.arange(round(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return level * np.sin(2 * np.pi * hz * t)


class TestRuns:
    def test_bridges_gaps_up_to_the_bridge_and_drops_short_runs(self):
        mask = np.array([1, 1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 1], dtype=bool)

        assert runs(mask, bridge=2, min_len=3) == [(0, 5), (9, 13)]
        assert runs(mask, bridge=0, min_len=3) == [(9, 11)]


class TestBallRuns:
    def test_starts_at_the_serve_and_ignores_a_ball_bounced_in_place(self):
        bounce = np.column_stack([np.full(40, 1100.0), 200 + 8 * np.sin(np.arange(40))])
        toss = flight(10, 1100, 0.0)
        serve = flight(40, 1100, -20.0)
        track = np.concatenate([bounce, toss, serve, np.full((60, 2), np.nan)])

        # The 3-frame speed lag sees the serve one frame after contact.
        assert ball_runs(track, FPS) == [(51, 89)]

    def test_drops_a_run_that_does_not_cross_the_court(self):
        track = np.concatenate([flight(30, 100, 5.0), np.full((60, 2), np.nan)])

        assert ball_runs(track, FPS) == []

    def test_a_jump_to_another_ball_splits_the_run(self):
        track = np.concatenate([flight(25, 100, 5.0), flight(25, 1100, -5.0), np.full((60, 2), np.nan)])

        assert ball_runs(track, FPS) == []


class TestWhistles:
    def test_finds_a_sustained_tone_in_the_whistle_band(self):
        rng = np.random.default_rng(0)
        audio = 0.02 * rng.standard_normal(2 * SAMPLE_RATE)
        audio[SAMPLE_RATE : SAMPLE_RATE + round(0.3 * SAMPLE_RATE)] += tone(0.3, 3900)

        found = whistles(audio)

        assert len(found) == 1
        assert abs(found[0][0] - 1.0) < 0.05 and abs(found[0][1] - 1.3) < 0.05

    def test_ignores_tones_outside_the_band_and_blips(self):
        rng = np.random.default_rng(0)
        audio = 0.02 * rng.standard_normal(2 * SAMPLE_RATE)
        audio[: round(0.3 * SAMPLE_RATE)] += tone(0.3, 1500)
        audio[SAMPLE_RATE : SAMPLE_RATE + round(0.03 * SAMPLE_RATE)] += tone(0.03, 3900)

        assert whistles(audio) == []

    def test_short_audio_has_no_whistle(self):
        assert whistles(np.zeros(FFT_SIZE - 1)) == []

    def test_finds_the_same_whistles_spectrum_block_by_block(self, monkeypatch):
        rng = np.random.default_rng(1)
        audio = 0.02 * rng.standard_normal(3 * SAMPLE_RATE)
        audio[SAMPLE_RATE : SAMPLE_RATE + round(0.5 * SAMPLE_RATE)] += tone(0.5, 3700)
        whole = whistles(audio)

        # Blocks of 70 windows: the whistle spans a block boundary.
        monkeypatch.setattr("volleyball_stats.rallies.BLOCK", 70)

        assert whistles(audio) == whole and len(whole) == 1


class TestSegment:
    rally = np.concatenate([np.full((30, 2), np.nan), flight(60, 1100, -15.0), np.full((300, 2), np.nan)])

    def test_closes_the_rally_at_the_whistle_following_the_ball(self):
        # Ball flies over frames 30-89 (seen moving from 33), whistle at 3.5 s = frame 105.
        assert segment(self.rally, [(3.5, 3.8)], FPS) == [(33, 89)]
        # A whistle before the ball stops caps the end.
        assert segment(self.rally, [(2.5, 2.8)], FPS) == [(33, 75)]

    def test_drops_a_run_without_a_closing_whistle(self):
        assert segment(self.rally, [], FPS) == []
        assert segment(self.rally, [(0.5, 0.8)], FPS) == []

    def test_skips_a_whistle_followed_by_a_flying_ball(self):
        # A serve, then 110 frames of the ball bouncing high at 16 px/frame.
        bouncing = np.column_stack([np.full(110, 500.0), 200 + 16 * (20 - np.abs(np.arange(110) % 40 - 20))])
        track = np.concatenate([np.full((30, 2), np.nan), flight(40, 1100, -15.0), bouncing, np.full((300, 2), np.nan)])

        # 2.5 s: the ball is still flying 1-3 s later; 6.5 s: it has stopped.
        assert segment(track, [(2.5, 2.8), (6.5, 6.8)], FPS) == [(33, 179)]


class TestServed:
    # 50 px per meter, the net at x = 640.
    calibration = Calibration(np.array([[50.0, 0, 640], [0, 50, 360], [0, 0, 1]]))
    # A server stands 1.5 m behind the right end line for 2 s, then serves over the net.
    server = [(f, 10.5, 0.0) for f in range(60)]
    track = np.concatenate([np.tile([1165.0, 300.0], (60, 1)), flight(30, 1165, -20.0), np.full((300, 2), np.nan)])

    def test_ends_when_the_ball_stops_or_at_a_whistle_before_never_at_the_go_or_a_late_whistle(self):
        # The go at 1 s sounds during the stand; the ball stops at frame 89, so the whistle at 5 s
        # (2 s later: the next rally's go) does not stretch the rally, and one at 2.5 s ends it.
        assert served(self.server, self.track, [(1.0, 1.4), (5.0, 5.3)], FPS, self.calibration) == [(59, 89, 1)]
        assert served(self.server, self.track, [(1.0, 1.4), (2.5, 2.8)], FPS, self.calibration) == [(59, 75, 1)]

    def test_a_serve_into_the_net_is_a_serve(self):
        # The ball stops 100 px before the net (under NET_NEAR, at this court's scale); 345 px is too far.
        netted = np.concatenate([np.tile([1165.0, 300.0], (60, 1)), flight(22, 1165, -20.0), np.full((300, 2), np.nan)])
        short = np.concatenate([np.tile([1165.0, 300.0], (60, 1)), flight(10, 1165, -20.0), np.full((300, 2), np.nan)])

        assert [(s, side) for s, _, side in served(self.server, netted, [], FPS, self.calibration)] == [(59, 1)]
        assert served(self.server, short, [], FPS, self.calibration) == []

    def test_ends_with_the_ball_run_without_a_whistle(self):
        assert served(self.server, self.track, [(1.0, 1.4)], FPS, self.calibration) == [(59, 89, 1)]

    def test_the_next_server_s_stand_caps_a_rally_only_when_it_starts_after_the_serve(self):
        # The next server, at the left end, already stands there from 1 s and serves at 400.
        servers = self.server + [(f, -10.5, 0.0) for f in range(30, 401)]
        track = np.concatenate([self.track[:90], np.full((250, 2), np.nan), np.tile([115.0, 300.0], (61, 1)), flight(30, 115, 20.0), np.full((300, 2), np.nan)])

        assert served(servers, track, [(1.0, 1.4)], FPS, self.calibration)[0] == (59, 89, 1)

    def test_a_stand_without_a_ball_crossing_is_no_serve(self):
        held = np.concatenate([np.tile([1165.0, 300.0], (90, 1)), np.full((300, 2), np.nan)])

        assert served(self.server, held, [(5.0, 5.3)], FPS, self.calibration) == []

    def test_with_serves_adds_the_served_rallies_serving_in_none_joined_to_the_one_they_run_into(self):
        assert with_serves([(100, 200)], [(150, 300, 1), (400, 500, -1)]) == [(100, 200), (400, 500)]
        # Served 20 frames before a rally's start (under `lead`): the same rally.
        assert with_serves([(100, 200)], [(80, 190, 1)], 30) == [(100, 200)]
        # A rally found running from inside a served one, or starting under `gap` after it, is the same.
        assert with_serves([(300, 400)], [(100, 350, 1)], 30) == [(100, 400)]
        assert with_serves([(300, 400)], [(100, 250, 1)], 30, 60) == [(100, 400)]
        assert with_serves([(300, 400)], [(100, 200, 1)], 30, 60) == [(100, 200), (300, 400)]
        # Two served ones under `gap` apart too.
        assert with_serves([], [(100, 200, 1), (230, 280, -1)], 30, 60) == [(100, 280)]
