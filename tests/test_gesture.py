import json

import numpy as np
import pytest

from volleyball_stats import decode, gesture, gesture_training
from volleyball_stats.court import Calibration
from volleyball_stats.players import Row

FPS = 50.0
WINDOWS = [(100, 400)]
TYPED = [(110, 500, 400, "serve", "left"), (200, 1500, 600, "pass", "right"), (260, 1600, 500, "set", "right"), (900, 30, 40, "attack", "left")]


def box(frame: int, track: int, x1: float, y1: float, x2: float, y2: float) -> Row:
    return Row(frame, track, (x1, y1, x2, y2), 0.9, (0.0, 0.0), (0.0, 0.0), "")


def table(touchers=(7, None, 8, None), boxes=None):
    boxes = boxes if boxes is not None else {110: {7: (450, 200, 550, 500)}, 200: {3: (1400, 500, 1500, 700), 4: (100, 100, 200, 300)}}
    return gesture.table(TYPED, list(touchers), WINDOWS, FPS, Calibration(np.eye(3)), {}, boxes, (3840, 2160))


class TestTable:
    def test_each_contact_s_place_in_its_rally(self):
        found = table()

        assert [(t["index"], t["count"], t["prev_type"], t["next_type"]) for t in found[:3]] == [(0, 3, "start", "pass"), (1, 3, "serve", "set"), (2, 3, "pass", "end")]
        assert found[1]["prev_s"] == pytest.approx(90 / FPS) and found[2]["side_run"] == 2 and found[3]["count"] == 1 and found[3]["rally"] < 0

    def test_the_crop_holds_the_credited_box_else_the_nearest_else_a_box_around_the_ball(self):
        found = table()

        assert found[0]["crop"] == [500 - 195, 350 - 195, 390] and found[0]["has_box"]
        assert found[1]["crop"][2] == 360 and found[1]["has_box"]
        assert found[3]["crop"] == [0, 0, 780] and not found[3]["has_box"]

    def test_the_boxes_near_the_contacts_by_frame_and_track(self):
        rows = [box(109, 7, 1, 2, 3, 4), box(110, 7, 5, 6, 7, 8), box(500, 1, 0, 0, 1, 1)]

        assert gesture.boxes_near(rows, {110}) == {109: {7: (1, 2, 3, 4)}, 110: {7: (5, 6, 7, 8)}}

    def test_what_the_heads_read_a_row_a_contact(self):
        tab = gesture.tabular(table())

        assert tab.shape == (4, gesture.TAB) and tab[0, gesture.LABELS.index("serve")] == 1 and tab[1, gesture.LABELS.index("pass")] == 1


class TestTypedBy:
    def test_the_best_touch_class_none_left_out(self):
        p = np.zeros((2, len(gesture.LABELS)), np.float32)
        p[0, gesture.NONE], p[0, gesture.LABELS.index("dig")] = 0.9, 0.1
        p[1, gesture.LABELS.index("set")] = 1

        assert gesture.typed_by(p, ["pass", "attack"]) == ["dig", "set"]


class TestClips:
    def test_cut_once_by_contact_and_crop_while_the_video_is_the_same(self, tmp_path, monkeypatch):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"video")
        asked = []

        def frames(path, wanted, workers=None):
            asked.append(sorted(set(wanted)))
            for f in sorted(set(wanted)):
                yield f, np.full((2160, 3840, 3), f % 251, np.uint8)

        monkeypatch.setattr(decode, "frames_apart", frames)
        rows = table()
        store, at = gesture.clips(video, rows[:2], tmp_path / "cache")
        assert store.shape[0] == 2 and int(store[at[1]][0, 0, 0, 0]) == (200 - 21) % 251 and len(asked) == 1

        store, at = gesture.clips(video, rows, tmp_path / "cache")
        assert store.shape[0] == 4 and asked[1][0] == 260 - 21 and int(store[at[0]][-1, 0, 0, 0]) == (110 + 24) % 251

        gesture.clips(video, rows, tmp_path / "cache")
        assert len(asked) == 2
        video.write_bytes(b"another video")
        gesture.clips(video, rows, tmp_path / "cache")
        assert len(asked) == 3


