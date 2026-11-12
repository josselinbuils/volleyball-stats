import numpy as np

from volleyball_stats import playing

FPS = 50.0
# A P(play) every 0.25 s over 60 s.
TIMES = np.arange(0, 60, 0.25)


def play(*spans: tuple[float, float]) -> np.ndarray:
    """P(play) high inside the spans of seconds, low elsewhere."""
    p = np.full(len(TIMES), 0.05)
    for start, end in spans:
        p[(TIMES >= start) & (TIMES <= end)] = 0.95
    return p


def seconds(windows: list[tuple[int, int]]) -> list[tuple[float, float]]:
    return [(s / FPS, e / FPS) for s, e in windows]


class TestLive:
    def test_bridges_a_short_dip_between_two_live_moments(self):
        p = play((10, 12), (12.75, 15))

        assert playing.live(p, 0.25)[(TIMES >= 10) & (TIMES <= 15)].all()

    def test_a_long_dip_stays(self):
        p = play((10, 12), (14, 15))

        assert not playing.live(p, 0.25)[TIMES == 13][0]


class TestMoved:
    def test_an_end_is_carried_on_through_play(self):
        windows = [(500, 750), (1500, 1750)]

        assert seconds(playing.moved(windows, FPS, TIMES, play((10, 20), (30, 35)), ("ends",))) == [(10.0, 20.0), (30.0, 35.0)]

    def test_an_end_stops_before_the_next_window(self):
        windows = [(500, 750), (900, 1000)]
        lead = playing.actions.LEAD_S

        moved = seconds(playing.moved(windows, FPS, TIMES, play((10, 25)), ("ends",)))

        assert 15.0 < moved[0][1] <= 18.0 - lead

    def test_an_end_with_no_play_after_it_stays(self):
        windows = [(500, 750)]

        assert playing.moved(windows, FPS, TIMES, play((10, 15.5)), ("ends",)) == windows

    def test_a_start_is_pulled_back_to_where_play_began(self):
        windows = [(1000, 1500)]

        (start, end), = seconds(playing.moved(windows, FPS, TIMES, play((12, 30)), ("starts",)))

        assert abs(start - (12.0 + playing.actions.LEAD_S)) <= 1 / FPS and end == 30.0

    def test_a_start_never_goes_into_the_previous_window(self):
        windows = [(500, 800), (1000, 1500)]

        moved = seconds(playing.moved(windows, FPS, TIMES, play((12, 30)), ("starts",)))

        assert moved[1][0] >= 16.0

    def test_without_its_use_nothing_moves(self):
        windows = [(500, 750)]

        assert playing.moved(windows, FPS, TIMES, play((5, 30)), ("keep", "alive")) == windows


class TestConfirmed:
    def test_keeps_the_windows_with_play_all_along(self):
        windows = [(500, 1000), (1500, 2000)]

        assert playing.confirmed(windows, FPS, TIMES, play((9, 21), (30, 33))) == {0}


class TestGoesOn:
    def test_play_all_through_the_seconds_after_a_frame(self):
        alive = playing.goes_on(TIMES, play((10, 20)), FPS)

        assert alive(600) and alive(round(16.5 * FPS))
        assert not alive(round(18 * FPS)) and not alive(1500)

    def test_nothing_goes_on_past_the_video_s_end(self):
        assert not playing.goes_on(TIMES, play((50, 60)), FPS)(round(58.5 * FPS))


class TestWanted:
    def test_runs_only_with_its_weights_on_the_camera_s_footage(self, tmp_path, monkeypatch):
        monkeypatch.setattr(playing.decode, "size", lambda video: (3840, 2160))
        monkeypatch.setattr(playing, "WEIGHTS", tmp_path)
        assert not playing.wanted(tmp_path / "match.mp4")

        (tmp_path / "model.safetensors").touch()
        assert playing.wanted(tmp_path / "match.mp4")

        monkeypatch.setattr(playing.decode, "size", lambda video: (1280, 720))
        assert not playing.wanted(tmp_path / "clip.mp4")


class TestLoad:
    def test_reads_the_clips_middles_and_every_use_by_default(self, tmp_path):
        np.savez(tmp_path / "play.npz", starts=np.array([0, 2, 4]), p=np.array([0.1, 0.9, 0.8]), fps=8, T=16)

        times, p, uses = playing.load(tmp_path / "play.npz")

        assert times.tolist() == [1.0, 1.25, 1.5] and p.tolist() == [0.1, 0.9, 0.8] and uses == playing.USES

    def test_a_benchmark_s_file_names_its_uses(self, tmp_path):
        np.savez(tmp_path / "play.npz", starts=np.array([0]), p=np.array([0.1]), fps=8, T=16, uses="ends,keep")

        assert playing.load(tmp_path / "play.npz")[2] == ("ends", "keep")
