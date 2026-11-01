import json
from pathlib import Path

from volleyball_stats.feedback import read


class TestRead:
    def test_reads_the_reports_and_skips_what_is_not_one(self, tmp_path):
        report = {"match": "first_match", "time": 61.5, "rally": 3, "kind": "player", "comment": "C'est Maeva"}
        lines = [json.dumps({"received": "2026-10-31T15:00:00+00:00", "report": json.dumps(report)}), "not json", json.dumps({"received": "x", "report": "{cut"})]
        (tmp_path / "feedback.log").write_text("\n".join(lines) + "\n")

        assert read(tmp_path / "feedback.log") == [{**report, "received": "2026-10-31T15:00:00+00:00"}]

    def test_a_flag_s_details_sent_later_complete_it(self, tmp_path):
        flag = {"id": "a1", "match": "m", "time": 61.5, "kind": "flag", "comment": ""}
        details = {**flag, "kind": "player", "comment": "C'est Maeva"}
        other = {"id": "b2", "match": "m", "time": 90.0, "kind": "flag", "comment": ""}
        lines = [json.dumps({"received": f"t{k}", "report": json.dumps(r)}) for k, r in enumerate((flag, other, details))]
        (tmp_path / "feedback.log").write_text("\n".join(lines) + "\n")

        assert read(tmp_path / "feedback.log") == [{**details, "received": "t0"}, {**other, "received": "t1"}]


class TestFetch:
    def test_keeps_a_dated_copy_then_empties_the_online_log(self, tmp_path, monkeypatch):
        from volleyball_stats import feedback

        calls = []

        def run(cmd, **_):
            calls.append(cmd)
            if cmd[0] == "scp":
                Path(cmd[-1]).write_text('{"report": "{}"}\n')

        monkeypatch.setattr(feedback.subprocess, "run", run)
        got = feedback.fetch(tmp_path, "root@host:/srv/vbs/site/", "~/key")

        assert got is not None and got.parent == tmp_path and got.name.startswith("feedback-")
        assert calls[0][-2] == "root@host:/srv/vbs/feedback/feedback.log"
        assert calls[1][-2:] == ["root@host", ": > /srv/vbs/feedback/feedback.log"]

    def test_an_empty_log_leaves_nothing(self, tmp_path, monkeypatch):
        from volleyball_stats import feedback

        calls = []

        def run(cmd, **_):
            calls.append(cmd)
            if cmd[0] == "scp":
                Path(cmd[-1]).write_text("")

        monkeypatch.setattr(feedback.subprocess, "run", run)

        assert feedback.fetch(tmp_path, "root@host:/srv/vbs/site/", "~/key") is None
        assert len(calls) == 1 and not list(tmp_path.iterdir())
