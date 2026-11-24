import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from volleyball_stats import backup, files, matches, sync
from volleyball_stats.matches import build


@pytest.fixture(autouse=True)
def timings(tmp_path, monkeypatch):
    """An update's durations kept in the test's folder, whatever the matches' paths."""
    monkeypatch.setattr(matches, "TIMINGS", str(tmp_path / matches.TIMINGS))


# The tests' copies are placeholders: there, they are as made today.
CURRENT = matches.video_copies.current


@pytest.fixture(autouse=True)
def placeholder_copies(monkeypatch):
    monkeypatch.setattr(matches.video_copies, "current", lambda key, path: path.exists())


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

    def test_each_match_page_and_its_video_one_link_back_to_the_list_once(self, tmp_path):
        self.page(tmp_path, "2026-11-02-a-vs-b", "m", ["A", "B"])
        (tmp_path / "2026-11-02-a-vs-b" / "video").mkdir()
        for index in (tmp_path / "2026-11-02-a-vs-b" / "index.html", tmp_path / "2026-11-02-a-vs-b" / "video" / "index.html"):
            index.write_text("<html><head>\n  </head><body></body></html>")

        build(tmp_path, "none")
        build(tmp_path, "none")

        page, video = ((tmp_path / "2026-11-02-a-vs-b" / f).read_text() for f in ("index.html", "video/index.html"))
        assert page.count('<meta name="list" content="../" />') == 1 and 'name="list"' not in page.replace('<meta name="list" content="../" />', "")
        assert video.count('<meta name="list" content="../../" />') == 1

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
        # Videos named "_.mp4" and "club.mp4", without teams.
        for folder, name in (("one", "_"), ("two", "club")):
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

    def test_a_set_not_given_takes_its_last_rally(self, tmp_path):
        rallies = [{"set": 1, "score": [25, 20]}, {"set": 2, "score": [3, 25]}]
        assert matches.set_scores({"rallies": rallies, "scores": [None, None]}) == [(25, 20), (3, 25)]
        assert matches.set_scores({"rallies": rallies, "scores": ["25-23", None]}) == [(25, 23), (3, 25)]

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

    @pytest.mark.parametrize("code, location, expected", [(302, "/volleyball/m/?video=denied", True), (403, None, False), (302, "/elsewhere", False)])
    def test_protected_only_by_the_redirect_to_the_password(self, monkeypatch, code, location, expected):
        import email.message
        import urllib.error

        def refuse(url, headers=None):
            sent = email.message.Message()
            if location:
                sent["Location"] = location
            raise urllib.error.HTTPError(url, code, "", sent, None)

        monkeypatch.setattr(matches, "_head", refuse)
        assert matches.protected("https://example.org/volleyball/m/video/") is expected

    def test_head_tries_again_after_a_network_failure_then_says_so(self, monkeypatch):
        import urllib.error

        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                if len(calls) < 3:
                    raise urllib.error.URLError(TimeoutError("_ssl.c:983: The handshake operation timed out"))
                return "answer"

        monkeypatch.setattr(matches.urllib.request, "build_opener", lambda *handlers: Opener())
        assert matches._head("https://example.org/v/", wait=0) == "answer"
        assert len(calls) == 3
        calls.clear()
        monkeypatch.setattr(matches, "HEAD_TRIES", 2)
        with pytest.raises(RuntimeError, match="example.org did not answer .*handshake.*: nothing uploaded"):
            matches._head("https://example.org/v/", wait=0)
        assert len(calls) == 2

    def test_stops_before_any_build_when_a_video_copy_is_missing(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(matches.web, "publish", lambda *args: built.append(args))
        config = {"site": str(tmp_path), "url": "https://example.org/", "upload": "host:/site/", "key": "key", "video": True, "light": str(tmp_path / "gone.mp4")}

        with pytest.raises(RuntimeError, match="light"):
            matches.host(Path("outputs/first"), Path("first.mp4"), Path("court.json"), "aspom", config)

        assert built == []

    @staticmethod
    def hosting(tmp_path, monkeypatch, **config):
        built, ran = [], []
        monkeypatch.setattr(matches, "head_commit", lambda: "c0ffee")
        monkeypatch.setattr(matches, "ensure_review_page", lambda *args: None)
        monkeypatch.setattr(matches, "make_voice", lambda match: built.append(("voice", match)))
        monkeypatch.setattr(matches.web, "publish", lambda *args: built.append((args[4]["footage"], args[4].get("link"), args[5])) or args[5].mkdir(parents=True, exist_ok=True) or ({}, {}))
        monkeypatch.setattr(matches.web, "computed", lambda *args: ({}, None))
        monkeypatch.setattr(matches, "build", lambda site, theme, url, retired=None: [{"name": "first", "path": "2026-10-29-a-vs-b/"}])
        monkeypatch.setattr(matches.subprocess, "run", lambda command, **kwargs: ran.append(command) or matches.subprocess.CompletedProcess(command, 0, ""))
        monkeypatch.setattr(backup, "free_gb", lambda host, ssh, folder: 100.0)
        monkeypatch.setattr(matches, "counted", lambda command, total, share=None: ran.append(command))
        monkeypatch.setattr(matches, "opens", lambda url, key: True)
        site = tmp_path / "site"
        site.mkdir()
        full = {"site": str(site), "url": "https://example.org/volleyball/", "upload": "host:/srv/service/site/", "key": "~/.ssh/key", **config}
        (tmp_path / "first.mp4").write_bytes(b"")
        return (Path("outputs/first"), tmp_path / "first.mp4", Path("court.json"), "aspom", full), built, ran, site

    @staticmethod
    def copies(tmp_path):
        made = {key: tmp_path / f"{key}.mp4" for key in ("light", "av1", "small")}
        for path in made.values():
            path.write_bytes(b"")
        return {key: str(path) for key, path in made.items()}

    def test_with_the_video_uploads_only_a_copy_the_password_guards_with_its_key_first(self, tmp_path, monkeypatch):
        args, built, ran, site = self.hosting(tmp_path, monkeypatch, video=True, **self.copies(tmp_path))
        monkeypatch.setattr(matches, "video_key", lambda outputs: "abc")

        monkeypatch.setattr(matches, "protected", lambda url: False)
        with pytest.raises(RuntimeError):
            matches.host(*args)

        assert built == [("voice", Path("outputs/first")), ("full", None, site / "first" / "video"), ("none", "video/", site / "first")]
        assert [c[:5] for c in ran] == [["rsync", "-rt", "--delete", "--include=*/video/films/*.mp4", "--exclude=*.mp4"]]
        ran.clear()
        monkeypatch.setattr(matches, "protected", lambda url: url == "https://example.org/volleyball/2026-10-29-a-vs-b/video/")
        matches.host(*args)
        assert ran[0][-2:] == ["host:/srv/service/site/", f"{site}/"]
        assert ran[1][0] == "ssh" and '"~^[^:/]+:abc$" 1;' in ran[1][-1]
        assert "--dry-run" in ran[2] and "--dry-run" not in ran[3]
        assert ran[3][:4] == ["rsync", "-rt", "--delete", "--delay-updates"] and ran[3][-2:] == [f"{site}/", "host:/srv/service/site/"]

    def test_says_so_when_its_password_does_not_open_it(self, tmp_path, monkeypatch):
        args, _, _, _ = self.hosting(tmp_path, monkeypatch, video=True, **self.copies(tmp_path))
        monkeypatch.setattr(matches, "video_key", lambda outputs: "abc")
        monkeypatch.setattr(matches, "protected", lambda url: True)
        monkeypatch.setattr(matches, "opens", lambda url, key: False)

        with pytest.raises(RuntimeError, match="does not open"):
            matches.host(*args)

    def test_without_the_video_only_the_public_page_goes_up_with_no_key_nor_old_copy(self, tmp_path, monkeypatch):
        args, built, ran, site = self.hosting(tmp_path, monkeypatch, video=False)
        old = site / "first" / "video"
        old.mkdir(parents=True)

        matches.host(*args)

        assert built == [("voice", Path("outputs/first")), ("none", None, site / "first")] and not old.exists()
        assert [command[0] for command in ran] == ["rsync", "rsync", "rsync"]

    def test_refuses_without_a_choice(self, tmp_path, monkeypatch):
        args, built, ran, _ = self.hosting(tmp_path, monkeypatch)

        with pytest.raises(RuntimeError, match="not chosen"):
            matches.host(*args)

        assert built == [] and ran == []

    @pytest.mark.parametrize("missing", ["light", "av1", "small"])
    def test_never_falls_back_on_the_source_when_a_copy_was_never_made(self, tmp_path, monkeypatch, missing):
        copies = self.copies(tmp_path)
        del copies[missing]
        args, built, _, _ = self.hosting(tmp_path, monkeypatch, video=True, **copies)
        monkeypatch.setattr(matches, "video_key", lambda outputs: "abc")

        with pytest.raises(RuntimeError, match=missing):
            matches.host(*args)

        assert built == []

    def test_refuses_the_video_without_a_password(self, tmp_path, monkeypatch):
        args, built, _, _ = self.hosting(tmp_path, monkeypatch, video=True, **self.copies(tmp_path))
        monkeypatch.setattr(matches, "video_key", lambda outputs: None)

        with pytest.raises(RuntimeError, match="no password"):
            matches.host(*args)

        assert built == []


class TestHostAll:
    @staticmethod
    def matches_of(tmp_path, monkeypatch):
        """Two matches online, the first with its video; the hosting's builds and commands recorded."""
        site, built, ran = tmp_path / "site", [], []
        copies = TestHost.copies(tmp_path)
        hosted = []
        for name, video in (("first", True), ("second", False)):
            match = tmp_path / "matches" / name
            match.mkdir(parents=True)
            (tmp_path / f"{name}.mp4").write_bytes(b"")
            (match / "source.json").write_text(json.dumps({"video": str(tmp_path / f"{name}.mp4"), "court": "court.json"}))
            config = {"site": str(site), "url": "https://example.org/volleyball/", "upload": "host:/site/", "key": "key", "video": video, **(copies if video else {})}
            (match / "publish.json").write_text(json.dumps(config))
            (site / name).mkdir(parents=True)
            (site / name / "data.js").write_text(f"window.MATCH = {json.dumps({'name': name, 'rallies': []})};\n")
            hosted.append((match, tmp_path / f"{name}.mp4", Path("court.json"), config))
        monkeypatch.setattr(matches, "video_key", lambda outputs: "abc")
        monkeypatch.setattr(matches, "head_commit", lambda: "c0ffee")
        monkeypatch.setattr(matches, "ensure_review_page", lambda *args: None)
        monkeypatch.setattr(matches, "make_voice", lambda match: built.append(("voice", match.name)))
        def publish(*args):
            built.append((args[0].name, args[4]["footage"], args[5]))
            (args[5] / "data.js").parent.mkdir(parents=True, exist_ok=True)
            (args[5] / "data.js").write_text(f"window.MATCH = {json.dumps({'name': args[0].name, 'rallies': []})};\n")
            return {}, {}

        monkeypatch.setattr(matches.web, "publish", publish)
        monkeypatch.setattr(matches.web, "computed", lambda *args: ({}, None))
        monkeypatch.setattr(matches.web, "renew_code", lambda page: built.append(("renewed", page)))
        monkeypatch.setattr(matches, "build", lambda site, theme, url, retired=None: [{"name": "first", "path": "first/"}, {"name": "second", "path": "second/"}])
        monkeypatch.setattr(matches.subprocess, "run", lambda command, **kwargs: ran.append(command) or matches.subprocess.CompletedProcess(command, 0, ""))
        monkeypatch.setattr(backup, "free_gb", lambda host, ssh, folder: 100.0)
        monkeypatch.setattr(matches, "counted", lambda command, total, share=None: ran.append(command))
        monkeypatch.setattr(matches, "protected", lambda url: True)
        monkeypatch.setattr(matches, "opens", lambda url, key: True)
        return hosted, built, ran, site

    def test_finds_the_matches_whose_page_is_online(self, tmp_path, monkeypatch):
        hosted, _, _, _ = self.matches_of(tmp_path, monkeypatch)
        # Chose nothing yet: never put online.
        (tmp_path / "matches" / "third").mkdir()
        (tmp_path / "matches" / "third" / "publish.json").write_text(json.dumps({"site": hosted[0][3]["site"]}))

        assert matches.online(tmp_path / "matches") == hosted

    def test_rebuilds_every_match_then_uploads_them_at_once(self, tmp_path, monkeypatch):
        hosted, built, ran, site = self.matches_of(tmp_path, monkeypatch)

        matches.host_all(hosted, "aspom")

        assert built == [("voice", "first"), ("first", "full", site / "first" / "video"), ("first", "none", site / "first"), ("voice", "second"), ("second", "none", site / "second")]
        assert [command[0] for command in ran] == ["rsync", "ssh", "rsync", "rsync"] and "--delay-updates" in ran[3]
        assert "--include=/first/**.mp4" in ran[3] and "--include=/second/**.mp4" in ran[3]

    def test_only_puts_the_page_s_code_in_a_match_built_from_the_same_inputs(self, tmp_path, monkeypatch):
        hosted, built, ran, site = self.matches_of(tmp_path, monkeypatch)
        matches.host_all(hosted, "aspom")
        built.clear(), ran.clear()
        (hosted[1][0] / "identity_answers.json").write_text("{}")

        matches.host_all(hosted, "aspom")

        # The first's data as online, its two pages' code renewed; the second changed, built again.
        assert built == [("voice", "first"), ("renewed", site / "first"), ("renewed", site / "first" / "video"), ("voice", "second"), ("second", "none", site / "second")]
        # The first's video copies are not here (`mirror`): those online stay.
        assert "--include=/first/**.mp4" not in ran[-1] and "--include=/second/**.mp4" in ran[-1]

    def test_builds_again_a_page_said_built_from_other_inputs_or_missing(self, tmp_path, monkeypatch):
        hosted, built, _, site = self.matches_of(tmp_path, monkeypatch)
        matches.host_all(hosted, "aspom")
        built.clear()
        (site / "first" / "video" / "data.js").unlink()
        (site / "second" / matches.MADE).write_text(json.dumps({"from": "other"}))

        matches.host_all(hosted, "aspom")

        assert ("first", "full", site / "first" / "video") in built and ("second", "none", site / "second") in built

    def test_tells_its_stages_and_keeps_their_durations(self, tmp_path, monkeypatch, capsys):
        hosted, _, _, _ = self.matches_of(tmp_path, monkeypatch)

        matches.host_all(hosted, "aspom")

        stages = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::stage ")]
        assert stages == ["::stage mirror", "::stage match 1/2", "::stage match 2/2", "::stage upload"]
        took = json.loads((tmp_path / matches.TIMINGS).read_text())
        assert {"mirror", "match:first", "match:second", "upload"} <= set(took)

    def test_nothing_is_built_nor_sent_when_a_match_cannot_be(self, tmp_path, monkeypatch):
        hosted, built, ran, _ = self.matches_of(tmp_path, monkeypatch)
        hosted[1][1].unlink()

        with pytest.raises(RuntimeError, match="second: video not found"):
            matches.host_all(hosted, "aspom")

        assert built == [] and ran == []

    def test_refuses_matches_hosted_in_different_places(self, tmp_path, monkeypatch):
        hosted, built, _, _ = self.matches_of(tmp_path, monkeypatch)
        hosted[1][3]["upload"] = "elsewhere:/site/"

        with pytest.raises(RuntimeError, match="different places"):
            matches.host_all(hosted, "aspom")

        assert built == []


    def test_gives_the_code_to_every_other_page_online_of_the_same_data_format(self, tmp_path, monkeypatch):
        hosted, built, _, site = self.matches_of(tmp_path, monkeypatch)
        # Put online by the other machine, and one built for another data format.
        for name, data in (("theirs", {"name": "theirs", "rallies": []}), ("older", {"name": "older", "rallies": [], "format": matches.web.FORMAT + 1})):
            (site / name / "video").mkdir(parents=True)
            for page in (site / name, site / name / "video"):
                (page / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        matches.host_all(hosted[1:], "aspom")

        renewed = sorted(entry[1] for entry in built if entry[0] == "renewed")
        assert renewed == [site / "first", site / "theirs", site / "theirs" / "video"]
        assert json.loads((site / matches.CODE).read_text()) == {"code": matches.code_stamps(), "commit": "c0ffee", "format": matches.web.FORMAT}

    def test_puts_the_code_alone_online(self, tmp_path, monkeypatch):
        hosted, built, ran, site = self.matches_of(tmp_path, monkeypatch)

        matches.host_all([], "aspom", told=matches.update_stages(tmp_path, []), config=hosted[0][3])

        assert [entry[0] for entry in built] == ["renewed"] * 2 and ran[-1][0] == "rsync" and "--delay-updates" in ran[-1]

    def test_never_puts_back_the_code_of_an_older_app(self, tmp_path, monkeypatch):
        hosted, built, ran, site = self.matches_of(tmp_path, monkeypatch)
        (site / matches.CODE).write_text(json.dumps({"code": {"page": "newer"}, "commit": "beef"}))
        monkeypatch.setattr(matches, "newer_code", lambda site: True)

        with pytest.raises(RuntimeError, match="newer code online"):
            matches.host_all(hosted, "aspom")

        assert built == [] and all(command[0] != "rsync" or "--dry-run" not in command for command in ran)


class TestSharedCode:
    @staticmethod
    def page(folder, code="a"):
        (folder / "assets").mkdir(parents=True)
        (folder / "assets" / f"index-{code}.js").write_text(f"code {code}")
        (folder / "assets" / f"index-{code}.js.gz").write_bytes(b"gz")
        (folder / "scene3d.js").write_text(f"three {code}")
        (folder / "index.html").write_text(f'<head>\n<script src="./assets/index-{code}.js"></script>\n  </head>')

    def test_every_page_loads_its_code_once_from_the_site_s_folder(self, tmp_path):
        for folder in (tmp_path / "one", tmp_path / "one" / "video", tmp_path / "two"):
            self.page(folder)

        matches.share_code(tmp_path)

        scene = f"scene3d-{hashlib.sha256(b'three a').hexdigest()[:10]}.js"
        assert sorted(p.name for p in (tmp_path / "assets").iterdir()) == ["index-a.js", scene]
        assert not (tmp_path / "one" / "assets").exists() and not (tmp_path / "one" / "scene3d.js").exists()
        page = (tmp_path / "one" / "video" / "index.html").read_text()
        assert 'src="../../assets/index-a.js"' in page and f'<meta name="scene3d" content="../../assets/{scene}" />' in page
        assert 'src="../assets/index-a.js"' in (tmp_path / "two" / "index.html").read_text()

    def test_a_page_built_again_takes_the_new_code_its_old_one_kept_a_week(self, tmp_path):
        from datetime import date, timedelta

        self.page(tmp_path / "one")
        matches.share_code(tmp_path)
        self.page(tmp_path / "two", "b")
        (tmp_path / "one" / "index.html").write_text('<script src="../assets/index-b.js"></script>')
        matches.share_code(tmp_path)
        day = date(2026, 11, 24)

        assert matches.retire_code(tmp_path, day) == []
        assert set(json.loads((tmp_path / "assets" / matches.RETIRED).read_text())) == {"index-a.js", next(p.name for p in (tmp_path / "assets").glob("scene3d-*.js") if "three a" == p.read_text())}
        assert matches.retire_code(tmp_path, day + timedelta(days=matches.RETIRED_DAYS)) != []
        assert not (tmp_path / "assets" / "index-a.js").exists() and (tmp_path / "assets" / "index-b.js").exists()
        assert not (tmp_path / "assets" / matches.RETIRED).exists()

    def test_a_file_named_again_is_no_longer_retired(self, tmp_path):
        from datetime import date

        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "x.js").write_text("")
        matches.retire_code(tmp_path, date(2026, 11, 1))
        (tmp_path / "index.html").write_text('<script src="./assets/x.js"></script>')

        assert matches.retire_code(tmp_path, date(2026, 11, 20)) == [] and not (tmp_path / "assets" / matches.RETIRED).exists()

    def test_an_upload_never_removes_code_another_machine_put_online(self):
        itemized = "*deleting   assets/index-old.js\n*deleting   assets/index-old.js.gz\n*deleting   assets/index-theirs.js\n*deleting   one/assets/index-a.js\n"

        assert matches.removed_code(itemized, ["index-old.js"]) == ["index-theirs.js"]

    def test_tells_code_online_from_an_app_this_one_does_not_come_after(self, tmp_path, monkeypatch):
        from volleyball_stats import git_check

        monkeypatch.setattr(matches, "head_commit", lambda: "here")
        ancestors = {("beef", "here"): 0, ("cafe", "here"): 1}
        monkeypatch.setattr(git_check, "_git", lambda root, *args: subprocess.CompletedProcess(args, ancestors[args[-2:]]))
        assert not matches.newer_code(tmp_path)
        for commit, newer in (("beef", False), ("cafe", True)):
            (tmp_path / matches.CODE).write_text(json.dumps({"code": {"page": "other"}, "commit": commit}))
            assert matches.newer_code(tmp_path) is newer
        (tmp_path / matches.CODE).write_text(json.dumps({"code": matches.code_stamps(), "commit": "cafe"}))
        assert not matches.newer_code(tmp_path)


class TestEnsurePublish:
    @staticmethod
    def imported(tmp_path, name="2026-11-02-avia-1-vs-aspom-2"):
        match = tmp_path / "outputs" / "matches" / name
        match.mkdir(parents=True)
        (match / "teams.json").write_text(json.dumps({"teams": [{"name": "AVIA 1"}, {"name": "ASPOM 2"}]}))
        return match, tmp_path / "data" / name / f"{name}.mp4"

    @staticmethod
    def hosted(tmp_path):
        other = tmp_path / "outputs" / "matches" / "2026-10-29-a-vs-b"
        other.mkdir(parents=True)
        (other / matches.PUBLISH).write_text(json.dumps({"site": "outputs/hosted", "url": "https://example.org/", "upload": "host:/site/", "key": "key", "light": "old.mp4", "club": 1}))

    def test_takes_the_hosting_from_another_match_with_its_own_copies_and_club(self, tmp_path):
        self.hosted(tmp_path)
        match, video = self.imported(tmp_path)

        matches.ensure_publish(match, video, "aspom")

        config = json.loads((match / matches.PUBLISH).read_text())
        assert (config["site"], config["url"], config["upload"], config["key"]) == ("outputs/hosted", "https://example.org/", "host:/site/", "key")
        assert config["club"] == 2
        assert "light" not in config and "video" not in config

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

    def test_the_app_s_club_by_its_teams_first(self, tmp_path, monkeypatch):
        (tmp_path / "teams.json").write_text(json.dumps({"teams": [{"name": "ASPOM 1"}, {"name": "ASPOM 2"}]}))
        monkeypatch.setattr(matches.club_settings, "read", lambda: {"name": "ASPOM Bègles", "teams": ["ASPOM 2"]})

        assert matches.club_team(tmp_path, matches.CLUB) == 2


KEY = matches.fingerprint("new-password")


class TestChoose:
    def test_keeps_the_choice_alone(self, tmp_path):
        (tmp_path / matches.PUBLISH).write_text(json.dumps({"url": "https://example.org/"}))

        assert matches.choose(tmp_path, True) == {"url": "https://example.org/", "video": True}
        assert matches.choose(tmp_path, False) == {"url": "https://example.org/", "video": False}


class TestSetPassword:
    @staticmethod
    def outputs(tmp_path, monkeypatch, online=True):
        """A match online with its video, with the password it had before 19 Nov."""
        site, match = tmp_path / "site", tmp_path / "matches" / "m"
        (site / "m").mkdir(parents=True)
        match.mkdir(parents=True)
        config = {"site": str(site), "url": "https://example.org/v/", "upload": "host:/srv/site/", "key": "k", "video": True, "videoKey": "b" * 64}
        (match / matches.PUBLISH).write_text(json.dumps(config))
        files.write_secret(match / matches.PASSWORD, '{"v": 1}')
        monkeypatch.setattr(matches, "online", lambda folder: [(match, Path("v.mp4"), Path("c.json"), json.loads((match / matches.PUBLISH).read_text()))] if online else [])
        monkeypatch.setattr(matches, "hosted_folder", lambda m, s: site / "m")
        return tmp_path

    def test_goes_online_then_is_kept_for_its_user_alone_then_checked(self, tmp_path, monkeypatch):
        outputs = self.outputs(tmp_path, monkeypatch)
        done = []
        monkeypatch.setattr(matches, "install_key", lambda config, key: done.append(("install", config["upload"], key)))
        monkeypatch.setattr(matches, "opens", lambda url, key: done.append(("opens", url, key)) or True)

        matches.set_password(outputs, "new-password")

        assert done == [("install", "host:/srv/site/", KEY), ("opens", "https://example.org/v/m/video/", KEY)]
        assert matches.password(outputs) == "new-password" and matches.video_key(outputs) == KEY
        if os.name == "posix":
            assert (outputs / matches.PASSWORD).stat().st_mode & 0o777 == 0o600
        # The match's own, from before 19 Nov, gone.
        assert not (outputs / "matches" / "m" / matches.PASSWORD).exists()
        assert "videoKey" not in json.loads((outputs / "matches" / "m" / matches.PUBLISH).read_text())

    def test_a_copy_s_wider_rights_are_narrowed_on_reading(self, tmp_path, monkeypatch):
        outputs = self.outputs(tmp_path, monkeypatch, online=False)
        matches.set_password(outputs, "new-password")
        (outputs / matches.PASSWORD).chmod(0o644)

        assert matches.password(outputs) == "new-password"
        if os.name == "posix":
            assert (outputs / matches.PASSWORD).stat().st_mode & 0o777 == 0o600

    def test_nothing_changes_when_the_server_refuses_it_nor_says_the_fingerprint(self, tmp_path, monkeypatch):
        outputs = self.outputs(tmp_path, monkeypatch)

        def refuse(config, key):
            raise subprocess.CalledProcessError(1, ["ssh", key], stderr=b"Permission denied")

        monkeypatch.setattr(matches, "install_key", refuse)

        with pytest.raises(RuntimeError, match="^Permission denied$"):
            matches.set_password(outputs, "new-password")

        assert matches.password(outputs) is None
        assert json.loads((outputs / "matches" / "m" / matches.PUBLISH).read_text())["videoKey"] == "b" * 64

    def test_without_a_match_online_kept_for_the_first_upload(self, tmp_path, monkeypatch):
        outputs = self.outputs(tmp_path, monkeypatch, online=False)
        monkeypatch.setattr(matches, "install_key", lambda *a: pytest.fail("not online"))

        matches.set_password(outputs, "new-password")

        assert matches.password(outputs) == "new-password"

    def test_says_so_when_a_page_does_not_open_with_it(self, tmp_path, monkeypatch):
        outputs = self.outputs(tmp_path, monkeypatch)
        monkeypatch.setattr(matches, "install_key", lambda config, key: None)
        monkeypatch.setattr(matches, "opens", lambda url, key: False)

        with pytest.raises(RuntimeError, match="does not open"):
            matches.set_password(outputs, "new-password")

    @pytest.mark.parametrize("wrong", [None, "", "short", "        x", "x" * 201, 12345678])
    def test_refuses_one_too_short_or_too_long(self, tmp_path, monkeypatch, wrong):
        outputs = self.outputs(tmp_path, monkeypatch)
        monkeypatch.setattr(matches, "install_key", lambda *a: pytest.fail("refused first"))

        with pytest.raises(ValueError):
            matches.set_password(outputs, wrong)

        assert matches.password(outputs) is None


class TestAddCopies:
    PLAN = {"map": [[0, 10, 0, 10]], "camera": [[1.0, 5000, 5000, 15000]]}

    def test_lists_them_once_made_as_the_review_has_them(self, tmp_path, monkeypatch):
        (tmp_path / matches.PUBLISH).write_text("{}")
        monkeypatch.setattr(matches, "review_cut", lambda match: self.PLAN)
        made = {key: tmp_path / f"{key}.mp4" for key in ("light", "av1", "small")}
        for path in made.values():
            path.write_bytes(b"")
        cut = []
        monkeypatch.setattr(matches.video_copies, "make", lambda video, plan, share: cut.append(plan) or made)

        config = matches.add_copies(tmp_path, Path("m.mp4"))

        assert config == {key: str(path.resolve()) for key, path in made.items()}
        assert cut == [self.PLAN] and matches.video_copies.recorded(tmp_path, made["light"]) == self.PLAN

    def test_removes_a_former_copy_of_the_copies_folder_only(self, tmp_path, monkeypatch):
        folder = tmp_path / matches.video_copies.FOLDER
        folder.mkdir()
        former, elsewhere, kept = folder / "m_1080p.mp4", tmp_path / "mine_av1.mp4", folder / "m_720p.mp4"
        for path in (former, elsewhere, kept):
            path.write_bytes(b"")
        (tmp_path / matches.PUBLISH).write_text(json.dumps({"light": str(former), "av1": str(elsewhere), "small": str(kept)}))
        monkeypatch.setattr(matches, "review_cut", lambda match: self.PLAN)
        made = {"light": folder / "m_1440p.mp4", "av1": folder / "m_av1.mp4", "small": kept}
        monkeypatch.setattr(matches.video_copies, "make", lambda video, plan, share: made["light"].write_bytes(b"") or made)
        former.unlink()

        matches.add_copies(tmp_path, Path("m.mp4"))

        assert elsewhere.exists() and kept.exists()

    def test_copies_made_otherwise_are_made_again_only_when_asked(self, tmp_path, monkeypatch):
        copies = {key: tmp_path / f"{key}.mp4" for key in matches.video_copies.COPIES}
        for path in copies.values():
            path.write_bytes(b"")
        (tmp_path / matches.PUBLISH).write_text(json.dumps({"video": True, **{key: str(path) for key, path in copies.items()}}))
        plan = dict(self.PLAN)
        monkeypatch.setattr(matches, "review_cut", lambda match: plan)
        matches.video_copies.record(tmp_path, copies["light"], self.PLAN)
        config = json.loads((tmp_path / matches.PUBLISH).read_text())
        made = []
        monkeypatch.setattr(matches.video_copies, "make", lambda video, p, share: made.append(p) or copies)

        (tmp_path / "review").mkdir()
        (tmp_path / "review" / "data.js").write_text("a")
        assert not matches.copies_stale(tmp_path, config)
        plan["map"] = [[0, 5, 0, 5]]
        assert not matches.copies_stale(tmp_path, config)  # the review's files unchanged: its former cut
        (tmp_path / "review" / "data.js").write_text("ab")
        assert matches.copies_stale(tmp_path, config)
        matches.add_copies(tmp_path, Path("m.mp4"))
        assert made == []
        matches.add_copies(tmp_path, Path("m.mp4"), remake=True)
        assert made == [plan] and not matches.copies_stale(tmp_path, config)

    def test_the_reviews_plan_from_its_page_an_older_one_too(self, tmp_path):
        (tmp_path / "review").mkdir()
        (tmp_path / "review" / "ball.js").write_text('window.MATCH_BALL = {"samples": []};\n')
        rallies = [{"start": 10, "end": 20, "set": 1}, {"start": 30, "end": 40, "set": 1}]
        (tmp_path / "review" / "data.js").write_text("window.MATCH = " + json.dumps({"views": [[0, 0, 0, 1], [9, 0.2, 0.1, 0.5]], "duration": 60, "rallies": rallies, "contacts": []}) + ";\n")

        plan = matches.review_cut(tmp_path)

        assert plan["map"][0][:2] == [8, 21] and plan["map"][-1][1] == 42 and plan["camera"]

    def test_copies_made_before_the_zoom_was_cut_in_them_are_stale(self, tmp_path, monkeypatch):
        copies = {key: tmp_path / f"{key}.mp4" for key in matches.video_copies.COPIES}
        for path in copies.values():
            path.write_bytes(b"")
        monkeypatch.setattr(matches, "review_cut", lambda match: self.PLAN)
        config = {"video": True, **{key: str(path) for key, path in copies.items()}}

        assert matches.copies_stale(tmp_path, config)
        assert not matches.copies_stale(tmp_path, {**config, "video": False})

    def test_a_copy_at_a_former_height_is_missing(self, tmp_path, monkeypatch):
        copies = {key: tmp_path / f"{key}.mp4" for key in matches.video_copies.COPIES}
        for key, path in copies.items():
            path.write_text(str(matches.video_copies.COPIES[key][1]))
        monkeypatch.setattr(matches.video_copies, "current", CURRENT)
        monkeypatch.setattr(matches.video_copies, "height", lambda path: int(path.read_text()))
        config = {key: str(path) for key, path in copies.items()}

        assert not matches.copies_missing(config)
        copies["av1"].write_text("1080")
        assert matches.copies_missing(config)


def test_sends_the_reports_beside_the_list():
    assert matches.feedback_address("https://example.org/volleyball/") == "/volleyball/feedback"
    assert matches.feedback_address("https://stats.example.org/") == "/feedback"
    assert matches.feedback_address(None) is None


class TestKeyCommand:
    @staticmethod
    def run(tmp_path, service, key):
        bin_ = tmp_path / "bin"
        bin_.mkdir(exist_ok=True)
        for name in ("docker", "nginx"):
            fake = bin_ / name
            fake.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/{name}.log\n')
            fake.chmod(0o755)
        subprocess.run(["sh", "-c", matches.key_command(service, key)], check=True, env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"})
        return service / "video_key.conf"

    def test_one_key_for_every_folder_in_place_the_former_ones_gone_then_reloads(self, tmp_path):
        service = tmp_path / "docker" / "volleyball-stats"
        service.mkdir(parents=True)
        (service.parent / "docker-compose.yml").write_text("services:\n  volleyballstats:\n    image: nginx\n")
        keys = service / "video_key.conf"
        keys.write_text('"old-match:111" 1;\n"m:222" 1;\n')
        inode = keys.stat().st_ino

        self.run(tmp_path, service, "333")

        assert keys.read_text() == '"~^[^:/]+:333$" 1;\n'
        assert keys.stat().st_ino == inode
        assert sorted(p.name for p in service.iterdir()) == ["video_key.conf"]
        assert "nginx -t -q && nginx -s reload" in (tmp_path / "docker.log").read_text()

    def test_reloads_the_servers_own_nginx_without_the_owners_compose(self, tmp_path):
        service = tmp_path / "srv" / "site-parent"
        service.mkdir(parents=True)
        (service / "video_key.conf").write_text("")

        self.run(tmp_path, service, "333")

        assert (tmp_path / "nginx.log").read_text() == "-t -q\n-s reload\n" and not (tmp_path / "docker.log").exists()


def test_a_match_from_the_other_machine_gets_its_review_page_before_the_voice(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(matches.web, "review_page", lambda match, video, court, theme, pictures: built.append((match, pictures)))
    matches.ensure_review_page(tmp_path, Path("v.mp4"), Path("c.json"), "aspom")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "data.js").write_text("window.MATCH = {};\n")
    matches.ensure_review_page(tmp_path, Path("v.mp4"), Path("c.json"), "aspom")

    assert built == [(tmp_path, False)]


class TestRemovedFilms:
    ITEMIZED = "\n".join([
        "*deleting   a/video/films/1-manon.mp4",
        "*deleting   a/video/films/manifest.json",
        "*deleting   b/video/films/2-sylvain.mp4",
        "*deleting   c/video/old.mp4",
        "<f+++++++++ a/data.js",
    ])  # fmt: skip

    def test_names_the_matches_with_no_films_here_whose_films_an_upload_deletes(self):
        assert matches.removed_films(self.ITEMIZED, ["a", "c"]) == ["a"]

    def test_a_match_whose_films_are_here_may_lose_one(self):
        assert matches.removed_films(self.ITEMIZED, []) == []


class TestAdoptFilms:
    def page(self, tmp_path):
        page = tmp_path / "site" / "m" / "video"
        (page / "films").mkdir(parents=True)
        films = {"*": "films/resume.mp4?v=aaa", "Loïck": "films/2-loick.mp4?v=bbb", "Gone": "films/1-gone.mp4?v=ccc"}
        (page / "data.js").write_text("window.MATCH = " + json.dumps({"name": "m", "films": films}) + ";\n")
        (page / "films" / "resume.mp4").write_bytes(b"r")
        (page / "films" / "2-loick.mp4").write_bytes(b"l")
        return page

    def test_takes_the_films_online_with_their_names_when_this_machine_has_none(self, tmp_path):
        match = tmp_path / "match"
        match.mkdir()
        assert matches.adopt_films(match, self.page(tmp_path)) == 2
        made = json.loads((match / "films" / "manifest.json").read_text())
        assert {n: (e["file"], e["hash"]) for n, e in made.items()} == {"*": ("resume.mp4", "aaa"), "Loïck": ("2-loick.mp4", "bbb")}
        assert (match / "films" / "2-loick.mp4").read_bytes() == b"l"

    def test_leaves_this_machines_own_films(self, tmp_path):
        match = tmp_path / "match"
        (match / "films").mkdir(parents=True)
        assert matches.adopt_films(match, self.page(tmp_path)) == 0
        assert not (match / "films" / "manifest.json").exists()


class TestExport:
    def test_zips_the_public_pages_and_their_list_without_the_servers_parts(self, tmp_path, monkeypatch):
        built = []
        match = tmp_path / "outputs" / "matches" / "first"
        match.mkdir(parents=True)
        (match / "publish.json").write_text(json.dumps({"club": 2, "video": True}))
        (tmp_path / "first.mp4").write_bytes(b"")
        monkeypatch.setattr(matches, "ensure_review_page", lambda *args: None)
        monkeypatch.setattr(matches, "make_voice", lambda match: built.append("voice"))

        def publish(match, video, court, theme, given, site, share=None):
            built.append(given)
            site.mkdir(parents=True)
            (site / "data.js").write_text(f"window.MATCH = {json.dumps({'name': 'first', 'date': '2026-10-29', 'teams': None, 'rallies': []})};\n")
            return {}, {}

        monkeypatch.setattr(matches.web, "publish", publish)
        out = tmp_path / "outputs" / matches.EXPORT

        matches.export([(match, tmp_path / "first.mp4", Path("court.json"))], "none", out, folder="matches")

        # No video nor pictures, no report endpoint nor link to a password's page: what needs the server.
        assert built == ["voice", {"footage": "none", "club": 2, "pictures": False}]
        names = matches.zipfile.ZipFile(out).namelist()
        assert "matches/index.html" in names and "matches/2026-10-29/data.js" in names
        assert not [n for n in names if n.endswith(".gz")]
        assert [p.name for p in out.parent.iterdir()] == ["site.zip"]

    def test_leaves_the_last_zip_when_a_match_fails(self, tmp_path, monkeypatch):
        match = tmp_path / "outputs" / "matches" / "first"
        match.mkdir(parents=True)
        out = tmp_path / "outputs" / matches.EXPORT
        out.parent.mkdir(parents=True)
        out.write_bytes(b"before")

        with pytest.raises(RuntimeError, match="video not found"):
            matches.export([(match, tmp_path / "gone.mp4", Path("court.json"))], "none", out)

        assert out.read_bytes() == b"before" and [p.name for p in out.parent.iterdir()] == ["site.zip"]


class TestCounted:
    def test_counts_the_files_a_dry_run_says_it_moves(self):
        assert matches.files_to_send("<f+++++++++ a.js\n.d..t...... ./\n*deleting   old\n>f.st...... b.js\n") == 2

    def test_tells_the_files_moved_of_those_to_move_and_ends_at_one(self, monkeypatch, tmp_path):
        script = tmp_path / "fake"
        script.write_text("#!/bin/sh\nprintf '<f+++ a\\n.d.. ./\\n<f+++ b\\n<f+++ c\\n'\n")
        script.chmod(0o755)
        told = []
        matches.counted([str(script)], 3, told.append)
        assert told[:3] == pytest.approx([1 / 3, 2 / 3, 1.0]) and told[-1] == 1.0

    def test_keeps_the_errors_when_it_fails(self, tmp_path):
        script = tmp_path / "fake"
        script.write_text("#!/bin/sh\necho 'no route' >&2\nexit 12\n")
        script.chmod(0o755)
        with pytest.raises(subprocess.CalledProcessError) as error:
            matches.counted([str(script)], 1)
        assert error.value.returncode == 12 and "no route" in error.value.stderr


class TestSsh:
    def test_a_new_server_is_reached_without_a_question(self):
        """After a move, the first upload takes the new server's host key instead of failing (BatchMode never asks)."""
        options = matches.ssh_options("~/key")
        assert "StrictHostKeyChecking=accept-new" in options and "BatchMode=yes" in options and "~" not in options[1]

    def test_rsync_keeps_a_key_path_with_spaces_whole(self, tmp_path):
        command = matches.upload_command({"key": "/Users/A B/key", "upload": "root@h:/site/"}, tmp_path, [])
        assert "'/Users/A B/key'" in command[command.index("-e") + 1]


class TestMadeFrom:
    def test_follows_the_match_s_inputs_not_what_hosting_or_the_review_s_code_writes(self, tmp_path):
        match, court = tmp_path / "m", tmp_path / "court.json"
        (match / "review" / "assets").mkdir(parents=True)
        (match / "rallies.csv").write_text("start_frame\n1\n")
        (match / "review" / "data.js").write_text('window.MATCH = {"name": "m", "v": "1"};\n')
        court.write_text("{}")
        made = lambda **config: matches.made_from(match, tmp_path / "m.mp4", court, "aspom", {"video": False, **config})  # noqa: E731
        first = made()

        (match / "hosted.json").write_text("{}")
        (match / "review" / "assets" / "index-abc.js").write_text("code")
        (match / "review" / "data.js").write_text('window.MATCH = {"name": "m", "v": "2"};\n')
        assert made() == first
        assert made(club=2) != first
        # A new password reaches the server alone: the pages stay as built.
        (match / matches.PUBLISH).write_text('{"videoKey": "b"}')
        (match / matches.PASSWORD).write_text("{}")
        assert made(videoKey="b") == first
        (match / "rallies.csv").write_text("start_frame\n2\n")
        assert made() != first


class TestUpdateAll:
    def test_puts_a_new_match_online_its_video_copies_made_first(self, tmp_path, monkeypatch):
        folder = tmp_path / "outputs" / "matches"
        old, new = folder / "old", folder / "new"
        for match in (old, new):
            match.mkdir(parents=True)
            (match / files.SOURCE).write_text(json.dumps({"video": str(tmp_path / "v.mp4"), "court": "c.json"}))
        (tmp_path / "v.mp4").write_bytes(b"v")
        (new / matches.PUBLISH).write_text(json.dumps({"site": str(tmp_path / "site"), "video": True}))
        online = [(old, tmp_path / "v.mp4", Path("c.json"), {"video": False})]
        done = []
        monkeypatch.setattr(matches, "online", lambda f: online)
        monkeypatch.setattr(matches, "hosted_folder", lambda m, s: None)
        monkeypatch.setattr(sync, "behind", lambda found: {})
        monkeypatch.setattr(matches, "ensure_review_page", lambda *args: None)
        monkeypatch.setattr(matches, "add_copies", lambda m, v, share: done.append(("copies", m.name)) or {"video": True, "light": "l"})
        monkeypatch.setattr(matches, "host_all", lambda found, theme, mirrored, told, config=None: done.append(("host", [(m.name, c) for m, *_, c in found], told.plan)))
        monkeypatch.setattr(sys, "argv", ["matches", "--all", str(folder), "--only", "new", "--only", "old"])

        matches.main()

        assert done == [("copies", "new"), ("host", [("old", {"video": False}), ("new", {"video": True, "light": "l"})], ["copies:new", "mirror", "match:old", "match:new", "upload"])]

    def test_a_first_upload_with_the_video_makes_its_films_missing_first(self, tmp_path, monkeypatch):
        from volleyball_stats import film

        folder = tmp_path / "outputs" / "matches"
        new, bare = folder / "new", folder / "bare"
        for match, video in ((new, True), (bare, False)):
            match.mkdir(parents=True)
            (match / files.SOURCE).write_text(json.dumps({"video": str(tmp_path / "v.mp4"), "court": "c.json"}))
            (match / matches.PUBLISH).write_text(json.dumps({"site": str(tmp_path / "site"), "video": video, "light": "l", "av1": "a", "small": "s"}))
        (tmp_path / "v.mp4").write_bytes(b"v")
        done = []
        monkeypatch.setattr(matches, "online", lambda f: [])
        monkeypatch.setattr(matches, "hosted_folder", lambda m, s: None)
        monkeypatch.setattr(matches, "copies_missing", lambda c: False)
        monkeypatch.setattr(sync, "behind", lambda found: {})
        monkeypatch.setattr(matches, "ensure_review_page", lambda *args: None)
        monkeypatch.setattr(film, "status", lambda m: {"players": {"total": 2, "stale": ["A"]}, "highlights": {"total": 1, "stale": []}})
        monkeypatch.setattr(film, "build", lambda m, v, c, share: done.append(("films", m.name)))
        monkeypatch.setattr(matches, "host_all", lambda found, theme, mirrored, told, config=None: done.append(("host", told.plan)))
        monkeypatch.setattr(sys, "argv", ["matches", "--all", str(folder), "--only", "new", "--only", "bare"])

        matches.main()

        assert done == [("films", "new"), ("host", ["films:new", "mirror", "match:new", "match:bare", "upload"])]
