import base64
import json

import cv2
import numpy as np
import pytest

from volleyball_stats import branding, web


class TestBranding:
    @staticmethod
    def png(colour=(0, 0, 255)) -> str:
        image = np.zeros((20, 40, 3), np.uint8)
        image[:] = colour
        return "data:image/png;base64," + base64.b64encode(cv2.imencode(".png", image)[1].tobytes()).decode()

    def test_saves_reads_and_keeps_the_pictures(self, tmp_path):
        folder = tmp_path / "brand"
        branding.save({"name": "Club", "url": "https://club.fr", "accent": "#e30613", "header": "#111111", "logo": self.png(), "sponsors": [{"name": "A", "background": "#ffffff", "logo": self.png((0, 255, 0))}, {"name": "B", "background": "#000000"}]}, folder)
        found = branding.read(folder)
        assert (found["name"], found["url"], found["accent"]) == ("Club", "https://club.fr", "#e30613")
        assert (folder / found["logo"]).exists() and (folder / "sponsors" / found["sponsors"][0]["logo"]).exists()
        listed = json.loads((folder / "sponsors" / "sponsors.json").read_text())
        assert listed[1] == {"name": "B", "background": "#000000", "text": "#ffffff"}
        # Kept by name, a new name, the old pictures gone.
        branding.save({**found, "name": "Club 2", "sponsors": [{**found["sponsors"][0], "name": "A2"}]}, folder)
        again = branding.read(folder)
        assert again["logo"] == found["logo"] and again["sponsors"][0]["logo"] == found["sponsors"][0]["logo"]
        assert sorted(p.name for p in (folder / "sponsors").iterdir()) == sorted([found["sponsors"][0]["logo"], "sponsors.json"])

    def test_keeps_the_club_s_teams_until_sent_again(self, tmp_path):
        folder = tmp_path / "brand"
        body = {"name": "Club", "accent": "#e30613", "header": "#111111"}
        branding.save(body, folder)
        assert branding.read(folder)["teams"] is None
        branding.save({**body, "teams": [" A 1", "A 2", "A 1"]}, folder)
        branding.save(body, folder)
        assert branding.read(folder)["teams"] == ["A 1", "A 2"]
        with pytest.raises(ValueError):
            branding.save({**body, "teams": [""]}, folder)

    def test_makes_the_colours_follow_a_new_accent_only(self, tmp_path):
        folder = tmp_path / "brand"
        branding.save({"name": "Club", "accent": "#e30613", "header": "#111111"}, folder)
        data = json.loads((folder / "brand.json").read_text())
        data["light"]["accentText"] = "#123456"
        (folder / "brand.json").write_text(json.dumps(data))
        branding.save({"name": "Club 2", "accent": "#e30613", "header": "#111111"}, folder)
        assert json.loads((folder / "brand.json").read_text())["light"]["accentText"] == "#123456"
        branding.save({"name": "Club 2", "accent": "#00ff00", "header": "#111111"}, folder)
        assert json.loads((folder / "brand.json").read_text())["light"]["accentText"] != "#123456"

    def test_refuses_what_it_cannot_show(self, tmp_path):
        for body in ({"name": "", "accent": "#000000", "header": "#000000"}, {"name": "A", "accent": "red", "header": "#000000"}, {"name": "A", "url": "javascript:x", "accent": "#000000", "header": "#000000"}, {"name": "A", "accent": "#000000", "header": "#000000", "logo": "../x.png"}):
            with pytest.raises(ValueError):
                branding.save(body, tmp_path / "brand")

    def test_starts_from_a_preset_or_none(self, tmp_path):
        folder = tmp_path / "brand"
        preset = branding.presets()[0]["id"]
        branding.save({"name": "Club", "accent": "#e30613", "header": "#111111", "teams": ["A 1"]}, folder)
        branding.use(preset, folder)
        assert (branding.read(folder)["name"], branding.read(folder)["teams"]) == (branding.presets()[0]["name"], ["A 1"])
        branding.use("none", folder)
        assert branding.read(folder) is None
        with pytest.raises(LookupError):
            branding.use("../x", folder)

    def test_serves_only_its_pictures(self, tmp_path):
        folder = tmp_path / "brand"
        branding.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": self.png()}, folder)
        assert branding.file(branding.read(folder)["logo"], folder)
        assert branding.file("brand.json", folder) is None and branding.file("../x.png", folder) is None

    def test_the_pages_show_the_apps_branding(self, tmp_path, monkeypatch):
        monkeypatch.setattr(branding, "BRAND", tmp_path / "brand")
        assert web.brand(web.CLUB, tmp_path / "site") is None
        branding.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": self.png()}, tmp_path / "brand")
        shown = web.brand(web.CLUB, tmp_path / "site")
        assert shown["name"] == "Club" and (tmp_path / "site" / shown["logo"]).exists()

    def test_refuses_its_own_files_as_pictures(self, tmp_path):
        folder = tmp_path / "brand"
        branding.save({"name": "Club", "accent": "#e30613", "header": "#111111"}, folder)
        with pytest.raises(ValueError):
            branding.save({"name": "Club", "accent": "#e30613", "header": "#111111", "logo": "brand.json"}, folder)
        assert branding.file("/etc/x.png", folder) is None
