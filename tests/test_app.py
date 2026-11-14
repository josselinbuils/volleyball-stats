import json
from pathlib import Path

import pytest

from volleyball_stats import app, files, jobs, presence


class TestApp:
    @pytest.fixture
    def place(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "OUTPUTS", tmp_path / "outputs")
        monkeypatch.setattr(app, "MATCHES", tmp_path / "outputs" / "matches")
        monkeypatch.setattr(app, "DATA", tmp_path / "data" / "matches")
        return tmp_path

    @staticmethod
    def match(place, name, *names):
        folder = place / "outputs" / "matches" / name
        folder.mkdir(parents=True)
        (folder / "teams.json").write_text(json.dumps({"teams": [{"name": "A", "colour": None}, {"name": "B", "colour": None}], "date": "2026-11-01"}))
        for file in names:
            (folder / file).write_text("{}")
        return folder

    @staticmethod
    def job(place, name, **fields):
        folder = jobs.folder(place / "outputs")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(json.dumps({"id": name, "kind": "import", "steps": [], "started": 1.0, "ended": 2.0, **fields}))

    def test_tells_what_each_match_waits_for(self, place, monkeypatch):
        # No pipeline of this machine's: one running for real would name these one-letter matches.
        monkeypatch.setattr(app, "commands_running", lambda: "")
        self.match(place, "a")
        self.match(place, "b", app.COURT)
        self.match(place, "c", files.SOURCE)
        self.match(place, "d", "report.md")
        self.match(place, "e")
        self.job(place, "e", failed="court", error="No stored court matches")
        self.match(place, "f", app.COURT)
        self.job(place, "f", kind="pipeline", failed="pipeline", error="boom")
        self.match(place, "g")
        self.job(place, "g", kind="court", failed="court", error="no fit", manual=True)
        found = {m["name"]: m for m in app.preparing([{"path": "d", "ready": True}])}
        assert {k: m["state"] for k, m in found.items()} == {"a": "court", "b": "check", "c": "stalled", "e": "court", "f": "failed", "g": "court"}
        assert found["g"]["fitFailed"] and not found["e"]["fitFailed"]

    def test_swaps_the_sides(self, place):
        folder = self.match(place, "a")
        app.swap("a")
        assert [t["name"] for t in json.loads((folder / "teams.json").read_text())["teams"]] == ["B", "A"]

    def test_deletes_only_a_match_not_reviewed(self, place):
        self.match(place, "a")
        (place / "data" / "matches" / "a").mkdir(parents=True)
        app.delete("a")
        assert not (place / "outputs" / "matches" / "a").exists() and not (place / "data" / "matches" / "a").exists()
        self.match(place, "b", "identity_answers.json")
        with pytest.raises(PermissionError):
            app.delete("b")

    def test_carries_the_teams_to_the_import(self):
        assert app.team_flag([{"name": " A ", "colour": "#ff0000"}, {"name": "B"}]) == "A:#ff0000,B"
        for teams in ([{"name": "A,B"}, {"name": "C"}], [{"name": "A"}], [{"name": "A", "colour": "nope"}, {"name": "B"}]):
            with pytest.raises(ValueError):
                app.team_flag(teams)

    def test_refuses_paths_out_of_the_matches(self, place):
        assert app.handle("POST", "/app/swap", "", {"match": "../x"}, list)[2] == 400
        assert app.handle("POST", "/app/forget", "", {"id": "../roster"}, list)[2] == 400
        assert app.handle("GET", "/app/image", "match=..&kind=start", {}, list)[2] == 404
        assert app.handle("GET", "/other", "", {}, list) is None

    def test_lists_the_teams_played_most_matches_first(self, place):
        self.match(place, "one")
        (self.match(place, "two") / "teams.json").write_text(json.dumps({"teams": [{"name": "C"}, {"name": "B"}]}))
        assert app.played_teams() == ["B", "A", "C"]

    def test_saves_the_server_for_every_match(self, place):
        self.match(place, "one", "source.json")
        (place / "outputs" / "matches" / "one" / "publish.json").write_text(json.dumps({"club": 2, "video": True}))
        body = {"address": "root@1.2.3.4", "folder": "/srv/site", "key": "~/.ssh/k", "url": "https://x.org/v"}
        answer = app.handle("POST", "/app/server", "", body, list)
        assert answer[2] == 200 and json.loads(answer[0])["server"] == {**body, "folder": "/srv/site/", "url": "https://x.org/v/"}
        assert json.loads((place / "outputs" / "matches" / "one" / "publish.json").read_text()) == {
            "club": 2, "video": True, "upload": "root@1.2.3.4:/srv/site/", "key": "~/.ssh/k", "url": "https://x.org/v/", "site": "outputs/hosted"
        }
        assert app.handle("POST", "/app/server", "", {**body, "address": "nobody"}, list)[2] == 400

    def test_exports_only_the_matches_ready(self, place, monkeypatch):
        started = []
        monkeypatch.setattr(app.jobs, "start", lambda outputs, job_id, kind, steps: started.append(steps[0][1]))
        listed = lambda: [{"path": "one", "name": "one", "ready": True}, {"path": "two", "ready": False}, {"path": "three", "ready": True, "missing": "video"}]  # noqa: E731
        answer = json.loads(app.handle("GET", "/app/export", "", {}, listed)[0])
        assert [m["path"] for m in answer["matches"]] == ["one"] and answer["file"] is None
        assert app.handle("POST", "/app/export", "", {"matches": ["two"]}, listed)[2] == 400
        assert app.handle("POST", "/app/export", "", {"matches": []}, listed)[2] == 400
        assert app.handle("GET", "/app/export/file", "", {}, listed)[2] == 404
        assert app.handle("POST", "/app/export", "", {"matches": ["one"], "folder": "../x"}, listed)[2] == 400
        assert app.handle("POST", "/app/export", "", {"matches": ["one"], "folder": "matches"}, listed)[2] == 200
        assert started == [["volleyball_stats.matches", "--export", str(place / "outputs" / "export" / "site.zip"), "--folder", "matches", "--match", str(place / "outputs" / "matches" / "one")]]
        # Once done: the zip, and the matches it holds.
        self.job(place, "export", kind="export", steps=[{"name": "export", "args": started[0]}])
        (place / "outputs" / "export" / "site.zip").parent.mkdir(parents=True)
        (place / "outputs" / "export" / "site.zip").write_bytes(b"zip")
        answer = json.loads(app.handle("GET", "/app/export", "", {}, listed)[0])
        assert answer["file"]["size"] == 3 and answer["file"]["matches"] == ["one"] and answer["file"]["folder"] == "matches"
        assert app.handle("GET", "/app/export/file", "", {}, listed)[:2] == (place / "outputs" / "export" / "site.zip", "application/zip")

    def test_the_update_starts_unless_answers_are_being_applied(self, monkeypatch):
        started = []
        monkeypatch.setattr(app.jobs, "start", lambda outputs, job_id, kind, steps: started.append(steps[0][1]))
        monkeypatch.setattr(app, "learn_state", lambda listed: {})

        assert app.handle("POST", "/app/learn", "", {}, list, lambda: True)[2] == 409
        assert not started
        assert app.handle("POST", "/app/learn", "", {}, list, lambda: False)[2] == 200
        assert started == [["volleyball_stats.learn", "--update", str(app.MATCHES)]]

    def test_refuses_to_quit_while_applying(self):
        assert app.handle("POST", "/app/quit", "", {}, list, lambda: True)[2] == 409
        assert app.handle("POST", "/app/quit", "", {}, list, lambda: False)[2] == 200

    def test_opens_the_page_in_a_window_of_its_own(self, monkeypatch):
        monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)
        assert app.app_window("http://127.0.0.1:8765/", "linux") == ["chromium", "--app=http://127.0.0.1:8765/"]
        monkeypatch.setattr(app.shutil, "which", lambda name: None)
        assert app.app_window("http://127.0.0.1:8765/", "linux") is None

    def test_under_wsl_opens_the_page_once_windows_reaches_the_server(self, monkeypatch):
        tries, shown = iter([False, False, True]), []
        monkeypatch.setattr(app, "reached_from_windows", lambda url: next(tries))
        monkeypatch.setattr(app, "show", lambda url: shown.append(url))
        monkeypatch.setattr(app.time, "sleep", lambda s: None)
        app.open_once_reached("http://127.0.0.1:8765/")
        assert shown == ["http://127.0.0.1:8765/"] and next(tries, None) is None

    def test_reads_the_word_after_stats(self):
        assert app.parse([]) == (None, [])
        assert app.parse(["browser", "m", "--port", "9000"]) == ("browser", ["m", "--port", "9000"])
        assert app.parse(["server", "m"]) == ("server", ["m"])
        assert app.parse(["stop"]) == ("stop", [])
        assert app.parse(["m", "--no-browser"]) == ("server", ["m"])
        assert app.parse(["--stop"]) == ("stop", [])
        assert {command: app.OPENING[command] for command in (None, "browser", "server")} == {None: "window", "browser": "tab", "server": None}

    def test_refuses_to_start_at_a_lowered_priority(self, monkeypatch):
        monkeypatch.setattr(app.os, "nice", lambda increment: 5)
        monkeypatch.setattr(app.os, "chdir", lambda path: None)
        monkeypatch.setattr(app.shortcut, "update_launcher", lambda: None)
        monkeypatch.setattr(app, "already_open", lambda port: False)
        monkeypatch.setattr(app.sys, "argv", ["stats", "server"])
        with pytest.raises(SystemExit, match="lowered priority"):
            app.main()

    def test_hears_from_the_pages(self, monkeypatch):
        pages = presence.Presence()
        monkeypatch.setattr(presence, "PAGES", pages)
        app.handle("POST", "/app/alive", "", {"id": "a"}, list)
        assert "a" in pages.pages
        app.handle("POST", "/app/leaving", "", {"id": "a"}, list)
        assert not pages.pages and pages.left_at is not None

    def test_stops_nothing_when_not_running(self, monkeypatch):
        monkeypatch.setattr(app, "already_open", lambda port: False)
        assert app.stop(1) == 0

    def test_answers_an_unreadable_video(self, tmp_path):
        (tmp_path / "DJI_cut.mp4").write_bytes(b"not a video")
        answer = app.handle("POST", "/app/scan", "", {"source": str(tmp_path)}, list)
        assert answer[2] == 400 and json.loads(answer[0])["error"] == "unreadable:DJI_cut.mp4"

    def test_previews_a_recording_and_refuses_one_not_there(self, tmp_path):
        from test_import_match import TestImport

        card = TestImport.card(tmp_path)
        picture = app.handle("GET", "/app/preview", f"source={card}&recording=1&at=3", {}, list)
        assert picture[1:] == ("image/jpeg", 200) and picture[0][:2] == b"\xff\xd8"
        assert app.handle("GET", "/app/preview", f"source={card}&recording=2&at=3", {}, list)[2] == 400

    def test_estimates_the_time_left(self):
        tracking = {"started": 0.0, "stepStarted": 0.0, "step": "pipeline", "stage": "tracking", "progress": 0.5, "duration": app.TOOK_VIDEO_S}
        left = app.time_left(tracking, 100.0)
        assert left > 100.0
        assert app.time_left({**tracking, "duration": app.TOOK_VIDEO_S / 10}, 100.0) < left
        assert app.time_left({"started": 0.0, "step": "import", "progress": 0.25}, 100.0) == pytest.approx(300.0)

    def test_tells_the_match_an_update_rebuilds(self):
        job = {"started": 0.0, "stepStarted": 0.0, "step": "hosting", "stage": "match 2/5", "progress": 0.5}
        assert app.told(job, 60.0) == {"stage": "match", "n": 2, "of": 5, "elapsed": 60.0, "left": pytest.approx(60.0)}
        assert app.told({**job, "stage": "upload"}, 60.0)["n"] is None


