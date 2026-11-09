import json

import pytest

from volleyball_stats import app, files, jobs


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

    def test_tells_what_each_match_waits_for(self, place):
        self.match(place, "a")
        self.match(place, "b", app.COURT)
        self.match(place, "c", files.SOURCE)
        self.match(place, "d", "report.md")
        self.match(place, "e")
        self.job(place, "e", failed="court", error="No stored court matches")
        self.match(place, "f", app.COURT)
        self.job(place, "f", kind="pipeline", failed="pipeline", error="boom")
        found = {m["name"]: m["state"] for m in app.preparing([{"path": "d", "ready": True}])}
        assert found == {"a": "court", "b": "check", "c": "elsewhere", "e": "court", "f": "failed"}

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
        assert app.handle("GET", "/app/image", "match=..&kind=start", {}, list)[2] == 404
        assert app.handle("GET", "/other", "", {}, list) is None

    def test_estimates_the_time_left(self):
        tracking = {"started": 0.0, "stepStarted": 0.0, "step": "pipeline", "stage": "tracking", "progress": 0.5, "duration": app.TOOK_VIDEO_S}
        left = app.time_left(tracking, 100.0)
        assert left > 100.0
        assert app.time_left({**tracking, "duration": app.TOOK_VIDEO_S / 10}, 100.0) < left
        assert app.time_left({"started": 0.0, "step": "import", "progress": 0.25}, 100.0) == pytest.approx(300.0)