RALLIES = [{"key": 1, "start": 2.0, "end": 8.0}]


def make(outputs, name: str, checked: list[int], contacts=None):
    """A match folder with its review's page (`checked` rallies checked), its actions.csv and its video."""
    match = outputs / "matches" / name
    (match / "review").mkdir(parents=True)
    contacts = contacts if contacts is not None else [{"rally": 0, "type": "serve", "t": 2.2}, {"rally": 0, "type": "dig", "t": 4.0}, {"rally": 0, "type": "fault", "t": 5.2}]
    (match / "review" / "data.js").write_text("window.MATCH = " + json.dumps({"rallies": RALLIES, "contacts": contacts}) + ";")
    (match / "identity_answers.json").write_text(json.dumps({"log": [{"id": "ok", "checked": checked}]}))
    (match / "actions.csv").write_text("frame,x,y,type,side,track\n")
    (outputs / f"{name}.mp4").write_bytes(b"video")
    (match / "source.json").write_text(json.dumps({"video": str(outputs / f"{name}.mp4"), "court": "court.json"}))
    return match


class TestLabels:
    def test_the_nearest_checked_touch_none_without_left_out_for_another_kind_or_out_of_the_rallies(self, tmp_path):
        found = gesture_training.truth(make(tmp_path, "a", [1]), FPS)
        contacts = [{"frame": 112}, {"frame": 205}, {"frame": 260}, {"frame": 600}, {"frame": 90}]

        assert gesture_training.labels(found, contacts, FPS).tolist() == [gesture.LABELS.index("serve"), gesture.LABELS.index("dig"), -1, -1, gesture.NONE]
        assert gesture_training.labels(found, [{"frame": 300}], FPS).tolist() == [gesture.NONE]

    def test_no_truth_while_a_rally_is_unchecked(self, tmp_path):
        assert gesture_training.truth(make(tmp_path, "a", []), FPS) is None


class TestDue:
    def test_two_matches_fully_checked_at_least(self, tmp_path):
        a = make(tmp_path, "a", [1])
        assert gesture_training.due(a) == []

        make(tmp_path, "b", [1])
        make(tmp_path, "c", [])
        assert [m.name for m, _ in gesture_training.due(a)] == ["a", "b"]

    def test_nothing_once_the_weights_know_them_or_refused_them(self, tmp_path):
        a, _ = make(tmp_path, "a", [1]), make(tmp_path, "b", [1])
        folder = tmp_path / gesture.WEIGHTS
        folder.mkdir(parents=True)
        signature = gesture_training.signature(gesture_training.sources(a))
        (folder / gesture_training.REFUSED).write_text(json.dumps({"matches": signature}))
        assert gesture_training.due(a) == []

        (folder / gesture_training.REFUSED).unlink()
        (folder / gesture.MODEL).touch()
        (folder / gesture_training.TRAINED).write_text(json.dumps({"matches": signature}))
        assert gesture_training.due(a) == []

        (folder / gesture_training.TRAINED).write_text(json.dumps({"matches": {**signature, "a": "old"}}))
        assert len(gesture_training.due(a)) == 2


class TestWeights:
    def test_beside_the_matches_else_the_held_out_ones_of_the_match(self, tmp_path, monkeypatch):
        match = tmp_path / "matches" / "a"
        assert gesture.weights(match) == tmp_path / gesture.WEIGHTS

        (tmp_path / "held" / "a").mkdir(parents=True)
        (tmp_path / "held" / "a" / gesture.MODEL).touch()
        monkeypatch.setenv(gesture.OVERRIDE, str(tmp_path / "held"))
        assert gesture.weights(match) == tmp_path / "held" / "a"
        assert gesture.weights(tmp_path / "matches" / "b") == tmp_path / "held"
