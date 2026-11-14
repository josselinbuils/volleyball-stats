import subprocess

import pytest

from volleyball_stats import video_copies


class TestVideoCopies:
    @staticmethod
    def clip(path, seconds=2):
        command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=640x360:r=50:d={seconds}", "-f", "lavfi", "-i", f"sine=d={seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)]
        subprocess.run(command, check=True)

    @staticmethod
    def stream(path):
        run = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,height,r_frame_rate", "-of", "csv=p=0", str(path)]
        return subprocess.run(run, capture_output=True, text=True, check=True).stdout.strip()

    def test_makes_the_three_copies_on_the_sources_timeline(self, tmp_path):
        video = tmp_path / "m.mp4"
        self.clip(video)

        made = video_copies.make(video)

        assert self.stream(made["light"]) == "h264,1440,25/1"
        assert self.stream(made["av1"]) == "av1,1440,25/1"
        assert self.stream(made["small"]) == "h264,720,25/1"
        assert all(video_copies.duration(path) == pytest.approx(2.0, abs=0.1) for path in made.values())
        assert sorted(p.name for p in (tmp_path / "reencoded").iterdir()) == ["m_1440p.mp4", "m_720p.mp4", "m_av1.mp4"]

    def test_only_those_missing(self, tmp_path, monkeypatch):
        video = tmp_path / "m.mp4"
        video_copies.paths(video)["light"].parent.mkdir()
        video_copies.paths(video)["light"].write_bytes(b"")
        monkeypatch.setattr(video_copies, "height", lambda path: 1440 if path.exists() else None)
        ran = []
        monkeypatch.setattr(video_copies.subprocess, "run", lambda command, **kwargs: ran.append(command) or subprocess.CompletedProcess(command, 1, "", "no encoder"))
        monkeypatch.setattr(video_copies.decode, "hardware", lambda path: ())

        with pytest.raises(RuntimeError, match="no encoder"):
            video_copies.make(video)

        written = [arg for arg in ran[0] if arg.endswith(".part.mp4")]
        assert [p.rsplit("/", 1)[1] for p in written] == ["m_av1.part.mp4", "m_720p.part.mp4"]

    def test_a_copy_cut_short_does_not_appear(self, tmp_path, monkeypatch):
        video = tmp_path / "m.mp4"
        self.clip(video)
        monkeypatch.setattr(video_copies, "TOLERANCE_S", -1.0)

        with pytest.raises(RuntimeError, match="lasts"):
            video_copies.make(video)

        assert sorted(p.name for p in tmp_path.iterdir()) == ["m.mp4", "reencoded"] and not any((tmp_path / "reencoded").iterdir())

    def test_makes_again_a_copy_at_a_former_height_and_keeps_those_listed_elsewhere(self, tmp_path, monkeypatch):
        video = tmp_path / "m.mp4"
        paths = video_copies.paths(video)
        paths["av1"].parent.mkdir()
        old_small = tmp_path / "reencoded" / "old_720p.mp4"
        for path, h in ((paths["av1"], 1080), (paths["light"], 1440), (old_small, 720)):
            path.write_text(str(h))
        monkeypatch.setattr(video_copies, "height", lambda path: int(path.read_text()) if path.exists() else None)
        ran = []
        monkeypatch.setattr(video_copies.subprocess, "run", lambda command, **kwargs: ran.append(command) or subprocess.CompletedProcess(command, 1, "", "no encoder"))
        monkeypatch.setattr(video_copies.decode, "hardware", lambda path: ())

        with pytest.raises(RuntimeError, match="no encoder"):
            video_copies.make(video, {"small": old_small})

        assert [p.rsplit("/", 1)[1] for p in ran[0] if p.endswith(".part.mp4")] == ["m_av1.part.mp4"]
