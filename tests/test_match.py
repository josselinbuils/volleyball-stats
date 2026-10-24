from pathlib import Path

from volleyball_stats.match import in_rallies, report


class TestInRallies:
    def test_keeps_frames_inside_a_window_started_early(self):
        assert in_rallies([5, 8, 25, 31, 50, 70], [(10, 30), (60, 65)], lead=2) == [8, 25]


class TestReport:
    def test_summarizes_rallies_actions_and_timings(self):
        typed = [(10, 0, 0, "serve", "left"), (20, 0, 0, "pass", "right"), (650, 0, 0, "serve", "right")]

        text = report(Path("m.mp4"), 30.0, 18000, [(0, 300), (600, 1200)], typed, [15], {"ball": 120.0})

        assert "- Duration: 10.0 min" in text
        assert "- Rallies: 2, ball in play 0.5 min (5%), median rally 15.0 s" in text
        assert "- Contacts in rallies: 3, 1.5 per rally" in text
        assert "| serve | 1 | 1 |" in text and "| pass | 0 | 1 |" in text
        assert "ball 2.0 min" in text

    def test_splits_by_side_without_teams_and_says_teams_need_the_players(self):
        text = report(Path("m.mp4"), 30.0, 300, [], [], [], {})

        assert "| Action | Left of the net | Right of the net |" in text
        assert "Teams need the player tracks (--players)" in text
        assert "Player tracks" not in text

    def test_splits_by_team_with_a_section_per_set(self):
        typed = [(10, 0, 0, "serve", "left"), (20, 0, 0, "pass", "right"), (650, 0, 0, "serve", "left"), (660, 0, 0, "attack", "right")]

        text = report(Path("m.mp4"), 30.0, 18000, [(0, 300), (600, 1200)], typed, [], {}, {"Bègles": 7, "Team 2": 6}, ["Bègles", "Team 2"], [1, 2, 2, 1], [1, 2])

        assert "- Player tracks: 7 Bègles, 6 Team 2" in text
        assert "- Sets: 2" in text
        assert "| Action | Bègles | Team 2 |" in text and "| serve | 1 | 1 |" in text
        assert "Left of the net" not in text and "--players" not in text
        set_2 = text[text.index("## Set 2") :]
        assert "- Rallies: 1, contacts: 2" in set_2 and "| serve | 0 | 1 |" in set_2 and "| attack | 1 | 0 |" in set_2

    def test_has_no_set_sections_for_a_single_set(self):
        assert "## Set" not in report(Path("m.mp4"), 30.0, 300, [(0, 30)], [], [], {}, {}, ["A", "B"], [], [1])

    def test_handles_a_video_without_rallies(self):
        assert "- Rallies: 0, ball in play 0.0 min (0%)\n" in report(Path("m.mp4"), 30.0, 300, [], [], [], {})

    def test_heads_with_the_default_title_built_from_the_tables_names_and_the_date(self):
        text = report(Path("m.mp4"), 30.0, 300, [], [], [], {}, {}, ["ASPOM Bègles", "Team 2"], [], [], "2016-12-21")

        assert text.startswith("# Match ASPOM Bègles vs Team 2 · 21 December 2016\n")
        assert "| Action | ASPOM Bègles | Team 2 |" in text
        assert report(Path("m.mp4"), 30.0, 300, [], [], [], {}, {}, ["A", "B"], [], []).startswith("# Match A vs B\n")

    def test_heads_with_a_typed_title_or_the_video_name_without_teams(self):
        assert report(Path("m.mp4"), 30.0, 300, [], [], [], {}, {}, ["A", "B"], [], [], "2026-11-02", "Finale").startswith("# Finale · 2 November 2026\n")
        assert report(Path("m.mp4"), 30.0, 300, [], [], [], {}).startswith("# m\n")
