import json

from volleyball_stats import learn
from volleyball_stats.learn import from_answers, near, record, report


class TestRecord:
    def test_the_replaced_scores_are_kept_with_the_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(learn, "scores", lambda *_: {"who": (3, 4)})
        record(tmp_path, tmp_path, tmp_path)
        record(tmp_path, tmp_path, tmp_path, {"who": (2, 4)})
        first, second = json.loads((tmp_path / "learn.json").read_text())
        assert "before" not in first
        assert second["before"] == {"who": [2, 4]}


class TestNear:
    def test_within(self):
        assert near(100, [80, 104, 130], 5) == 104
        assert near(100, [80, 130], 5) is None


class TestReport:
    def test_change_shown(self):
        text = report({"a": (3, 5), "b": (1, 2)}, {"a": [2, 5], "b": [1, 2]})
        assert "3/5  (was 2/5)" in text
        assert "was" not in text.splitlines()[1]


class TestFromAnswers:
    def test_scores(self, tmp_path):
        (tmp_path / "identity_answers.json").write_text(json.dumps({
            "touch": [{"frame": 100, "team": 1, "identity": 3, "name": None}, {"frame": 300, "team": 2, "identity": None, "name": None}],
            "added": [{"start": 90, "frame": 205, "team": 1, "type": "set"}, {"start": 90, "frame": 400, "team": 1, "type": "set"}],
            "action": [{"frame": 100, "type": "pass"}],
            "rally": [{"start": 90, "play": True}, {"start": 500, "play": False}],
        }))
        (tmp_path / "actions.csv").write_text("frame,type,team,identity\n100,pass,1,3\n200,set,1,4\n")
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n90,450\n")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity\n")

        out = from_answers(tmp_path, 50.0)

        assert out["attribution: answered touches"] == (1, 1)
        assert out["contacts: added touches found"] == (1, 2)
        assert out["contacts: false ones gone"] == (1, 1)
        assert out["actions: types set"] == (1, 1)
        assert out["rallies: kept"] == (1, 1)
        assert out["rallies: dropped"] == (1, 1)


class TestReviewed:
    def test_the_other_answered_matches_with_their_video(self, tmp_path, monkeypatch):
        monkeypatch.setattr(learn, "ROOT", tmp_path)
        (tmp_path / "a.mp4").touch()
        for name, answered, video in (("open", True, "a.mp4"), ("other", True, "a.mp4"), ("unanswered", False, "a.mp4"), ("no_video", True, "gone.mp4")):
            folder = tmp_path / "matches" / name
            folder.mkdir(parents=True)
            (folder / "source.json").write_text(json.dumps({"video": video, "court": "c.json"}))
            if answered:
                (folder / "identity_answers.json").write_text("{}")

        assert learn.reviewed(tmp_path / "matches" / "open") == [f"{tmp_path / 'matches' / 'other'}:{tmp_path / 'a.mp4'}:{tmp_path / 'c.json'}"]
