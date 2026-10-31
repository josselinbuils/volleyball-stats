import json

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
