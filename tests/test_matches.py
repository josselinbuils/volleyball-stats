import gzip
import json
from pathlib import Path

import cv2
import pytest

from volleyball_stats import matches
from volleyball_stats.matches import build


class TestBuild:
    def test_lists_the_match_pages_newest_first_and_loads_the_list_by_its_hash(self, tmp_path):
        for name, date in (("old", "2026-09-01"), ("new", "2026-10-25")):
            (tmp_path / name).mkdir()
            data = {"name": name, "date": date, "teams": None, "rallies": [{"set": 1}, {"set": 2}, {"set": 2}]}
            (tmp_path / name / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        matches = build(tmp_path, "none")

        assert [(m["path"], m["sets"], m["rallies"]) for m in matches] == [("2026-10-25/", 2, 3), ("2026-09-01/", 2, 3)]
        assert (tmp_path / "matches.js").read_text().startswith('window.MATCHES = {"matches":[{"path":"2026-10-25/"')
        assert 'src="matches.js?v=' in (tmp_path / "index.html").read_text()
        assert not (tmp_path / "matches.html").exists()

    @staticmethod
    def page(site, folder, name, teams):
        (site / folder).mkdir(parents=True, exist_ok=True)
        data = {"name": name, "date": "2026-11-02", "teams": [{"name": t} for t in teams], "rallies": [{"set": 1}]}
        (site / folder / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")
        (site / folder / "index.html").write_text('<meta property="og:title" content="M" /><p>page</p>')

    def test_a_page_whose_address_changed_redirects_from_the_old_one_keeping_what_the_link_carries(self, tmp_path):
        self.page(tmp_path, "2026-11-02-a-vs-b", "m", ["A", "B"])
        self.page(tmp_path, "2026-11-02-a-vs-b", "m", ["A", "C"])

        listed = build(tmp_path, "none")

        assert [m["path"] for m in listed] == ["2026-11-02-a-vs-c/"]
        page = (tmp_path / "2026-11-02-a-vs-b" / "index.html").read_text()
        assert 'url=../2026-11-02-a-vs-c/"' in page and "location.search + location.hash" in page
        assert 'property="og:title"' in page and "noindex" in page
        assert 'url=../../2026-11-02-a-vs-c/video/"' in (tmp_path / "2026-11-02-a-vs-b" / "video" / "index.html").read_text()
        assert json.loads((tmp_path / "redirects.json").read_text()) == {"2026-11-02-a-vs-b": "2026-11-02-a-vs-c"}

    def test_a_page_built_for_the_first_time_leaves_no_redirect(self, tmp_path):
        self.page(tmp_path, "m", "m", ["A", "B"])

        build(tmp_path, "none")

        assert not (tmp_path / "m").exists()
        assert json.loads((tmp_path / "redirects.json").read_text()) == {}

    def test_a_second_change_sends_the_oldest_address_straight_to_the_latest(self, tmp_path):
        self.page(tmp_path, "2026-11-02-a-vs-b", "m", ["A", "C"])
        build(tmp_path, "none")
        self.page(tmp_path, "2026-11-02-a-vs-c", "m", ["A", "D"])

        build(tmp_path, "none")

        assert 'url=../2026-11-02-a-vs-d/"' in (tmp_path / "2026-11-02-a-vs-b" / "index.html").read_text()
        assert 'url=../2026-11-02-a-vs-d/"' in (tmp_path / "2026-11-02-a-vs-c" / "index.html").read_text()

    def test_a_match_taking_an_old_address_replaces_its_redirect(self, tmp_path):
        self.page(tmp_path, "2026-11-02-a-vs-b", "m", ["A", "C"])
        build(tmp_path, "none")
        self.page(tmp_path, "2026-11-02-a-vs-b", "other", ["A", "B"])

        listed = build(tmp_path, "none")

        assert sorted(m["path"] for m in listed) == ["2026-11-02-a-vs-b/", "2026-11-02-a-vs-c/"]
        assert json.loads((tmp_path / "redirects.json").read_text()) == {}

    def test_compresses_the_text_files_once_and_drops_the_copies_of_files_gone(self, tmp_path):
        (tmp_path / "m").mkdir()
        big, small = tmp_path / "m" / "players.js", tmp_path / "m" / "tiny.js"
        big.write_text("x" * 5000)
        small.write_text("x")
        (tmp_path / "m" / "video.mp4").write_bytes(b"0" * 5000)
        (tmp_path / "m" / "old.js.gz").write_bytes(b"")

        matches.compress(tmp_path)

        assert sorted(p.name for p in (tmp_path / "m").glob("*.gz")) == ["players.js.gz"]
        assert gzip.decompress((tmp_path / "m" / "players.js.gz").read_bytes()) == b"x" * 5000
        assert (tmp_path / "m" / "players.js.gz").stat().st_mtime == big.stat().st_mtime
        made = (tmp_path / "m" / "players.js.gz").stat().st_mtime_ns
        matches.compress(tmp_path)
        assert (tmp_path / "m" / "players.js.gz").stat().st_mtime_ns == made

    def test_names_each_folder_after_the_match_s_date_and_teams_a_new_build_replacing_the_old(self, tmp_path):
        teams = [{"name": "ASPOM Bègles"}, {"name": "Talence"}]
        for name, rallies in (("2026-10-25-aspom-begles-vs-talence", 1), ("full_match", 2), ("unnamed", 1)):
            (tmp_path / name).mkdir()
            data = {"name": name, "date": "2026-10-25" if name != "unnamed" else None, "teams": teams if name != "unnamed" else None, "rallies": [{"set": 1}] * rallies}
            (tmp_path / name / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        matches = build(tmp_path, "none")

        assert [(m["path"], m["rallies"]) for m in matches] == [("2026-10-25-aspom-begles-vs-talence/", 2), ("unnamed/", 1)]
        assert sorted(p.parent.name for p in tmp_path.glob("*/data.js")) == ["2026-10-25-aspom-begles-vs-talence", "unnamed"]

    def test_a_match_making_no_address_or_a_reserved_one_keeps_its_folder(self, tmp_path):
        # Videos named "_.mp4" and "brand.mp4", without teams.
        for folder, name in (("one", "_"), ("two", "brand")):
            (tmp_path / folder).mkdir()
            data = {"name": name, "date": None, "teams": None, "rallies": [{"set": 1}]}
            (tmp_path / folder / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        matches = build(tmp_path, "none")

        assert sorted(m["path"] for m in matches) == ["one/", "two/"]
        assert (tmp_path / "one" / "data.js").exists() and (tmp_path / "two" / "data.js").exists()


class TestShare:
    def page(self, folder, **extra):
        folder.mkdir(parents=True)
        (folder / "index.html").write_text('<html><head><meta name="description" content="old" /><title>Match</title></head></html>')
        data = {"name": "m", "date": "2026-10-29", "teams": [{"name": "A & B", "colour": "#151515"}, {"name": "C", "colour": "#ff0000"}], "scores": ["25-23", "12-25", "25-18"], "rallies": [], **extra}
        (folder / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

    def test_a_match_says_its_teams_score_and_picture_at_its_address_again_after_a_rebuild(self, tmp_path):
        self.page(tmp_path / "m")
        matches.share_match(tmp_path / "m", "https://x.dev/volleyball/m/")
        first = (tmp_path / "m" / "index.html").read_text()
        matches.share_match(tmp_path / "m", "https://x.dev/volleyball/m/")

        assert (tmp_path / "m" / "index.html").read_text() == first
        assert first.count('property="og:title"') == 1
        assert "<title>A &amp; B - C · 2-1</title>" in first
        assert 'content="25-23, 12-25, 25-18 · 29 octobre 2026 · Statistiques et replay du match"' in first
        assert 'content="https://x.dev/volleyball/m/preview.png?v=' in first
        assert cv2.imread(str(tmp_path / "m" / "preview.png")).shape == (630, 1200, 3)

    def test_the_sets_come_from_the_last_rallies_when_no_score_is_given(self, tmp_path):
        assert matches.set_scores({"rallies": [{"set": 1, "score": [1, 0]}, {"set": 1, "score": [25, 20]}, {"set": 2, "score": [3, 25]}]}) == [(25, 20), (3, 25)]

    def test_the_site_is_tagged_only_with_an_address(self, tmp_path):
        self.page(tmp_path / "m")
        build(tmp_path)
        assert "og:title" not in (next(tmp_path.glob("*/data.js")).parent / "index.html").read_text()
        build(tmp_path, url="https://x.dev/volleyball")
        assert 'content="https://x.dev/volleyball/2026-10-29-a-b-vs-c/"' in (next(tmp_path.glob("*/data.js")).parent / "index.html").read_text()
        assert 'content="https://x.dev/volleyball/preview.png?v=' in (tmp_path / "index.html").read_text()


class TestHost:
    def test_finds_a_video_outside_the_password_s_folder(self, tmp_path):
        (tmp_path / "m" / "video" / "films").mkdir(parents=True)
        (tmp_path / "m" / "video" / "match.mp4").write_bytes(b"")
        (tmp_path / "m" / "video" / "films" / "1-ana.mp4").write_bytes(b"")
        assert matches.unguarded_videos(tmp_path) == []
        (tmp_path / "m" / "films").mkdir()
        (tmp_path / "m" / "films" / "1-ana.mp4").write_bytes(b"")
        assert [p.name for p in matches.unguarded_videos(tmp_path)] == ["1-ana.mp4"]

    def test_stops_before_any_build_when_a_video_copy_is_missing(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(matches.web, "publish", lambda *args: built.append(args))
        config = {"site": str(tmp_path), "url": "https://example.org/", "upload": "host:/site/", "key": "key", "light": str(tmp_path / "gone.mp4")}

        with pytest.raises(RuntimeError, match="gone.mp4"):
            matches.host(Path("outputs/first"), Path("first.mp4"), Path("court.json"), "aspom", config)

        assert built == []

    def test_rebuilds_both_pages_and_uploads_only_a_copy_the_password_guards(self, tmp_path, monkeypatch):
        built, ran = [], []
        monkeypatch.setattr(matches.web, "publish", lambda *args: built.append((args[4]["footage"], args[5])) or ({}, {}))
        monkeypatch.setattr(matches, "build", lambda site, theme, url: [{"name": "first", "path": "2026-10-29-a-vs-b/"}])
        monkeypatch.setattr(matches.subprocess, "run", lambda command, **kwargs: ran.append(command))
        config = {"site": str(tmp_path), "url": "https://example.org/volleyball/", "upload": "host:/site/", "key": "~/.ssh/key"}
        args = (Path("outputs/first"), Path("first.mp4"), Path("court.json"), "aspom", config)

        monkeypatch.setattr(matches, "protected", lambda url: False)
        with pytest.raises(RuntimeError):
            matches.host(*args)

        assert built == [("full", tmp_path / "first" / "video"), ("none", tmp_path / "first")] and ran == []
        monkeypatch.setattr(matches, "protected", lambda url: url == "https://example.org/volleyball/2026-10-29-a-vs-b/video/")
        matches.host(*args)
        assert ran[0][:3] == ["rsync", "-rt", "--delete"] and ran[0][-2:] == [f"{tmp_path}/", "host:/site/"]


class TestEnsurePublish:
    @staticmethod
    def imported(tmp_path, name="2026-11-02-avia-1-vs-aspom-2"):
        match = tmp_path / "outputs" / name
        match.mkdir(parents=True)
        (match / "teams.json").write_text(json.dumps({"teams": [{"name": "AVIA 1"}, {"name": "ASPOM 2"}]}))
        return match, tmp_path / "data" / name / f"{name}.mp4"

    @staticmethod
    def hosted(tmp_path):
        other = tmp_path / "outputs" / "2026-10-29-a-vs-b"
        other.mkdir(parents=True)
        (other / matches.PUBLISH).write_text(json.dumps({"site": "outputs/hosted", "url": "https://example.org/", "upload": "host:/site/", "key": "key", "light": "old.mp4", "club": 1}))

    def test_takes_the_hosting_from_another_match_with_its_own_copies_and_club(self, tmp_path):
        self.hosted(tmp_path)
        match, video = self.imported(tmp_path)

        matches.ensure_publish(match, video, "aspom")

        config = json.loads((match / matches.PUBLISH).read_text())
        assert (config["site"], config["url"], config["upload"], config["key"]) == ("outputs/hosted", "https://example.org/", "host:/site/", "key")
        assert config["club"] == 2
        assert config["light"].endswith("2026-11-02-avia-1-vs-aspom-2_1080p.mp4")

    def test_keeps_an_existing_config(self, tmp_path):
        self.hosted(tmp_path)
        match, video = self.imported(tmp_path)
        (match / matches.PUBLISH).write_text("{}")

        matches.ensure_publish(match, video, "aspom")

        assert (match / matches.PUBLISH).read_text() == "{}"

    def test_none_without_another_match_hosted(self, tmp_path):
        match, video = self.imported(tmp_path)

        matches.ensure_publish(match, video, "aspom")

        assert not (match / matches.PUBLISH).exists()

    def test_none_for_a_test_clip(self, tmp_path):
        self.hosted(tmp_path)
        match, _ = self.imported(tmp_path, "side_setend")

        matches.ensure_publish(match, tmp_path / "data" / "side_setend.mp4", "aspom")

        assert not (match / matches.PUBLISH).exists()


class TestClubTeam:
    @pytest.mark.parametrize("names, expected", [(["AVIA 1", "ASPOM 2"], 2), (["ASPOM 1", "ASPOM 2"], 1), (["A", "B"], 1)])
    def test_the_first_team_of_the_club(self, tmp_path, names, expected):
        (tmp_path / "teams.json").write_text(json.dumps({"teams": [{"name": n} for n in names]}))

        assert matches.club_team(tmp_path, "aspom") == expected
