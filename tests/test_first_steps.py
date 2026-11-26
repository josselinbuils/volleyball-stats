import json

import pytest

from volleyball_stats import files, first_steps, identity, matches


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestFirstSteps:
    def test_a_new_install_has_nothing_done(self, tmp_path):
        assert first_steps.state(tmp_path, []) == {"done": [], "hidden": False, "review_intro": False}

    def test_ticks_each_step_from_the_files(self, tmp_path):
        write(tmp_path / "club" / "club.json", {"name": "ASPOM", "light": {"accent": "#000", "header": "#000"}, "teams": ["Loisirs 1"]})
        write(tmp_path / "placement" / "verdict.json", {"ok": True})
        assert first_steps.state(tmp_path, [])["done"] == ["club", "framing"]
        first_steps.mark(tmp_path, "guide")
        listed = [{"path": "m", "ready": True}]
        assert first_steps.state(tmp_path, listed)["done"] == ["club", "guide", "framing", "import", "analysis"]
        write(tmp_path / "matches" / "m" / files.ANSWERS, {"log": [{"id": 1, "applied": False}]})
        assert "review" not in first_steps.state(tmp_path, listed)["done"]
        write(tmp_path / "matches" / "m" / identity.NAMES, {"players": [{"name": "Léa"}]})
        found = first_steps.state(tmp_path, listed)
        assert "review" in found["done"] and found["review_intro"]
        write(tmp_path / matches.EXPORT, {})
        assert first_steps.state(tmp_path, listed)["done"] == list(first_steps.STEPS)

    def test_a_club_without_teams_is_not_done(self, tmp_path):
        write(tmp_path / "club" / "club.json", {"name": "ASPOM", "light": {"accent": "#000", "header": "#000"}})
        assert first_steps.state(tmp_path, [])["done"] == []

    def test_an_analysed_match_counts_the_guide_and_the_framing(self, tmp_path):
        assert first_steps.state(tmp_path, [{"path": "m", "ready": True}])["done"] == ["guide", "framing", "import", "analysis"]

    def test_a_step_done_once_stays_done(self, tmp_path):
        first_steps.state(tmp_path, [{"path": "m", "ready": False}])
        assert first_steps.state(tmp_path, [])["done"] == ["framing", "import"]

    def test_marks_what_a_screen_saw(self, tmp_path):
        first_steps.mark(tmp_path, "hidden")
        first_steps.mark(tmp_path, "review_intro")
        assert first_steps.state(tmp_path, []) == {"done": [], "hidden": True, "review_intro": True}
        first_steps.mark(tmp_path, "hidden", False)
        assert not first_steps.state(tmp_path, [])["hidden"]
        with pytest.raises(ValueError):
            first_steps.mark(tmp_path, "share")
