import json
import time

from volleyball_stats import jobs


class TestJobs:
    @staticmethod
    def wait(outputs, job_id):
        for _ in range(100):
            found = {j["id"]: j for j in jobs.state(outputs)}[job_id]
            if not found["running"]:
                return found
            time.sleep(0.1)
        raise AssertionError("still running")

    def test_runs_the_steps_in_turn_until_one_fails(self, tmp_path):
        jobs.start(tmp_path, "ok", "court", [("one", ["json.tool", "--help"]), ("two", ["json.tool", "--help"])])
        done = self.wait(tmp_path, "ok")
        assert "failed" not in done and done["step"] is None
        jobs.start(tmp_path, "ko", "court", [("one", ["json.tool", str(tmp_path / "none.json")]), ("two", ["json.tool", "--help"])])
        failed = self.wait(tmp_path, "ko")
        assert failed["failed"] == "one" and failed["error"]

    def test_tells_progress_and_stage(self):
        assert jobs.progress("::stage tracking\n::progress 0.25\n") == (0.25, "tracking")
        assert jobs.progress("::progress 0.9\n::stage rallies\n") == (None, "rallies")
        assert jobs.progress("frame=1 time=00:01:30.00 bitrate", total_s=180) == (0.5, None)

    def test_reads_the_last_line_shown(self, tmp_path):
        log = tmp_path / "a.log"
        log.write_text("start\nframe=1 time=00:00:01\rframe=2 time=00:00:02\nerror: no court\n")
        assert jobs.tail(log).split("\n")[1] == "frame=2 time=00:00:02"
        assert jobs.error_of(jobs.tail(log)) == "error: no court"

    def test_a_dead_runner_is_interrupted(self, tmp_path):
        folder = jobs.folder(tmp_path)
        folder.mkdir()
        (folder / "x.json").write_text(json.dumps({"id": "x", "kind": "pipeline", "steps": [], "started": 1.0, "pid": 999999999, "step": "pipeline"}))
        found = jobs.state(tmp_path)[0]
        assert not found["running"] and found["failed"] == "pipeline" and found["error"] == "interrupted"
