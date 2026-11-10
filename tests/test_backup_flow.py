import json
import os
import stat

import pytest

from volleyball_stats import backup, server, sync, sync_remote


class TestBackupFlow:
    """Two machines and the server as folders here, ssh run locally: the real rsync, snapshot and claims."""

    @pytest.fixture
    def place(self, tmp_path, monkeypatch):
        root = tmp_path / "server"
        fake = tmp_path / "ssh"
        # The host, then the command: run here.
        fake.write_text('#!/bin/sh\nshift\nexec sh -c "$*"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(backup, "ROOT", str(root))
        monkeypatch.setattr(backup, "connection", lambda config: ("here", [str(fake)]))
        machine = {"name": "mac"}
        monkeypatch.setattr(sync, "machine", lambda: machine["name"])
        server_root = str(root)
        monkeypatch.setattr(sync, "remote", lambda config, op, match="-", base=0, force=False, root=None, timeout=60: sync_remote.run(server_root, op, match, machine["name"], base, force))
        hour = {"id": "2026-01-01T10"}
        monkeypatch.setattr(backup, "copy_id", lambda now=None: hour["id"])
        monkeypatch.setattr(backup, "MIN_FREE_GB", 0)
        return tmp_path, root, machine, hour

    @staticmethod
    def machine(place, name):
        outputs = place / name / "outputs"
        (outputs / "matches").mkdir(parents=True)
        files = {"server.json": {"upload": "here:/site/", "key": "k"}}
        for path, content in files.items():
            (outputs / path).write_text(json.dumps(content))
        return outputs

    @staticmethod
    def match(outputs, name="m"):
        match = outputs / "matches" / name
        match.mkdir()
        (match / "source.json").write_text("{}")
        (match / "publish.json").write_text(json.dumps({"upload": "here:/site/", "key": "k"}))
        (match / "answers.json").write_text("first")
        (match / "embeddings.npz").write_text("big and unchanged")
        return match

    @staticmethod
    def write(path, text, at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        os.utime(path, (at, at))

    def test_two_machines_share_and_keep_every_copy(self, place):
        tmp_path, root, machine, hour = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        self.write(a / "courts" / "gym.json", "a's court", 1000)
        self.write(a / "feedback" / "feedback.log", "a1\n", 1000)
        self.write(a / "club" / "club.json", "old club", 1000)
        sync.push(m)
        assert (root / "2026-01-01T10" / "m" / "answers.json").read_text() == "first"
        assert backup.state(a)["at"] and not backup.state(a)["error"]

        # The next hour: the copy starts as the one before, only the change goes up.
        hour["id"] = "2026-01-01T11"
        (m / "answers.json").write_text("second")
        sync.push(m)
        before, after = root / "2026-01-01T10" / "m", root / "2026-01-01T11" / "m"
        assert (before / "answers.json").read_text() == "first" and (after / "answers.json").read_text() == "second"
        assert (before / "embeddings.npz").stat().st_ino == (after / "embeddings.npz").stat().st_ino

        # The other machine pulls it, adds its own court and report, edits the club: nothing of a's is lost.
        machine["name"] = "pc"
        b = self.machine(tmp_path, "b")
        sync.pull("m", b)
        assert (b / "matches" / "m" / "answers.json").read_text() == "second" and (b / "courts" / "gym.json").exists()
        self.write(b / "courts" / "hall.json", "b's court", 2000)
        self.write(b / "feedback" / "feedback.log", "a1\nb1\n", 2000)
        self.write(b / "club" / "club.json", "new club", 2000)
        sync.keep_shared(b, sync.server(b))
        machine["name"] = "mac"
        self.write(a / "feedback" / "feedback.log", "a1\na2\n", 1500)
        sync.keep_shared(a, sync.server(a))
        assert sorted(p.name for p in (a / "courts").iterdir()) == ["gym.json", "hall.json"]
        assert (a / "club" / "club.json").read_text() == "new club"
        assert (a / "feedback" / "feedback.log").read_text().splitlines() == ["a1", "a2", "b1"]
        assert sorted(p.name for p in (root / "2026-01-01T11" / "courts").iterdir()) == ["gym.json", "hall.json"]

        # A shared change alone moves no match's version.
        version = sync_remote.read(str(root), "m")["version"]
        assert not sync.changed(m) and version == 2

        # The copies match this machine's; a damaged one is found.
        assert sync.verify(a) == []
        (root / "2026-01-01T11" / "m" / "answers.json").write_text("damaged")
        assert sync.verify(a) and backup.state(a)["problems"]

        # A match brought back from an older copy: this machine's set aside, the match left to send.
        server.restore(a, "2026-01-01T10", "m")
        assert (m / "answers.json").read_text() == "first" and sync.changed(m)
        assert any(p.name.startswith("backup-sync-") for p in m.iterdir())
        with pytest.raises(PermissionError):
            server.restore(a, "2026-01-01T10", "m", open_match="m")

        # Past the count kept, the oldest copies go, never a match's newest.
        sync.share_settings(sync.server(a), {"keep": 1})
        hour["id"] = "2026-01-01T12"
        sync.push(m)
        assert sorted(p.name for p in root.iterdir() if backup.COPY.fullmatch(p.name)) == ["2026-01-01T12"]
        assert (root / "2026-01-01T12" / "m" / "answers.json").read_text() == "first"

    def test_a_failed_copy_is_noted_for_the_app(self, place, monkeypatch):
        tmp_path, _, _, _ = place
        a = self.machine(tmp_path, "a")
        m = self.match(a)
        monkeypatch.setattr(backup, "MIN_FREE_GB", 10**9)
        with pytest.raises(RuntimeError, match="free"):
            sync.push(m)
        assert "free" in backup.state(a)["error"]
        assert server.warning(a)["kind"] == "failed"
