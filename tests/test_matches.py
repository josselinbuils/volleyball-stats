import json

from volleyball_stats.matches import build


class TestBuild:
    def test_lists_the_match_pages_newest_first_and_loads_the_list_by_its_hash(self, tmp_path):
        for name, date in (("old", "2026-09-01"), ("new", "2026-10-25")):
            (tmp_path / name).mkdir()
            data = {"name": name, "date": date, "teams": None, "rallies": [{"set": 1}, {"set": 2}, {"set": 2}]}
            (tmp_path / name / "data.js").write_text(f"window.MATCH = {json.dumps(data)};\n")

        matches = build(tmp_path, "none")

        assert [(m["path"], m["sets"], m["rallies"]) for m in matches] == [("new/", 2, 3), ("old/", 2, 3)]
        assert (tmp_path / "matches.js").read_text().startswith('window.MATCHES = {"matches":[{"path":"new/"')
        assert 'src="matches.js?v=' in (tmp_path / "index.html").read_text()
        assert not (tmp_path / "matches.html").exists()
