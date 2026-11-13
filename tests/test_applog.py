import io
import json
import sys

from volleyball_stats import app, applog


def test_output_kept_and_served(tmp_path, monkeypatch):
    log = tmp_path / "app.log"
    log.write_text("x" * 50 + "\n" + "old\n")
    monkeypatch.setattr(applog, "MAX_BYTES", 20)
    monkeypatch.setattr(applog, "KEEP_BYTES", 10)
    shown = io.StringIO()
    monkeypatch.setattr(sys, "stdout", shown)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    applog.start(log)
    print("Traceback: boom")
    applog.start(log)  # once only
    assert shown.getvalue() == "Traceback: boom\n"
    text = log.read_text()
    # Trimmed to its last whole lines, then appended to.
    assert text.startswith("old\n") and text.endswith("Traceback: boom\n") and text.count("---") == 2
    monkeypatch.setattr(app, "LOG", log)
    assert "boom" in json.loads(app.handle("GET", "/app/log", "", {}, list)[0])["text"]


def test_no_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    applog.start(tmp_path / "app.log")
    print("still kept", file=sys.stderr)
    assert "still kept" in (tmp_path / "app.log").read_text()
