import os

from volleyball_stats.backup import rsync_command, signature, sources, stale, vanished


class TestSources:
    def test_the_match_and_what_sits_in_the_outputs_folder(self, tmp_path):
        match = tmp_path / "matches" / "first_match"
        match.mkdir(parents=True)
        (tmp_path / "courts").mkdir()
        (tmp_path / "court").mkdir()
        (tmp_path / "roster.json").write_text("{}")
        (tmp_path / "brand").mkdir()
        (tmp_path / "feedback").mkdir()
        (tmp_path / "hosted").mkdir()
        assert [p.name for p in sources(match) if p.is_relative_to(tmp_path)] == ["first_match", "courts", "court", "roster.json", "brand", "feedback"]


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
        assert stale(["2026-01-03", "2026-01-01", "2026-01-02"], 2) == ["2026-01-01"]
        assert stale(["2026-01-01"], 2) == []


class TestRsyncCommand:
    def test_links_to_the_copy_before_and_leaves_out_the_old_copies_and_pages(self, tmp_path):
        out = rsync_command([tmp_path], "root@host", ["ssh"], "/root/b", "2026-01-02", "2026-01-01")
        assert {"--exclude=backup-*", "--exclude=review", "--exclude=site", "--link-dest=/root/b/2026-01-01"} <= set(out)
        assert out[-2:] == [str(tmp_path), "root@host:/root/b/2026-01-02/"]
        assert not any(a.startswith("--link-dest") for a in rsync_command([tmp_path], "root@host", ["ssh"], "/root/b", "2026-01-02", None))
