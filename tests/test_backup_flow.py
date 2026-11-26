import json
import os
import shutil
import stat
import threading
import time

import pytest

from volleyball_stats import backup, server, sync, sync_remote, transfer


# The server's commands are a shell's.
@pytest.mark.skipif(not shutil.which("sh"), reason="no sh")
class TestBackupFlow:
    """Two machines and the server as folders here, ssh run locally: rsync (or its stand-in), snapshot and claims."""

    @pytest.fixture(params=["rsync", "stand-in"])
    def place(self, request, tmp_path, monkeypatch):
        if request.param == "rsync" and not shutil.which("rsync"):
            pytest.skip("no rsync")
        if request.param == "stand-in":
            monkeypatch.setattr(transfer, "command", lambda: [transfer.sys.executable, transfer.__file__])
        root = tmp_path / "server"
        fake = tmp_path / "ssh"
        # The host, then the command: run here.
        fake.write_text('#!/bin/sh\nshift\nexec sh -c "$*"\n', encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(backup, "ROOT", str(root))
        monkeypatch.setattr(backup, "connection", lambda config: ("here", [str(fake)]))
        machine = {"name": "mac"}
        monkeypatch.setattr(sync, "machine", lambda: machine["name"])
        server_root = str(root)
        monkeypatch.setattr(sync, "remote", lambda config, op, match="-", base=0, force=False, root=None, timeout=60: sync_remote.run(server_root, op, match, machine["name"], base, force))
        hour = {"id": "2026-01-01T10"}
        monkeypatch.setattr(backup, "copy_id", lambda now=None: hour["id"])
        monkeypatch.setattr(backup, "MARGIN_GB", -1e9)
        return tmp_path, root, machine, hour

    @staticmethod
    def machine(place, name):
        outputs = place / name / "outputs"
        (outputs / "matches").mkdir(parents=True)
        files = {"server.json": {"upload": "here:/site/", "key": "k"}}
        for path, content in files.items():
            (outputs / path).write_text(json.dumps(content), encoding="utf-8")
        return outputs

    @staticmethod
    def match(outputs, name="m"):
        match = outputs / "matches" / name
        match.mkdir()
        (match / "source.json").write_text("{}", encoding="utf-8")
        (match / "publish.json").write_text(json.dumps({"upload": "here:/site/", "key": "k"}), encoding="utf-8")
        (match / "answers.json").write_text("first", encoding="utf-8")
        (match / "embeddings.npz").write_text("big and unchanged", encoding="utf-8")
        return match

    @staticmethod
    def write(path, text, at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        os.utime(path, (at, at))

    def test_two_machines_share_and_keep_every_copy(self, place):
        tmp_path, root, machine, hour = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        self.write(a / "courts" / "gym.json", "a's court", 1000)
        self.write(a / "feedback" / "feedback.log", "a1\n", 1000)
        self.write(a / "club" / "club.json", "old club", 1000)
        sync.push(m)
        assert (root / "2026-01-01T10" / "m" / "answers.json").read_text(encoding="utf-8") == "first"
        assert backup.state(a)["at"] and not backup.state(a)["error"]

        # The next hour: the copy starts as the one before, only the change goes up.
        hour["id"] = "2026-01-01T11"
        (m / "answers.json").write_text("second", encoding="utf-8")
        sync.push(m)
        before, after = root / "2026-01-01T10" / "m", root / "2026-01-01T11" / "m"
        assert (before / "answers.json").read_text(encoding="utf-8") == "first" and (after / "answers.json").read_text(encoding="utf-8") == "second"
        assert (before / "embeddings.npz").stat().st_ino == (after / "embeddings.npz").stat().st_ino

        # The other machine pulls it, adds its own court and report, edits the club: nothing of a's is lost.
        machine["name"] = "pc"
        b = self.machine(tmp_path, "b")
        sync.pull("m", b)
        assert (b / "matches" / "m" / "answers.json").read_text(encoding="utf-8") == "second" and (b / "courts" / "gym.json").exists()
        self.write(b / "courts" / "hall.json", "b's court", 2000)
        self.write(b / "feedback" / "feedback.log", "a1\nb1\n", 2000)
        self.write(b / "club" / "club.json", "new club", 2000)
        sync.keep_shared(b, sync.server(b))
        machine["name"] = "mac"
        self.write(a / "feedback" / "feedback.log", "a1\na2\n", 1500)
        sync.keep_shared(a, sync.server(a))
        assert sorted(p.name for p in (a / "courts").iterdir()) == ["gym.json", "hall.json"]
        assert (a / "club" / "club.json").read_text(encoding="utf-8") == "new club"
        assert (a / "feedback" / "feedback.log").read_text(encoding="utf-8").splitlines() == ["a1", "a2", "b1"]
        assert sorted(p.name for p in (root / "2026-01-01T11" / "courts").iterdir()) == ["gym.json", "hall.json"]

        # A shared change alone moves no match's version.
        version = sync_remote.read(str(root), "m")["version"]
        assert not sync.changed(m) and version == 2

        # The copies match this machine's; a damaged one is found.
        assert sync.verify(a) == []
        (root / "2026-01-01T11" / "m" / "answers.json").write_text("damaged", encoding="utf-8")
        assert sync.verify(a) and backup.state(a)["problems"]

        # A match brought back from an older copy: this machine's set aside, the match left to send.
        server.restore(a, "2026-01-01T10", "m")
        assert (m / "answers.json").read_text(encoding="utf-8") == "first" and sync.changed(m)
        assert any(p.name.startswith("backup-sync-") for p in m.iterdir())
        with pytest.raises(PermissionError):
            server.restore(a, "2026-01-01T10", "m", open_match="m")

        # Past the count kept, the oldest copies go, never a match's newest.
        sync.share_settings(sync.server(a), {"keep": 1})
        hour["id"] = "2026-01-01T12"
        sync.push(m)
        assert sorted(p.name for p in root.iterdir() if backup.COPY.fullmatch(p.name)) == ["2026-01-01T12"]
        assert (root / "2026-01-01T12" / "m" / "answers.json").read_text(encoding="utf-8") == "first"

    def test_two_processes_of_one_machine_send_a_match_one_after_the_other(self, place, monkeypatch):
        # 21 Nov: the review's timer and the app's "Sauvegarder maintenant" sent the same matches together.
        tmp_path, root, _, _ = place
        a = self.machine(tmp_path, "a")
        self.match(a)
        copy = backup.backup

        def slow(match):
            copy(match)
            time.sleep(0.3)

        monkeypatch.setattr(backup, "backup", slow)
        failed = []
        both = [threading.Thread(target=lambda: failed.extend(sync.push_all(a))) for _ in range(2)]
        for t in both:
            t.start()
        for t in both:
            t.join()
        assert failed == [] and sync_remote.read(str(root), "m")["version"] == 1 and not sync.changed(a / "matches" / "m")

    def test_a_match_changed_on_both_machines_waits_for_the_owner_not_failing_the_backup(self, place, monkeypatch, capsys):
        from volleyball_stats import app, jobs

        tmp_path, _, machine, _ = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        sync.push(m)
        machine["name"] = "pc"
        b = self.machine(tmp_path, "b")
        sync.pull("m", b)
        (b / "matches" / "m" / "answers.json").write_text("pc's", encoding="utf-8")
        sync.push(b / "matches" / "m")
        machine["name"] = "mac"
        (m / "answers.json").write_text("mac's", encoding="utf-8")
        assert sync.push_all(a) == []
        monkeypatch.setattr(app, "MATCHES", a / "matches")
        log = capsys.readouterr().out
        assert app.conflicts(log) == [{"name": "m", "title": None, "teams": None, "machine": "pc"}] and jobs.error_of(log) is None
        sync.keep(m)
        assert app.conflicts(log) == []

    def test_get_everything_brings_what_is_newer_and_asks_before_replacing_a_change_here(self, place, monkeypatch):
        from volleyball_stats import app, jobs

        tmp_path, _, machine, _ = place
        a = self.machine(tmp_path, "a")
        sync.push(self.match(a, "m"))
        sync.push(self.match(a, "n"))
        machine["name"] = "pc"
        b = self.machine(tmp_path, "b")
        assert sync.due(b) == [("m", False), ("n", False)]
        assert sync.pull_all(b) == [] and sync.due(b) == []
        (b / "matches" / "m" / "answers.json").write_text("pc's", encoding="utf-8")
        sync.push(b / "matches" / "m")
        machine["name"] = "mac"
        (a / "matches" / "m" / "answers.json").write_text("mac's", encoding="utf-8")
        assert sync.due(a) == [("m", True)]
        started = []
        monkeypatch.setattr(app, "MATCHES", a / "matches")
        monkeypatch.setattr(app, "OUTPUTS", a)
        monkeypatch.setattr(app, "server_state", lambda: {})
        monkeypatch.setattr(jobs, "start", lambda *args, **kwargs: started.append(args[1]))
        assert app.start_pull(False) == {"due": 1, "changed": [{"name": "m", "title": None, "teams": None}]} and not started
        assert app.start_pull(True)["due"] == 1 and started == ["pull"]
        assert sync.pull_all(a) == [] and (a / "matches" / "m" / "answers.json").read_text(encoding="utf-8") == "pc's"
        assert any(p.name.startswith("backup-sync-") for p in (a / "matches" / "m").iterdir())

    def test_the_site_tab_saved_unchanged_leaves_the_matches_unchanged(self, place):
        tmp_path, _, _, _ = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        sync.push(m)
        server.save(a, {"address": "root@here", "folder": "/site", "key": "k"})
        server.save(a, {"address": "root@here", "folder": "/site", "key": "k"})
        sync.push(m)
        before = (m / "publish.json").stat().st_mtime_ns
        server.save(a, {"address": "root@here", "folder": "/site", "key": "k"})
        assert (m / "publish.json").stat().st_mtime_ns == before and not sync.changed(m)

    def test_a_failed_copy_is_noted_for_the_app(self, place, monkeypatch):
        tmp_path, _, _, _ = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        monkeypatch.setattr(backup, "MARGIN_GB", 1e9)
        with pytest.raises(RuntimeError, match="free"):
            sync.push(m)
        assert "free" in backup.state(a)["error"]
        assert server.warning(a)["kind"] == "failed"
