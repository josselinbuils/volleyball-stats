import json

import numpy as np

from volleyball_stats import play_training, playing
from volleyball_stats.actions import LEAD_S

RALLIES = [{"key": 100, "start": 10.0, "end": 20.0}, {"key": 200, "start": 40.0, "end": 50.0}]
CONTACTS = [{"rally": 0, "type": "serve", "t": 10.0}, {"rally": 0, "type": "attack", "t": 16.0}, {"rally": 0, "type": "floor", "t": 17.0}, {"rally": 1, "type": "serve", "t": 40.0}]


def make(outputs, name: str, checked: list[int], video: bool = True, rallies: list[dict] = RALLIES):
    """A match folder with its review's page, the rallies of `checked` checked and its video beside the outputs."""
    match = outputs / "matches" / name
    (match / "review").mkdir(parents=True)
    (match / "review" / "data.js").write_text("window.MATCH = " + json.dumps({"rallies": rallies, "contacts": CONTACTS}) + ";")
    (match / "identity_answers.json").write_text(json.dumps({"log": [{"id": "ok", "checked": checked}]}))
    path = outputs / f"{name}.mp4"
    if video:
        path.write_bytes(b"video")
    (match / "source.json").write_text(json.dumps({"video": str(path), "court": "court.json"}))
    return match


def weights(outputs, matches: dict[str, str]) -> None:
    folder = outputs / playing.WEIGHTS
    folder.mkdir(parents=True, exist_ok=True)
    (folder / playing.MODEL).touch()
    (folder / play_training.TRAINED).write_text(json.dumps({"matches": matches}))


class TestSpans:
    def test_each_rally_s_serve_last_player_touch_and_end(self, tmp_path):
        match = make(tmp_path, "a", [100, 200])

        assert play_training.spans(match) == [(10.0 - LEAD_S, 16.0, 20.0), (40.0 - LEAD_S, 40.0, 50.0)]

    def test_none_while_a_rally_is_unchecked_or_the_page_is_missing(self, tmp_path):
        assert play_training.spans(make(tmp_path, "a", [100])) is None
        assert play_training.spans(tmp_path / "matches" / "nowhere") is None


class TestLabels:
    def test_play_from_the_serve_to_just_after_the_last_touch_no_play_later_unsure_between(self):
        label, sure = play_training.labels([(10.0, 16.0, 20.0)], 8 * 60)
        at = lambda seconds: round(seconds * playing.FPS - playing.T / 2)  # noqa: E731

        assert label[at(12)] == 1 and sure[at(12)]
        assert label[at(5)] == 0 and sure[at(5)] and label[at(25)] == 0 and sure[at(25)]
        assert not sure[at(18)] and not sure[at(10)]
        assert len(label) == 8 * 60 - playing.T + 1


class TestDue:
    def test_the_matches_fully_checked_whose_video_is_here(self, tmp_path):
        a, b = make(tmp_path, "a", [100, 200]), make(tmp_path, "b", [100])
        make(tmp_path, "c", [100, 200], video=False)

        assert [m.name for m, _ in play_training.due(a)] == ["a"]
        assert [m.name for m, _ in play_training.due(b)] == ["a"]

    def test_nothing_once_the_weights_know_them(self, tmp_path):
        a = make(tmp_path, "a", [100, 200])
        weights(tmp_path, play_training.signature(play_training.sources(a)))

        assert play_training.due(a) == []

    def test_again_when_a_match_is_checked_or_its_rallies_change(self, tmp_path):
        a = make(tmp_path, "a", [100, 200])
        weights(tmp_path, play_training.signature(play_training.sources(a)))
        make(tmp_path, "b", [100, 200], rallies=[{**RALLIES[0], "end": 22.0}, RALLIES[1]])

        assert [m.name for m, _ in play_training.due(a)] == ["a", "b"]

    def test_never_on_fewer_matches_than_the_weights_know(self, tmp_path):
        a = make(tmp_path, "a", [100, 200])
        weights(tmp_path, {"a": "old", "elsewhere": "known"})

        assert play_training.due(a) == []


class TestFrames:
    def test_kept_and_read_back_while_the_video_is_the_same(self, tmp_path, monkeypatch):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"video")
        made = [np.full((playing.HEIGHT, playing.WIDTH, 3), k, np.uint8) for k in range(3)]
        calls = []
        monkeypatch.setattr(playing, "frames", lambda v: calls.append(v) or iter(made))

        first = play_training.frames(video, tmp_path / "cache", "match")
        again = play_training.frames(video, tmp_path / "cache", "match")

        assert first.shape == (3, playing.HEIGHT, playing.WIDTH, 3) and [int(f[0, 0, 0]) for f in again] == [0, 1, 2] and len(calls) == 1

        video.write_bytes(b"another video")
        play_training.frames(video, tmp_path / "cache", "match")
        assert len(calls) == 2
