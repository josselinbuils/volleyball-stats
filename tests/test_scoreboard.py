from volleyball_stats.review import board_off, missed_points
from volleyball_stats.scoreboard import boards, grid, parse, steady


class TestParse:
    def test_splits_the_scores_around_the_two_set_digits(self):
        assert parse("10005", {0}) == (10, 0, 0, 5)
        assert parse("152011", {2}) == (15, 2, 0, 11)
        assert parse("0000", {0}) == (0, 0, 0, 0)

    def test_drops_readings_off_the_sets_played_or_ambiguous(self):
        assert parse("152011", {1}) is None
        assert parse("30", {0}) is None
        assert parse("21015", {1}) is None
        assert parse("12a07", {0}) is None


class TestSteady:
    def test_drops_a_misread_score_going_down(self):
        found = [(0, (10, 0, 0, 4)), (1, (11, 0, 0, 4)), (2, (1, 0, 0, 14)), (3, (11, 0, 0, 5)), (4, (12, 0, 0, 5))]
        assert steady(found) == [found[0], found[1], found[3], found[4]]


class TestBoardOff:
    def page(self, scores):
        rallies = [{"start": 10.0 * k, "end": 10.0 * k + 5, "set": 1, "score": s} for k, s in enumerate(scores)]
        return {"fps": 50.0, "rallies": rallies}

    def texts(self, page, boards_after):
        """The board read on every frame before each next serve."""
        rallies = [(r["start"], r["end"], r["set"]) for r in page["rallies"]]
        out = {}
        for k, text in enumerate(boards_after):
            start = rallies[k][1]
            end = rallies[k + 1][0] if k + 1 < len(rallies) else rallies[k][1] + 3
            for f in grid(start, end, 50.0):
                out[f] = [text]
        return out

    def test_reports_the_rally_after_which_the_scores_part(self):
        page = self.page([[1, 0], [2, 0], [2, 1], [3, 1], [3, 2]])
        # The board never counted the third rally's point.
        texts = self.texts(page, ["1000", "2000", "2000", "3000", "3001"])
        assert [(r["time"], r["shown"]) for r in board_off(page, texts)] == [(25.0, "2-1 ≠ 2-0")]

    def test_a_board_flipped_late_is_no_report(self):
        page = self.page([[1, 0], [2, 0], [3, 0]])
        texts = self.texts(page, ["1000", "1000", "3000"])
        assert board_off(page, texts) == []

    def test_a_board_gaining_more_points_than_rallies_is_a_missed_point(self):
        page = self.page([[1, 0], [2, 0], [3, 0], [4, 0], [5, 0]])
        texts = self.texts(page, ["1000", "2000", "4000", "5000", "6000"])
        assert [(r["kind"], r["time"], r["shown"]) for r in missed_points(page, texts)] == [("auto.missedPoint", 25.0, "2-0 → 4-0")]

    def test_a_missed_point_over_several_rallies_names_them(self):
        page = self.page([[1, 0], [2, 0], [3, 0], [4, 0], [5, 0]])
        texts = self.texts(page, ["1000", "2000", "?", "5000", "6000"])
        assert [(r["time"], r["shown"]) for r in missed_points(page, texts)] == [(35.0, "2-0 → 5-0 (3–4)")]

    def test_a_board_flipped_late_or_keeping_up_is_no_missed_point(self):
        page = self.page([[1, 0], [2, 0], [3, 0], [4, 0]])
        assert missed_points(page, self.texts(page, ["1000", "1000", "3000", "4000"])) == []
        assert missed_points(page, self.texts(page, ["1000", "2000", "3000", "4000"])) == []

    def test_a_rally_to_replay_may_give_the_board_a_point_or_none(self):
        page = self.page([[1, 0], [1, 0], [2, 0], [3, 0]])
        page["rallies"][1]["redo"] = True
        assert missed_points(page, self.texts(page, ["1000", "1000", "2000", "3000"])) == []
        assert missed_points(page, self.texts(page, ["1000", "2000", "3000", "4000"])) == []
        assert [r["shown"] for r in missed_points(page, self.texts(page, ["1000", "3000", "4000", "5000"]))] == ["1-0 → 3-0"]

    def test_fits_the_board_turned_round(self):
        page = self.page([[1, 0], [1, 1], [2, 1]])
        texts = self.texts(page, ["0001", "1001", "1002"])
        assert board_off(page, texts) == []
        assert len(boards(texts, [(r["start"], r["end"], r["set"]) for r in page["rallies"]], 50.0)) == 3
