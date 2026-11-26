import json

from volleyball_stats import doctor, estimate, gesture, playing


def test_a_new_machine_has_no_time_until_it_is_measured(tmp_path):
    assert estimate.factor(tmp_path) is None and estimate.stages(tmp_path) is None
    assert doctor.speed(tmp_path) == {"id": "speed", "status": "ok", "hour": None}


def test_the_measure_scales_the_reference(tmp_path):
    (tmp_path / estimate.SPEED).write_text(json.dumps({"frame_s": 2 * estimate.REFERENCE_FRAME_S}))
    found = estimate.stages(tmp_path)
    assert found == {k: 2 * v for k, v in estimate.REFERENCE.items()}
    assert doctor.speed(tmp_path)["hour"] == 2 * 3600 * sum(estimate.REFERENCE.values())


def test_a_runs_timings_come_first_and_scale_the_stages_it_did_not_run(tmp_path):
    (tmp_path / estimate.SPEED).write_text(json.dumps({"frame_s": 9.0}))
    (tmp_path / estimate.TIMINGS).write_text(json.dumps({"tracking": 3 * estimate.REFERENCE["tracking"], "jerseys": 0.5}))
    found = estimate.stages(tmp_path)
    assert estimate.factor(tmp_path) == 3
    assert found["jerseys"] == 0.5 and found["identity"] == 3 * estimate.REFERENCE["identity"]


def test_counts_only_the_stages_that_will_run(tmp_path, monkeypatch):
    (tmp_path / estimate.SPEED).write_text(json.dumps({"frame_s": estimate.REFERENCE_FRAME_S}))
    monkeypatch.setattr(playing, "wanted", lambda video, out: False)
    monkeypatch.setattr(gesture, "wanted", lambda video, out: True)
    assert "play" not in estimate.planned(tmp_path / "v.mp4", tmp_path) and "gesture" in estimate.planned(tmp_path / "v.mp4", tmp_path)
    per_s = sum(v for k, v in estimate.REFERENCE.items() if k != "play")
    assert abs(estimate.seconds(tmp_path, tmp_path / "v.mp4", tmp_path, 100.0) - 100 * per_s) < 1e-9


def test_too_slow_a_machine_is_warned(tmp_path):
    (tmp_path / estimate.SPEED).write_text(json.dumps({"frame_s": 20 * estimate.REFERENCE_FRAME_S}))
    assert doctor.speed(tmp_path)["status"] == "warn"


def test_a_stopped_run_counts_only_the_tracking_left(tmp_path, monkeypatch):
    (tmp_path / estimate.SPEED).write_text(json.dumps({"frame_s": estimate.REFERENCE_FRAME_S}))
    monkeypatch.setattr(playing, "wanted", lambda video, out: True)
    monkeypatch.setattr(gesture, "wanted", lambda video, out: True)
    whole = estimate.seconds(tmp_path, tmp_path / "v.mp4", tmp_path, 100.0)
    assert abs(whole - estimate.seconds(tmp_path, tmp_path / "v.mp4", tmp_path, 100.0, 0.25) - 25 * estimate.REFERENCE["tracking"]) < 1e-9
