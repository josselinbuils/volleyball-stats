import base64
import json

import cv2
import numpy as np
import pytest

from volleyball_stats import club_settings, web


class TestClubSettings:
    @staticmethod
    def png(colour=(0, 0, 255)) -> str:
        image = np.zeros((20, 40, 3), np.uint8)
        image[:] = colour
        return "data:image/png;base64," + base64.b64encode(cv2.imencode(".png", image)[1].tobytes()).decode()

    def test_saves_reads_and_keeps_the_pictures(self, tmp_path):
        folder = tmp_path / "club"
        club_settings.save({"name": "Club", "url": "https://club.fr", "accent": "#e30613", "header": "#111111", "logo": self.png(), "sponsors": [{"name": "A", "background": "#ffffff", "logo": self.png((0, 255, 0))}, {"name": "B", "background": "#000000"}]}, folder)
        found = club_settings.read(folder)
        assert (found["name"], found["url"], found["accent"]) == ("Club", "https://club.fr", "#e30613")
        assert (folder / found["logo"]).exists() and (folder / "sponsors" / found["sponsors"][0]["logo"]).exists()
        listed = json.loads((folder / "sponsors" / "sponsors.json").read_text())
        assert listed[1] == {"name": "B", "background": "#000000", "text": "#ffffff"}
        # Kept by name, a new name, the old pictures gone.
        club_settings.save({**found, "name": "Club 2", "sponsors": [{**found["sponsors"][0], "name": "A2"}]}, folder)
        again = club_settings.read(folder)
        assert again["logo"] == found["logo"] and again["sponsors"][0]["logo"] == found["sponsors"][0]["logo"]
        assert sorted(p.name for p in (folder / "sponsors").iterdir()) == sorted([found["sponsors"][0]["logo"], "sponsors.json"])

    def test_keeps_the_club_s_teams_until_sent_again(self, tmp_path):
        folder = tmp_path / "club"
        body = {"name": "Club", "accent": "#e30613", "header": "#111111"}
        club_settings.save(body, folder)
        assert club_settings.read(folder)["teams"] is None
        club_settings.save({**body, "teams": [" A 1", "A 2", "A 1"]}, folder)
        club_settings.save(body, folder)
        assert club_settings.read(folder)["teams"] == ["A 1", "A 2"]
        with pytest.raises(ValueError):
            club_settings.save({**body, "teams": [""]}, folder)

    def test_makes_the_colours_follow_a_new_accent_only(self, tmp_path):
        folder = tmp_path / "club"
        club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111"}, folder)
        data = json.loads((folder / club_settings.FILE).read_text())
        data["light"]["accentText"] = "#123456"
        (folder / club_settings.FILE).write_text(json.dumps(data))
        club_settings.save({"name": "Club 2", "accent": "#e30613", "header": "#111111"}, folder)
        assert json.loads((folder / club_settings.FILE).read_text())["light"]["accentText"] == "#123456"
        club_settings.save({"name": "Club 2", "accent": "#00ff00", "header": "#111111"}, folder)
        assert json.loads((folder / club_settings.FILE).read_text())["light"]["accentText"] != "#123456"

    def test_refuses_what_it_cannot_show(self, tmp_path):
        for body in ({"name": "", "accent": "#000000", "header": "#000000"}, {"name": "A", "accent": "red", "header": "#000000"}, {"name": "A", "url": "javascript:x", "accent": "#000000", "header": "#000000"}, {"name": "A", "accent": "#000000", "header": "#000000", "logo": "../x.png"}):
            with pytest.raises(ValueError):
                club_settings.save(body, tmp_path / "club")

    def test_starts_from_a_theme_or_none(self, tmp_path):
        folder = tmp_path / "club"
        theme = club_settings.themes()[0]["id"]
        club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111", "teams": ["A 1"]}, folder)
        club_settings.use(theme, folder)
        assert (club_settings.read(folder)["name"], club_settings.read(folder)["teams"]) == (club_settings.themes()[0]["name"], ["A 1"])
        club_settings.use("none", folder)
        assert club_settings.read(folder) is None
        with pytest.raises(LookupError):
            club_settings.use("../x", folder)

    def test_moves_the_club_kept_as_brand(self, tmp_path):
        old = tmp_path / "brand"
        old.mkdir()
        (old / "brand.json").write_text("{}")
        club_settings.migrate(tmp_path / "club", old)
        assert not old.exists() and (tmp_path / "club" / club_settings.FILE).exists()

    def test_serves_only_its_pictures(self, tmp_path):
        folder = tmp_path / "club"
        club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": self.png()}, folder)
        assert club_settings.file(club_settings.read(folder)["logo"], folder)
        assert club_settings.file(club_settings.FILE, folder) is None and club_settings.file("../x.png", folder) is None

    def test_the_pages_show_the_apps_club(self, tmp_path, monkeypatch):
        monkeypatch.setattr(club_settings, "FOLDER", tmp_path / "club")
        assert web.club_page(web.CLUB, tmp_path / "site") is None
        club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": self.png()}, tmp_path / "club")
        shown = web.club_page(web.CLUB, tmp_path / "site")
        assert shown["name"] == "Club" and (tmp_path / "site" / shown["logo"]).exists()

    def test_refuses_its_own_files_as_pictures(self, tmp_path):
        folder = tmp_path / "club"
        club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111"}, folder)
        with pytest.raises(ValueError):
            club_settings.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": club_settings.FILE}, folder)
        assert club_settings.file("/etc/x.png", folder) is None
