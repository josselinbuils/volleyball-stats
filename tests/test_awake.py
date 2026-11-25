import json
import os
import sys
import time
from contextlib import contextmanager

from volleyball_stats import awake, jobs


def test_tells_the_battery_then_only_its_changes(monkeypatch):
    monkeypatch.setattr(awake, "holder", lambda: None)
    monkeypatch.setattr(awake, "in_wsl", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")
    states = iter([False, False, None, True, True, False])
    monkeypatch.setattr(awake, "on_battery", lambda: next(states, False))
    told = []
    with awake.held(told.append, check_s=0.01):
        time.sleep(0.3)
    assert told == [False, True, False]


def test_each_system_s_own_way(monkeypatch):
    monkeypatch.setattr(awake, "in_wsl", lambda: False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert awake.holder() == ["caffeinate", "-i", "-w", str(os.getpid())]
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(awake.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert awake.holder()[0] == "systemd-inhibit" and "--what=idle:sleep" in awake.holder()
    monkeypatch.setattr(awake, "in_wsl", lambda: True)
    assert awake.holder()[0] == "powershell.exe" and "SetThreadExecutionState" in awake.holder()[-1]
    monkeypatch.setattr(awake.shutil, "which", lambda name: None)
    assert awake.holder() is None
    monkeypatch.setattr(sys, "platform", "win32")
    assert awake.holder() is None


def test_a_holder_that_cannot_start_leaves_the_work_running(monkeypatch):
    monkeypatch.setattr(awake, "holder", lambda: ["no-such-command-volleyball-stats"])
    monkeypatch.setattr(awake, "in_wsl", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(awake, "on_battery", lambda: None)
    done = []
    with awake.held():
        done.append(1)
    assert done == [1]


def test_the_holder_ends_with_the_block(monkeypatch, tmp_path):
    monkeypatch.setattr(awake, "holder", lambda: [sys.executable, "-c", "import sys; sys.stdin.read()"])
    monkeypatch.setattr(awake, "in_wsl", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(awake, "on_battery", lambda: None)
    started = []
    real = awake.subprocess.Popen
    monkeypatch.setattr(awake.subprocess, "Popen", lambda *a, **k: started.append(real(*a, **k)) or started[-1])
    with awake.held():
        assert started[0].poll() is None
    assert started[0].poll() is not None


def test_a_job_records_the_battery_while_it_runs(monkeypatch, tmp_path):
    @contextmanager
    def held(battery):
        battery(True)
        yield

    monkeypatch.setattr(awake, "held", held)
    record = tmp_path / "jobs" / "m.json"
    record.parent.mkdir()
    record.write_text(json.dumps({"id": "m", "kind": "pipeline", "steps": [{"name": "one", "args": ["json.tool", "--help"]}], "started": time.time()}))
    jobs.run(record)
    job = json.loads(record.read_text())
    assert job["battery"] is True and job["step"] is None and "ended" in job
