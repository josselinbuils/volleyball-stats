import os

from volleyball_stats import backup_remote
from volleyball_stats.backup import held, kept, listed, newest, rsync_command, signature, sources, stale, vanished


class TestSources:
    def test_the_match_and_what_sits_in_the_outputs_folder(self, tmp_path):
        match = tmp_path / "matches" / "first_match"
        match.mkdir(parents=True)
        (tmp_path / "courts").mkdir()
        (tmp_path / "court").mkdir()
        (tmp_path / "roster.json").write_text("{}")
        (tmp_path / "club").mkdir()
        (tmp_path / "feedback").mkdir()
        (tmp_path / "hosted").mkdir()
        assert [p.name for p in sources(match) if p.is_relative_to(tmp_path)] == ["first_match", "courts", "court", "roster.json", "club", "feedback"]


class TestSignature:
    def test_moves_with_a_file_copied_not_with_one_skipped(self, tmp_path):
        (tmp_path / "site").mkdir()
        (tmp_path / "answers.json").write_text("a")
        os.utime(tmp_path / "answers.json", (100, 100))
        first = signature([tmp_path])
        assert first == (1, 100)
        (tmp_path / "site" / "data.js").write_text("b")
        (tmp_path / ".answers.json.1.tmp").write_text("c")
        (tmp_path / "photos_stale").touch()
        assert signature([tmp_path]) == first
        os.utime(tmp_path / "answers.json", (200, 200))
        assert signature([tmp_path]) == (1, 200)

    def test_a_link_to_the_video_is_not_read(self, tmp_path):
        (tmp_path / "video.mp4").symlink_to(tmp_path / "gone.mp4")
        assert signature([tmp_path]) == (0, 0.0)


class TestVanished:
    def test_a_file_gone_during_the_copy_is_no_failure(self):
        assert vanished("rsync(63518): error: outputs/m/photos_stale: open (2) in /x: No such file or directory\n")
        assert not vanished("ssh: connect to host 1.2.3.4 port 22: Connection refused\n")
        assert not vanished("")


class TestStale:
    def test_all_but_the_last_ones(self):
        assert stale({"2026-01-03": set(), "2026-01-01": set(), "2026-01-02": set()}, 2) == ["2026-01-01"]
        assert stale({"2026-01-01": set()}, 2) == []

    def test_keeps_a_match_s_newest_copy_however_old(self):
        days = {"2026-01-01": {"a", "b"}, "2026-01-02": {"a"}, "2026-01-03": {"a"}, "2026-01-04": {"a"}}
        assert stale(days, 2) == ["2026-01-02"]


class TestListed:
    def test_the_free_room_the_settings_and_each_day_s_matches(self):
        free, settings, days = listed("/dev/sda1 1 2 2097152 1% /\n{\"keep\": 5}\n2026-01-01/\n2026-01-01/a/source.json\n")
        assert (free, settings, days) == (2.0, {"keep": 5}, {"2026-01-01": {"a"}})
        assert kept(settings) == 5 and kept({}) == 30 and kept({"keep": 0}) == 30

    def test_each_match_s_newest_copy(self):
        assert newest({"2026-01-01": {"a", "b"}, "2026-01-02": {"a"}}) == {"a": "2026-01-02", "b": "2026-01-01"}


class TestHeld:
    def test_each_day_s_matches_from_the_listing(self):
        listing = "2026-01-01/\n2026-01-02/\nclaims/\n2026-01-01/a/source.json\n2026-01-02/b/source.json\n"
        assert held(listing) == {"2026-01-01": {"a"}, "2026-01-02": {"b"}}


class TestRsyncCommand:
    def test_leaves_out_the_old_copies_and_pages(self, tmp_path):
        out = rsync_command([tmp_path], "root@host", ["ssh"], "/root/b", "2026-01-02")
        assert {"--exclude=backup-*", "--exclude=review", "--exclude=site"} <= set(out)
        assert out[-2:] == [str(tmp_path), "root@host:/root/b/2026-01-02/"]


class TestSnapshot:
    def test_the_day_starts_as_the_one_before_hard_linked_once(self, tmp_path):
        (tmp_path / "2026-01-01" / "a").mkdir(parents=True)
        (tmp_path / "2026-01-01" / "a" / "x").write_text("old")
        for _ in range(2):
            backup_remote.snapshot(str(tmp_path), "2026-01-02", "2026-01-01")
        copied = tmp_path / "2026-01-02" / "a" / "x"
        assert copied.read_text() == "old" and copied.stat().st_ino == (tmp_path / "2026-01-01" / "a" / "x").stat().st_ino
        assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-01-01", "2026-01-02"]
