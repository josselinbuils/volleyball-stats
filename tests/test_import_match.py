import json
import subprocess
import sys

import pytest

from volleyball_stats import import_match
from volleyball_stats.import_match import Chapter, concat_list, probe, recordings, videos


class TestImport:
    @staticmethod
    def chapter(folder, stamp, number, seconds=2):
        path = folder / f"DJI_{stamp}_{number:04d}_D.MP4"
        lavfi = ["-f", "lavfi", "-i", f"testsrc2=size=64x36:rate=25:duration={seconds}", "-f", "lavfi", "-i", f"sine=duration={seconds}"]
        subprocess.run(["ffmpeg", "-v", "error", *lavfi, "-c:v", "libx264", "-g", "25", "-c:a", "aac", "-y", str(path)], check=True)
        return path

    @classmethod
    def card(cls, tmp_path):
        folder = tmp_path / "card" / "DCIM" / "DJI_001"
        folder.mkdir(parents=True)
        for k in range(3):
            cls.chapter(folder, f"2026110221043{k * 2}", k + 2)
        (folder / "DJI_20261102210430_0002_D.LRF").write_bytes(b"proxy")
        (folder / "._DJI_20261102210430_0002_D.MP4").write_bytes(b"macos")
        return tmp_path / "card"

    @staticmethod
    def run(monkeypatch, tmp_path, *args):
        argv = ["import_match", *args, "--data", str(tmp_path / "data"), "--out", str(tmp_path / "outputs")]
        monkeypatch.setattr(sys, "argv", argv)
        import_match.main()

    def test_joins_a_card_into_a_folder_named_like_the_hosted_page(self, tmp_path, monkeypatch):
        self.run(monkeypatch, tmp_path, str(self.card(tmp_path)), "--teams", "AVIA 01,ASPOM 02:rouge")
        name = "2026-11-02-avia-01-vs-aspom-02"

        video = probe(tmp_path / "data" / name / f"{name}.mp4")
        assert video.frames == 150
        saved = json.loads((tmp_path / "outputs" / name / "teams.json").read_text())
        assert saved["date"] == "2026-11-02"
        assert [t["name"] for t in saved["teams"]] == ["AVIA 01", "ASPOM 02"]
        assert saved["teams"][1]["colour"]
        assert (tmp_path / "outputs" / name / "start.jpg").exists()
        assert sorted(p.name for p in (tmp_path / "data" / name).iterdir()) == [f"{name}.mp4"]

    def test_cuts_from_the_keyframe_before_the_start(self, tmp_path, monkeypatch):
        self.run(monkeypatch, tmp_path, str(self.card(tmp_path)), "--teams", "A,B", "--from", "2.4", "--to", "5", "--date", "03/11/2026")

        video = probe(tmp_path / "data" / "2026-11-03-a-vs-b" / "2026-11-03-a-vs-b.mp4")
        assert 2.5 <= video.duration <= 3.1

    def test_refuses_a_video_already_imported(self, tmp_path, monkeypatch):
        card = self.card(tmp_path)
        self.run(monkeypatch, tmp_path, str(card), "--teams", "A,B")

        with pytest.raises(SystemExit):
            self.run(monkeypatch, tmp_path, str(card), "--teams", "A,B")

    def test_asks_which_recording_when_the_card_holds_several(self, tmp_path, monkeypatch, capsys):
        card = self.card(tmp_path)
        self.chapter(card / "DCIM" / "DJI_001", "20261102230000", 9)

        with pytest.raises(SystemExit):
            self.run(monkeypatch, tmp_path, str(card), "--teams", "A,B")
        assert "2 recordings" in capsys.readouterr().err

        self.run(monkeypatch, tmp_path, str(card), "--teams", "A,B", "--recording", "2")
        assert probe(tmp_path / "data" / "2026-11-02-a-vs-b" / "2026-11-02-a-vs-b.mp4").frames == 50

    def test_refuses_a_team_without_a_name(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            self.run(monkeypatch, tmp_path, str(self.card(tmp_path)), "--teams", "A")

    def test_previews_a_picture_of_the_joined_recording(self, tmp_path):
        chapters = recordings([probe(p) for p in videos(self.card(tmp_path))])[0]
        for at in (0.0, 3.0, 6.0, 99.0):
            assert import_match.frame_at(chapters, at, 32)[:2] == b"\xff\xd8"

    def test_finds_only_the_videos_in_the_camera_s_order(self, tmp_path):
        assert [p.name[-10:] for p in videos(self.card(tmp_path))] == ["0002_D.MP4", "0003_D.MP4", "0004_D.MP4"]


class TestConcatList:
    chapters = [Chapter(import_match.Path(f"/c/{k}.mp4"), 10.0, 0) for k in range(3)]

    def test_lists_every_chapter_without_a_cut(self):
        assert concat_list(self.chapters, None, None) == "file '/c/0.mp4'\nfile '/c/1.mp4'\nfile '/c/2.mp4'\n"

    def test_leaves_out_the_chapters_outside_the_cut_and_cuts_inside_the_others(self):
        assert concat_list(self.chapters, 12.5, 25.0) == "file '/c/1.mp4'\ninpoint 2.500\nfile '/c/2.mp4'\noutpoint 5.000\n"

    def test_previews_inside_the_chapter_holding_the_time(self, monkeypatch):
        asked = []
        monkeypatch.setattr(import_match.subprocess, "run", lambda command, **_: asked.append(command) or subprocess.CompletedProcess(command, 0, b"\xff\xd8"))
        for at in (12.5, 30.0):
            import_match.frame_at(self.chapters, at)
        assert [(c[c.index("-i") + 1], c[c.index("-ss") + 1]) for c in asked] == [("/c/1.mp4", "2.50"), ("/c/2.mp4", "10.00")]

    def test_quotes_an_apostrophe(self):
        assert "it'\\''s" in concat_list([Chapter(import_match.Path("/it's.mp4"), 1.0, 0)], None, None)


class TestRecordings:
    @staticmethod
    def at(stamp, duration=290.0):
        return Chapter(import_match.Path(f"DJI_{stamp}_0001_D.MP4"), duration, 0)

    def test_chapters_following_each_other_are_one_recording(self):
        assert len(recordings([self.at("20261102210430", 289.9), self.at("20261102210921"), self.at("20261102211412")])) == 1

    def test_a_pause_starts_a_new_recording(self):
        assert [len(g) for g in recordings([self.at("20261102210430"), self.at("20261102220000")])] == [1, 1]

    def test_names_without_a_time_are_one_recording(self):
        chapters = [Chapter(import_match.Path("a.mp4"), 10.0, 0), Chapter(import_match.Path("b.mp4"), 10.0, 0)]
        assert len(recordings(chapters)) == 1
