import numpy as np
import pytest
import torch

from volleyball_stats import ball, decode, match, players, resume

FRAMES, FPS = 100, 10.0
TRACKED = match.tracked


class Counting:
    """A tracker whose rows depend on every frame before: started again from a pickled copy, it carries on."""

    def __init__(self):
        self.seen = 0


def counted_rows(frames, calibration, model, device, tracker=None, size=None, fps=30.0, first=0):
    for index, frame in enumerate(frames, first):
        tracker.seen += int(frame[0, 0, 0])
        yield [players.Row(index, 1 + tracker.seen % 3, (1.0, 2.0, 3.0, 4.0), 0.9, (2.0, 4.0), (0.5, 1.0))]


def fake_frames(video, count=None, first=0):
    last = FRAMES if count is None else first + count
    for index in range(first, last):
        frame = np.zeros((ball.HEIGHT, ball.WIDTH, 3), np.uint8)
        frame[0, 0, 0] = index % 7 + 1
        frame[1, 0, 0] = index % 250
        yield frame


class Heatmaps(torch.nn.Module):
    """A ball model whose peaks depend on the window's frames and on its place in its batch: a frame's ball is the same
    only when its windows run in the same batches."""

    def forward(self, inputs):
        batch, channels, height, width = inputs.shape
        out = torch.full((batch, channels // 3, height, width), -10.0)
        for b in range(batch):
            for k in range(channels // 3):
                seen = int(round(float(inputs[b, 3 * k + 2, 1, 0] * ball.IMAGENET_STD[2] + ball.IMAGENET_MEAN[2]) * 255))
                out[b, k, 20, (seen * 2 + b) % width] = 2.0 + 0.1 * ((b + k) % 4)
        return [out]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(decode, "frames", fake_frames)
    monkeypatch.setattr(decode, "size", lambda video: (ball.WIDTH, ball.HEIGHT))
    monkeypatch.setattr(ball, "default_device", lambda: "cpu")
    monkeypatch.setattr(ball, "load_model", lambda device: Heatmaps())
    monkeypatch.setattr(players, "load_model", lambda: None)
    monkeypatch.setattr(players, "track_frames", counted_rows)
    monkeypatch.setattr(players, "make_tracker", lambda fps=30.0: Counting())


class TestTracked:
    def test_from_a_part_s_start_it_gives_what_a_pass_from_the_start_gives_there(self, fakes):
        full = list(match.tracked(None, None, True, True, FPS, tracker=Counting()))
        at = Counting()
        at.seen = sum(i % 7 + 1 for i in range(2 * resume.LEAD))
        again = list(match.tracked(None, None, True, True, FPS, first=2 * resume.LEAD, tracker=at))

        assert len(full) == FRAMES and any(b for b, _ in full)
        assert [(b, [(r.frame, r.track) for r in rows]) for b, rows in again] == [(b, [(r.frame, r.track) for r in rows]) for b, rows in full[2 * resume.LEAD :]]

    def test_the_ball_alone_too(self, fakes):
        full = list(match.tracked(None, None, True, False, FPS))
        assert list(match.tracked(None, None, True, False, FPS, first=resume.LEAD)) == full[resume.LEAD :]


class Stopped(Exception):
    pass


class TestTrack:
    def run(self, out, monkeypatch, stop_at=None):
        def stopping(*args, **kwargs):
            for index, item in enumerate(TRACKED(*args, **kwargs), kwargs.get("first", 0)):
                if index == stop_at:
                    raise Stopped
                yield item

        monkeypatch.setattr(match, "tracked", stopping)
        out.mkdir(exist_ok=True)
        match.track(out / "video.mp4", None, FPS, out / "ball.csv", out / "players.csv", FRAMES)

    def test_a_pass_stopped_twice_then_started_again_writes_the_tracks_of_one_never_stopped(self, fakes, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(resume, "CHUNK", 2 * resume.LEAD)
        self.run(tmp_path / "once", monkeypatch)
        stopped = tmp_path / "stopped"
        for at in (45, 81):
            with pytest.raises(Stopped):
                self.run(stopped, monkeypatch, at)
            # The parts kept up to the last whole one.
            assert resume.done(stopped) == pytest.approx((at // resume.CHUNK * resume.CHUNK) / FRAMES)
        self.run(stopped, monkeypatch)

        for name in ("ball.csv", "players.csv"):
            assert (stopped / name).read_bytes() == (tmp_path / "once" / name).read_bytes()
        assert not (stopped / resume.FOLDER).exists() and resume.done(stopped) == 0.0
        assert "Tracking from frame 64" in capsys.readouterr().out

    def test_parts_of_another_video_or_code_start_over(self, fakes, tmp_path, monkeypatch):
        monkeypatch.setattr(resume, "CHUNK", 2 * resume.LEAD)
        with pytest.raises(Stopped):
            self.run(tmp_path, monkeypatch, 70)
        monkeypatch.setattr(resume, "stamp", lambda *args: "changed")
        starts = []
        monkeypatch.setattr(match, "tracked", lambda *args, **kwargs: starts.append(kwargs["first"]) or TRACKED(*args, **kwargs))
        match.track(tmp_path / "video.mp4", None, FPS, tmp_path / "ball.csv", tmp_path / "players.csv", FRAMES)
        assert starts == [0]

    def test_a_part_cut_short_is_left_out(self, tmp_path):
        folder = tmp_path / resume.FOLDER
        resume.start(folder, "k", 100)
        resume.save(folder, resume.CHUNK, [[0, 0, "", ""]], [], Counting())
        resume.part(folder, 2 * resume.CHUNK).write_bytes(b"\x80\x05cut")
        first, positions, _, tracker = resume.kept(folder, "k")
        assert (first, positions, type(tracker)) == (resume.CHUNK, [[0, 0, "", ""]], Counting)


def test_the_backups_and_the_hosted_pages_leave_the_parts_out():
    from volleyball_stats import backup, matches

    assert resume.FOLDER in backup.SKIP and resume.FOLDER in matches.MADE_SKIP
    assert resume.LEAD == ball.BATCH * ball.STRIDE and resume.CHUNK % resume.LEAD == 0
