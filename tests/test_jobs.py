import json
import os
import subprocess
import sys
import time

import pytest

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

    def test_reads_the_stage_s_share_and_the_time_left_a_command_tells(self):
        found = jobs.told("::stage wrists\n::progress 0.6200 part=0.400 left=1234\n")
        assert found == {"stage": "wrists", "progress": 0.62, "part": 0.4, "toldLeft": 1234.0}
        # A new stage forgets the last one's share; an older command's bare share reads as before.
        assert jobs.told("::progress 0.5 part=0.9 left=10\n::stage teams\n") == {"stage": "teams", "progress": None}
        assert jobs.told("::progress 0.25\n") == {"stage": None, "progress": 0.25}

    def test_reads_the_last_line_shown(self, tmp_path):
        log = tmp_path / "a.log"
        log.write_text("start\nframe=1 time=00:00:01\rframe=2 time=00:00:02\nerror: no court\n", encoding="utf-8")
        assert jobs.tail(log).split("\n")[1] == "frame=2 time=00:00:02"
        assert jobs.error_of(jobs.tail(log)) == "error: no court"
        # A log written on Windows.
        log.write_bytes(b"start\r\nframe=1\rframe=2\r\nerror: no court\r\n")
        assert jobs.tail(log).split("\n")[1] == "frame=2" and jobs.error_of(jobs.tail(log)) == "error: no court"

    def test_refuses_ids_out_of_its_folder(self, tmp_path):
        for job_id in ("../roster", "a/b", "..", ""):
            with pytest.raises(ValueError):
                jobs.forget(tmp_path, job_id)

    def test_a_number_given_to_another_process_is_not_the_job(self, tmp_path):
        import os

        assert jobs.alive(os.getpid(), jobs.started_at(os.getpid()))
        assert not jobs.alive(os.getpid(), "Mon Jan  1 00:00:00 2001")

    def test_a_clock_set_again_keeps_the_process_its_own(self, monkeypatch):
        # WSL2 after a resync: `ps` tells a start 9 s off the one recorded.
        monkeypatch.setattr(jobs, "started_at", lambda pid: "Fri Nov 13 11:04:46 2026")
        assert jobs.alive(os.getpid(), "Fri Nov 13 11:04:55 2026")
        assert not jobs.alive(os.getpid(), "Fri Nov 13 09:04:55 2026")

    def test_a_process_known_by_its_key_is_that_one_whatever_the_clock(self, monkeypatch):
        key = jobs.process_key(os.getpid())
        if key is None:
            pytest.skip("no /proc here")
        monkeypatch.setattr(jobs, "started_at", lambda pid: "Mon Jan  1 00:00:00 2001")
        assert jobs.alive(os.getpid(), "Fri Nov 13 11:04:55 2026", key)
        assert not jobs.alive(os.getpid(), None, key.rsplit(":", 1)[0] + ":1")

    def test_a_dead_runner_is_interrupted(self, tmp_path):
        folder = jobs.folder(tmp_path)
        folder.mkdir()
        (folder / "x.json").write_text(json.dumps({"id": "x", "kind": "pipeline", "steps": [], "started": 1.0, "pid": 999999999, "step": "pipeline"}), encoding="utf-8")
        found = jobs.state(tmp_path)[0]
        assert not found["running"] and found["failed"] == "pipeline" and found["error"] == "interrupted"


