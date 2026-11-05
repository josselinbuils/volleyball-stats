import json

import pytest

from volleyball_stats import backup, files
from volleyball_stats.rename import rename_match, target_name


class TestRename:
    @staticmethod
    def match(tmp_path, monkeypatch, video="data/old.mp4", court="outputs/court/old.json"):
        monkeypatch.chdir(tmp_path)
        match = tmp_path / "outputs" / "old"
        match.mkdir(parents=True)
        for path in (video, court, "data/old_1080p.mp4", "outputs/court/old.jpg", "outputs/court/old_clicks.json", "outputs/court/older.json"):
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).touch()
        files.write_source(match, video, court)
        (match / "report.md").touch()
        (match / "teams.json").write_text(json.dumps({"date": "2026-11-02", "teams": [{"name": "AVIA 01"}, {"name": "ASPOM Bègles"}]}))
        return match

    def test_the_name_comes_from_the_date_and_the_teams(self, tmp_path, monkeypatch):
        assert target_name(self.match(tmp_path, monkeypatch)) == "2026-11-02-avia-01-vs-aspom-begles"

    def test_no_name_without_a_date_or_a_team_s_name(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)
        (match / "teams.json").write_text(json.dumps({"date": "2026-11-02", "teams": [{"name": "A"}, {"name": None}]}))
        assert target_name(match) is None
        (match / "teams.json").write_text(json.dumps({"date": None, "teams": [{"name": "A"}, {"name": "B"}]}))
        assert target_name(match) is None

    def test_moves_the_match_s_files_and_keeps_the_old_name_as_an_alias(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)

        target = rename_match(match, "new", tmp_path / "data")

        assert target == tmp_path / "outputs" / "new" and not match.exists()
        given = json.loads((target / files.SOURCE).read_text())
        assert given["aliases"] == ["old"] and (tmp_path / given["video"]).name == "new.mp4"
        assert sorted(p.name for p in (tmp_path / "data" / "new").iterdir()) == ["new.mp4", "old_1080p.mp4"]
        assert (target / "court.json").exists() and (target / "court.jpg").exists() and (target / "old_clicks.json").exists()
        assert given["court"].endswith("new/court.json")
        # Another match whose name starts alike stays.
        assert (tmp_path / "outputs" / "court" / "older.json").exists()

    def test_renames_again_from_the_match_s_own_folder_keeping_every_alias(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)
        data = tmp_path / "data"
        files_first = rename_match(match, "two", data)
        given = json.loads((files_first / files.SOURCE).read_text())
        given["video"] = "data/two/two.mp4"
        (files_first / files.SOURCE).write_text(json.dumps(given))

        target = rename_match(files_first, "three", data)

        assert json.loads((target / files.SOURCE).read_text())["aliases"] == ["old", "two"]
        assert not (data / "two").exists()
        assert sorted(p.name for p in (data / "three").iterdir()) == ["old_1080p.mp4", "three.mp4"]

    def test_a_court_of_the_library_stays_for_the_next_matches(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch, court="outputs/courts/gym.json")

        target = rename_match(match, "new", tmp_path / "data")

        assert (tmp_path / "outputs" / "courts" / "gym.json").exists()
        assert json.loads((target / files.SOURCE).read_text())["court"] == "outputs/courts/gym.json"

    def test_moves_the_hosted_copies_and_says_where_they_are(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)
        copy = tmp_path / "data" / "hosted_copies" / "light.mp4"
        copy.parent.mkdir()
        copy.touch()
        (match / "publish.json").write_text(json.dumps({"site": "outputs/hosted", "light": str(copy), "av1": None}))

        target = rename_match(match, "new", tmp_path / "data")

        saved = json.loads((target / "publish.json").read_text())
        assert saved["light"].endswith("data/new/reencoded/light.mp4") and (tmp_path / "data" / "new" / "reencoded" / "light.mp4").exists()
        assert saved["av1"] is None and not copy.exists()

    def test_the_copies_stay_in_their_folder(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch, video="data/old/old.mp4")
        copy = tmp_path / "data" / "old" / "reencoded" / "old_720p.mp4"
        copy.parent.mkdir()
        copy.touch()
        (match / "publish.json").write_text(json.dumps({"site": "outputs/hosted", "small": str(copy)}))

        target = rename_match(match, "new", tmp_path / "data")

        assert json.loads((target / "publish.json").read_text())["small"] == str((tmp_path / "data" / "new" / "reencoded" / "old_720p.mp4").resolve())
        assert (tmp_path / "data" / "new" / "reencoded" / "old_720p.mp4").exists()

    def test_moves_the_roster_s_entries(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)
        (tmp_path / "outputs" / "roster.json").write_text(json.dumps({"players": [{"name": "Ana", "vectors": {"old": [1.0], "other": [2.0]}}]}))

        rename_match(match, "new", tmp_path / "data")

        assert json.loads((tmp_path / "outputs" / "roster.json").read_text())["players"][0]["vectors"] == {"new": [1.0], "other": [2.0]}

    def test_refuses_with_nothing_moved(self, tmp_path, monkeypatch):
        match = self.match(tmp_path, monkeypatch)
        data = tmp_path / "data"
        (tmp_path / "outputs" / "taken").mkdir()
        with pytest.raises(ValueError):
            rename_match(match, "taken", data)
        with pytest.raises(ValueError):
            rename_match(match, "old", data)
        (match / "report.md").unlink()
        with pytest.raises(ValueError):
            rename_match(match, "new", data)
        assert match.exists() and (data / "old.mp4").exists()

    def test_the_review_s_source_keeps_the_aliases(self, tmp_path, monkeypatch):
        target = rename_match(self.match(tmp_path, monkeypatch), "new", tmp_path / "data")

        files.write_source(target, "v.mp4", "c.json")

        assert files.aliases(target) == ["old"]


class TestBackups:
    def test_moves_each_dated_copy_s_folder(self):
        command = backup.rename_command("/root/backups", "old", "new")

        assert 'for d in /root/backups/*/' in command and 'mv "$d"old "$d"new' in command and '[ ! -e "$d"new ]' in command
