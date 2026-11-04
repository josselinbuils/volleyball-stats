from collections import Counter

from volleyball_stats import timeouts


class TestFound:
    FPS, STEP = 10.0, 5

    def counts(self, last: int, empty: range = range(0)) -> Counter:
        return Counter({at: 2 if at in empty else 11 for at in range(0, last, self.STEP)})

    def test_a_gap_with_the_court_near_empty_long_enough(self):
        rallies = [(0, 100, 1), (700, 800, 1)]
        assert timeouts.found(rallies, self.counts(900, range(200, 600)), self.STEP, self.FPS) == [(100, 700)]

    def test_a_long_gap_with_a_full_court(self):
        assert timeouts.found([(0, 100, 1), (1000, 1100, 1)], self.counts(1200), self.STEP, self.FPS) == [(100, 1000)]

    def test_a_full_court_a_short_emptying_a_set_break_and_a_very_long_gap_are_none(self):
        assert timeouts.found([(0, 100, 1), (700, 800, 1)], self.counts(900), self.STEP, self.FPS) == []
        assert timeouts.found([(0, 100, 1), (700, 800, 1)], self.counts(900, range(200, 400)), self.STEP, self.FPS) == []
        assert timeouts.found([(0, 100, 1), (1000, 1100, 2)], self.counts(1200, range(200, 800)), self.STEP, self.FPS) == []
        assert timeouts.found([(0, 100, 1), (3000, 3100, 1)], self.counts(3200, range(200, 2800)), self.STEP, self.FPS) == []


class TestOnCourt:
    def test_counts_the_feet_on_the_court_at_each_step(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text("frame,track,court_x,court_y\n0,1,1.0,1.0\n0,2,-9.0,4.0\n0,3,12.0,0.0\n0,4,0.0,7.0\n0,5,,\n3,1,0.0,0.0\n5,1,0.0,0.0\n")
        assert timeouts.on_court(path, 5) == {0: 2, 5: 1}


class TestMerged:
    def test_answers_replace_what_they_overlap(self):
        detected = [(100, 200), (300, 400), (500, 600)]
        answers = [{"start": 300, "end": 400, "team": 2}, {"start": 500, "end": 600, "removed": True}, {"start": 700, "end": 800, "team": None}]
        assert timeouts.merged(detected, answers) == [
            {"start": 100, "end": 200, "team": None},
            {"start": 300, "end": 400, "team": 2},
            {"start": 700, "end": 800, "team": None},
        ]

    def test_an_answer_survives_a_rerun_moving_the_gap(self):
        assert timeouts.merged([(290, 410)], [{"start": 300, "end": 400, "team": 1}]) == [{"start": 300, "end": 400, "team": 1}]


class TestAdded:
    RALLIES = [(0, 100, 1), (500, 600, 1), (5000, 5100, 1)]

    def test_takes_the_gap_it_falls_in(self):
        assert timeouts.added(300, self.RALLIES, 10.0) == {"start": 100, "end": 500, "team": None}

    def test_a_short_span_inside_a_rally_or_a_very_long_gap(self):
        assert timeouts.added(550, self.RALLIES, 10.0) == {"start": 550, "end": 850, "team": None}
        assert timeouts.added(1000, self.RALLIES, 10.0) == {"start": 1000, "end": 1300, "team": None}


class TestAnswer:
    def test_corrections_are_kept_and_the_last_wins(self, tmp_path):
        (tmp_path / timeouts.DETECTED).write_text("start_frame,end_frame\n100,200\n300,400\n")
        assert timeouts.answer(tmp_path, 10.0, {"start": 100, "end": 200, "team": 2})[0]["team"] == 2
        assert timeouts.answer(tmp_path, 10.0, {"start": 100, "end": 200, "team": None})[0]["team"] is None
        assert [t["start"] for t in timeouts.answer(tmp_path, 10.0, {"start": 300, "end": 400, "removed": True})] == [100]
        assert [t["start"] for t in timeouts.shown(tmp_path, 10.0)] == [100]

    def test_moving_a_bound_replaces_the_timeout_and_what_was_detected(self, tmp_path):
        (tmp_path / timeouts.DETECTED).write_text("start_frame,end_frame\n100,500\n")
        timeouts.answer(tmp_path, 10.0, {"start": 100, "end": 500, "team": 2})
        timeouts.answer(tmp_path, 10.0, {"start": 200, "end": 500, "team": 2})
        assert timeouts.answer(tmp_path, 10.0, {"start": 200, "end": 450, "team": 2}) == [{"start": 200, "end": 450, "team": 2}]
        assert timeouts.shown(tmp_path, 10.0) == [{"start": 200, "end": 450, "team": 2}]

    def test_adding_takes_back_a_removal(self, tmp_path):
        (tmp_path / timeouts.DETECTED).write_text("start_frame,end_frame\n")
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame,left,set\n0,100,1,1\n500,600,1,1\n")
        timeouts.answer(tmp_path, 10.0, {"start": 100, "end": 500, "removed": True})
        assert timeouts.answer(tmp_path, 10.0, {"frame": 300}) == [{"start": 100, "end": 500, "team": None}]


class TestReadDetected:
    def test_detects_when_an_older_run_left_none(self, tmp_path):
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame,left,set\n0,100,1,1\n1000,1100,1,1\n")
        (tmp_path / "players.csv").write_text("frame,track,court_x,court_y\n")
        assert timeouts.read_detected(tmp_path, 10.0) == [(100, 1000)]
        assert (tmp_path / timeouts.DETECTED).exists()

    def test_none_without_the_tracks(self, tmp_path):
        assert timeouts.read_detected(tmp_path, 10.0) == []