class TestStages:
    def test_the_share_done_counts_each_match_as_it_last_took(self, tmp_path):
        (tmp_path / "took.json").write_text(json.dumps({"mirror": 10.0, "match:long": 80.0, "upload": 10.0}), encoding="utf-8")
        stages = jobs.Stages(tmp_path / "took.json", ["mirror", "match:long", "match:new", "upload"], {"match": 15.0}, told=False)
        stages.done, stages.key = 90.0, "match:new"
        # 10 + 80 done of 10 + 80 + 15 (a match not measured yet) + 10.
        assert stages.share() == pytest.approx(90.0 / 115.0, abs=0.01)

    def test_the_share_moves_only_with_counted_work_and_the_time_left_from_its_pace(self, tmp_path, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(jobs.time, "time", lambda: clock[0])
        # By second of a video 100 s long: tracking 2 s, rallies 0.5 s, page 1 s.
        stages = jobs.Stages(None, ["tracking", "rallies", "page"], {"tracking": 2.0, "rallies": 0.5, "page": 1.0}, told=False, scale=100.0)
        stages.start("tracking")
        clock[0] += 50.0
        # Nothing counted yet: the bar holds, whatever the time.
        assert (stages.part(), stages.share()) == (0.0, 0.0)
        assert stages.line() == f"{jobs.PROGRESS}0.0000 part= left=300"
        tick = stages.counter(8)
        tick(2)
        # A quarter of the tracking in 50 s: 150 s more, then rallies and page as expected.
        assert (stages.part(), stages.left()) == (0.25, 150.0 + 50.0 + 100.0)
        assert stages.share() == pytest.approx(50.0 / 350.0)
        stages.start("rallies")
        clock[0] += 25.0
        # A stage that counts nothing holds, its time left from its last duration.
        assert (stages.part(), stages.left()) == (0.0, 25.0 + 100.0)
        clock[0] += 100.0
        assert stages.part() == 0.0 and stages.left() == 100.0
        assert stages.share() == pytest.approx(200.0 / 350.0)
        assert " part= left=100" in stages.line()

    def test_tells_which_match_of_how_many(self, tmp_path, capsys):
        stages = jobs.Stages(tmp_path / "took.json", ["match:a", "match:b", "shared"], {}, told=True)
        for key in ("match:a", "match:b", "shared", None):
            stages.start(key)
        told = [line for line in capsys.readouterr().out.splitlines() if line.startswith(jobs.STAGE)]
        assert told == ["::stage match 1/2", "::stage match 2/2", "::stage shared"]
        assert set(json.loads((tmp_path / "took.json").read_text(encoding="utf-8"))) == {"match:a", "match:b", "shared"}


    def test_a_stage_started_again_counts_from_where_it_was_its_pace_and_duration_its_own(self, tmp_path, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(jobs.time, "time", lambda: clock[0])
        stages = jobs.Stages(tmp_path / "took.json", ["tracking", "page"], {"tracking": 2.0, "page": 1.0}, told=False, scale=100.0)
        stages.start("tracking")
        stages.resumed(0.5)
        # Half the tracking kept: the bar from there, 100 s of it left as expected.
        assert stages.share() == pytest.approx(100.0 / 300.0) and stages.left() == 100.0 + 100.0
        clock[0] += 30.0
        stages.share_of_stage(0.6)
        # A tenth in 30 s: 120 s more, not the pace of half in 30 s.
        assert stages.left() == pytest.approx(120.0 + 100.0)
        clock[0] += 120.0
        stages.start("page")
        # 150 s for half the tracking: 300 s for a whole one, 3 s per second of video.
        assert json.loads((tmp_path / "took.json").read_text(encoding="utf-8"))["tracking"] == pytest.approx(3.0)

    def test_a_run_reusing_an_earlier_ones_work_keeps_no_durations(self, tmp_path):
        (tmp_path / "took.json").write_text(json.dumps({"identity": 0.4}), encoding="utf-8")
        stages = jobs.Stages(tmp_path / "took.json", ["identity"], {}, told=False, keep=False)
        for key in ("identity", None):
            stages.start(key)
        assert json.loads((tmp_path / "took.json").read_text(encoding="utf-8")) == {"identity": 0.4}
        assert stages.expected("identity") == 0.4


class TestCounting:
    def test_a_step_cut_in_parts_tells_its_share_the_parts_before_done(self):
        told = []
        part = jobs.parts(told.append, {"read": 1.0, "skipped": 0.0, "work": 3.0})
        part("read")(0.5)
        part("work")(0.5)
        part("work")(2.0)
        assert told == [0.125, 0.625, 1.0]

    def test_a_loop_tells_its_share_now_and_then_and_at_its_end(self):
        told = []
        seen = jobs.every(250, told.append)
        for k in range(250):
            seen(k)
        assert told[0] == 2 / 250 and told[-1] == 1.0 and len(told) == 125

    def test_follows_a_child_s_shares_and_passes_its_other_lines(self, capsys):
        told = []
        jobs.follow([sys.executable, "-c", "from volleyball_stats import jobs; print('hello'); jobs.tell(0.25); jobs.tell(1)"], told.append)
        assert told == [0.25, 1.0] and capsys.readouterr().out == "hello\n"
        with pytest.raises(subprocess.CalledProcessError):
            jobs.follow([sys.executable, "-c", "raise SystemExit(3)"], told.append)

    def test_tells_ffmpeg_s_share_from_the_time_it_wrote(self, tmp_path):
        told = []
        run = jobs.ffmpeg(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=64x64:rate=10", "-y", str(tmp_path / "out.mp4")], 2.0, told.append)
        assert run.returncode == 0 and told and told[-1] == pytest.approx(1.0, abs=0.1)
        failed = jobs.ffmpeg(["ffmpeg", "-v", "error", "-i", str(tmp_path / "missing.mp4"), str(tmp_path / "x.mp4")], 2.0, told.append)
        assert failed.returncode and "missing.mp4" in failed.stderr


def test_tell_in_a_terminal_writes_each_percentage_once_over_the_last(monkeypatch, capsys):
    monkeypatch.setattr(jobs.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(jobs, "_told", [])
    for share in (0.0, 0.001, 0.5, 0.504, 1.0):
        jobs.tell(share)
    assert capsys.readouterr().out == "\r0%\r50%\r100%\n"
