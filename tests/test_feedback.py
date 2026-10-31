import json

from volleyball_stats.feedback import read


class TestRead:
    def test_reads_the_reports_and_skips_what_is_not_one(self, tmp_path):
        report = {"match": "first_match", "time": 61.5, "rally": 3, "kind": "player", "comment": "C'est Maeva"}
        lines = [json.dumps({"received": "2026-10-31T15:00:00+00:00", "report": json.dumps(report)}), "not json", json.dumps({"received": "x", "report": "{cut"})]
        (tmp_path / "feedback.log").write_text("\n".join(lines) + "\n")

        assert read(tmp_path / "feedback.log") == [{**report, "received": "2026-10-31T15:00:00+00:00"}]