class TestPickVideo:
    def run_as(self, monkeypatch, kind, stdout=b"", returncode=0):
        ran = []

        def run(command, **_):
            ran.append(command)
            return app.subprocess.CompletedProcess(command, returncode, stdout, b"")

        monkeypatch.setattr(app.doctor, "system", lambda: kind)
        monkeypatch.setattr(app.subprocess, "run", run)
        return ran

    def test_gives_the_videos_picked_in_the_finder(self, monkeypatch):
        ran = self.run_as(monkeypatch, "mac", "/Users/léa/Movies/a.mp4\n/Users/léa/Movies/b.mp4\n".encode())
        assert app.picker() == "mac" and app.pick("files") == ["/Users/léa/Movies/a.mp4", "/Users/léa/Movies/b.mp4"]
        assert ran[0][0] == "osascript" and "multiple selections allowed" in " ".join(ran[0])
        self.run_as(monkeypatch, "mac", b"/Volumes/OSMO/DCIM/\n")
        assert app.pick("folder") == ["/Volumes/OSMO/DCIM"]

    def test_a_window_closed_without_a_video_gives_none(self, monkeypatch):
        self.run_as(monkeypatch, "mac", b"", 1)
        assert app.pick() is None
        self.run_as(monkeypatch, "wsl", b"\r\n")
        assert app.pick() is None
        with pytest.raises(ValueError):
            app.pick("anything")

    def test_under_wsl_gives_windows_paths_as_wsl_sees_them_their_drive_mounted(self, monkeypatch):
        mounted = []
        ran = self.run_as(monkeypatch, "wsl", "E:\\DCIM\\DJI_001\\match é.MP4\r\nE:\\DCIM\\DJI_001\\b.MP4\r\n".encode())
        monkeypatch.setattr(app, "mount", lambda drive: mounted.append(drive))
        monkeypatch.setattr(app.os.path, "ismount", lambda path: False)
        assert app.pick("files") == ["/mnt/e/DCIM/DJI_001/match é.MP4", "/mnt/e/DCIM/DJI_001/b.MP4"]
        assert mounted == ["E", "E"] and ran[0][0] == "powershell.exe" and "Multiselect" in ran[0][-1]
        # The window opens on top of the page's.
        assert "TopMost = $true" in ran[0][-1] and "ShowDialog($top)" in ran[0][-1]
        ran = self.run_as(monkeypatch, "wsl", b"C:\\Users\\a\\Videos\r\n")
        assert app.pick("folder") == ["/mnt/c/Users/a/Videos"] and "FolderBrowserDialog" in ran[0][-1]

    def test_a_linux_desktop_uses_its_own_tool_and_none_means_no_window(self, monkeypatch):
        self.run_as(monkeypatch, "linux", b"/home/a/m.mp4\n/home/a/n.mp4\n")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/kdialog" if name == "kdialog" else None)
        assert app.picker() == "kdialog" and app.pick() == ["/home/a/m.mp4", "/home/a/n.mp4"]
        monkeypatch.setattr(app.shutil, "which", lambda name: None)
        assert app.picker() is None
        with pytest.raises(LookupError, match="picker"):
            app.pick()
        monkeypatch.setattr(app.shutil, "which", lambda name: "/usr/bin/zenity")
        monkeypatch.delenv("DISPLAY")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert app.picker() is None

    def test_names_windows_drives_as_windows_does(self, monkeypatch):
        self.run_as(monkeypatch, "wsl", "C:|Windows\r\nD:|\r\nE:|OSMO ACTION\r\n".encode())
        monkeypatch.setattr(app, "windows_home", lambda: None)
        monkeypatch.setattr(app.os.path, "ismount", lambda path: False)
        monkeypatch.setattr(app.Path, "home", lambda: Path("/nowhere"))
        assert [(s["name"], s.get("drive")) for s in app.sources()] == [("D:", "D"), ("OSMO ACTION (E:)", "E")]


class TestSources:
    def test_several_videos_picked_together_are_one_source(self, tmp_path):
        assert app.paths_of(str(tmp_path)) == tmp_path
        assert app.paths_of([str(tmp_path / "a.mp4")]) == tmp_path / "a.mp4"
        assert app.paths_of([str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")]) == [tmp_path / "a.mp4", tmp_path / "b.mp4"]
        with pytest.raises(ValueError):
            app.paths_of([])
        assert app.query_source({"source": ["x"]}) == "x" and app.query_source({"source": ["x", "y"]}) == ["x", "y"]
