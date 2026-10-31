import json

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
