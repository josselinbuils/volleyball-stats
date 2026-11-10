import json

import pytest

from volleyball_stats import backup, sync, sync_remote


class TestRemote:
    @staticmethod
    def copy(root, day="2026-11-08"):
        (root / day / "m").mkdir(parents=True, exist_ok=True)
        (root / day / "m" / "source.json").write_text("{}")

    def test_any_machine_sends_a_copy_from_the_servers_version_which_moves_it(self, tmp_path):
        root = str(tmp_path)

        assert sync_remote.run(root, "begin", "m", "mac", 0)["ok"]
        assert sync_remote.run(root, "commit", "m", "mac", 0)["version"] == 1
        # From the old version: the Mac's copy would be lost.
        assert not sync_remote.run(root, "begin", "m", "pc", 0)["ok"]
        assert sync_remote.run(root, "begin", "m", "pc", 1)["ok"]
        done = sync_remote.run(root, "commit", "m", "pc", 1)
        assert done["version"] == 2 and done["pushedBy"] == "pc"

    def test_one_machine_sends_at_a_time(self, tmp_path):
        root = str(tmp_path)
        sync_remote.run(root, "begin", "m", "mac", 0)

        refused = sync_remote.run(root, "begin", "m", "pc", 0)

        assert not refused["ok"] and refused["busy"]
        assert sync_remote.run(root, "status", "m", "pc")["busy"] and not sync_remote.run(root, "status", "m", "mac")["busy"]

    def test_keeping_this_machines_sets_the_servers_copy_aside(self, tmp_path):
        root = str(tmp_path)
        self.copy(tmp_path)
        sync_remote.run(root, "begin", "m", "mac", 0)
        sync_remote.run(root, "commit", "m", "mac", 0)

        forced = sync_remote.run(root, "begin", "m", "pc", 0, force=True)

        assert forced["ok"]
        assert [p.name for p in (tmp_path / "aside").glob("*-v1/m/source.json")] == ["source.json"]
        assert sync_remote.run(root, "commit", "m", "pc", 0)["version"] == 2

    def test_reads_the_records_of_the_old_claims(self, tmp_path):
        (tmp_path / "claims").mkdir()
        (tmp_path / "claims" / "m.json").write_text(json.dumps({"owner": "mac", "since": "x", "version": 3, "pushed": None, "pushedBy": "mac"}))

        found = sync_remote.run(str(tmp_path), "status", "m", "pc")

        assert found["version"] == 3 and "owner" not in found and found["ok"] and not found["busy"]

    def test_lists_each_match_by_its_newest_copy(self, tmp_path):
        for day in ("2026-11-01", "2026-11-03"):
            (tmp_path / day / "m").mkdir(parents=True)
            (tmp_path / day / "m" / "source.json").write_text("{}")
        (tmp_path / "2026-11-01" / "old").mkdir()
        (tmp_path / "2026-11-01" / "old" / "source.json").write_text("{}")
        (tmp_path / "2026-11-03" / "courts").mkdir()

        found = sync_remote.run(str(tmp_path), "list", "-", "mac")["matches"]

        assert {k: v["day"] for k, v in found.items()} == {"m": "2026-11-03", "old": "2026-11-01"}
        assert found["m"]["version"] == 0 and found["m"]["pushedBy"] is None


class TestMerged:
    @staticmethod
    def player(name, team, jersey, **vectors):
        return {"name": name, "team": team, "jersey": jersey, "vectors": vectors}

    def test_each_match_from_the_machine_whose_copy_is_not_behind(self):
        mine = [self.player("Ana", "A", None, m1=[1], m2=[2])]
        theirs = [self.player("Ana", "A", 7, m1=[9], m2=[8]), self.player("Bob", "A", None, m2=[5], m3=[6])]

        out = sync.merged(mine, theirs, lambda match: match == "m1")

        assert out == [self.player("Ana", "A", 7, m1=[1], m2=[8]), self.player("Bob", "A", None, m2=[5], m3=[6])]

    def test_a_match_only_here_stays(self):
        out = sync.merged([self.player("Ana", "A", 4, m1=[1])], [], lambda match: False)

        assert out == [self.player("Ana", "A", 4, m1=[1])]

    def test_a_player_renamed_on_the_holding_machine_leaves_the_old_name(self):
        out = sync.merged([self.player("Anna", "A", None, m1=[1])], [self.player("Ana", "A", None, m1=[1])], lambda match: True)

        assert [p["name"] for p in out] == ["Anna"]


class TestRelativeCopies:
    def test_the_other_machines_paths_become_the_projects(self, tmp_path):
        (tmp_path / "publish.json").write_text(json.dumps({"light": "/home/pc/volleyball-stats/data/matches/m/reencoded/a.mp4", "small": str(tmp_path / "publish.json"), "key": "~/.ssh/k"}))

        sync.relative_copies(tmp_path)

        given = json.loads((tmp_path / "publish.json").read_text())
        assert given == {"light": "data/matches/m/reencoded/a.mp4", "small": str(tmp_path / "publish.json"), "key": "~/.ssh/k"}


class TestChanged:
    def test_a_file_changed_since_the_last_sync(self, tmp_path):
        match = tmp_path / "m"
        match.mkdir()
        (match / "answers.json").write_text("a")
        assert sync.changed(match)

        sync.remember(match, 3, backup.signature([match]))

        assert not sync.changed(match) and sync.local(match)["version"] == 3
        (match / "answers.json").write_text("bb")
        assert sync.changed(match)


class TestPush:
    @staticmethod
    def setup(tmp_path, monkeypatch, answers: dict):
        match = tmp_path / "outputs" / "matches" / "m"
        match.mkdir(parents=True)
        (match / "publish.json").write_text(json.dumps({"upload": "root@host:/site/", "key": "k"}))
        calls = []

        def remote(config, op, match="-", base=0, force=False, timeout=60):
            calls.append((op, base, force))
            return {"version": 2, "pushed": "2026-11-08T14:02:00+0100", "pushedBy": "mac", "pushing": None, "busy": False, **answers[op]}

        monkeypatch.setattr(sync, "remote", remote)
        monkeypatch.setattr(sync, "merge_roster", lambda *args, **kwargs: None)
        monkeypatch.setattr(sync.backup, "backup", lambda m: calls.append(("backup", None, None)))
        return match, calls

    def test_refused_when_another_machine_sent_a_newer_copy(self, tmp_path, monkeypatch):
        match, calls = self.setup(tmp_path, monkeypatch, {"begin": {"ok": False}})

        with pytest.raises(sync.Conflict) as error:
            sync.push(match)

        assert calls == [("begin", 0, False)] and error.value.claim == {"machine": "mac", "at": "14:02", "changed": True}

    def test_waits_while_another_machine_sends_it(self, tmp_path, monkeypatch):
        match, _ = self.setup(tmp_path, monkeypatch, {"begin": {"ok": False, "busy": True, "pushing": {"machine": "mac", "at": 0}}})

        with pytest.raises(RuntimeError, match="mac is sending it"):
            sync.push(match)

    def test_copies_then_takes_the_new_version(self, tmp_path, monkeypatch):
        match, calls = self.setup(tmp_path, monkeypatch, {"begin": {"ok": True, "version": 0}, "commit": {"ok": True, "version": 1}})

        sync.push(match)

        assert calls == [("begin", 0, False), ("backup", None, None), ("commit", 0, False)] and sync.local(match)["version"] == 1

    def test_keeping_this_machines_sends_it_over_the_newer_one(self, tmp_path, monkeypatch):
        match, calls = self.setup(tmp_path, monkeypatch, {"begin": {"ok": True}, "commit": {"ok": True, "version": 3}})

        sync.keep(match)

        assert calls[0] == ("begin", 0, True) and sync.local(match)["version"] == 3


class TestCheck:
    @staticmethod
    def setup(tmp_path, monkeypatch, version: int, here: int, changed: bool):
        match = tmp_path / "outputs" / "matches" / "m"
        match.mkdir(parents=True)
        (match / "publish.json").write_text(json.dumps({"upload": "root@host:/site/", "key": "k"}))
        sync.remember(match, here, backup.signature([match]))
        if changed:
            (match / "answers.json").write_text("new")
        pulled = []
        monkeypatch.setattr(sync, "remote", lambda *a, **k: {"version": version, "day": "2026-11-08", "pushed": "2026-11-08T14:02:00+0100", "pushedBy": "mac", "ok": True, "busy": False})
        monkeypatch.setattr(sync, "pull", lambda name, outputs: pulled.append(name))
        return match, pulled

    def test_brings_the_newer_copy_when_nothing_changed_here(self, tmp_path, monkeypatch):
        match, pulled = self.setup(tmp_path, monkeypatch, version=3, here=2, changed=False)

        assert sync.check(match) is None and pulled == ["m"]

    def test_asks_which_to_keep_when_both_changed(self, tmp_path, monkeypatch):
        match, pulled = self.setup(tmp_path, monkeypatch, version=3, here=2, changed=True)

        assert sync.check(match) == {"machine": "mac", "at": "14:02", "changed": True} and pulled == []

    def test_nothing_when_this_copy_is_the_servers(self, tmp_path, monkeypatch):
        match, pulled = self.setup(tmp_path, monkeypatch, version=2, here=2, changed=True)

        assert sync.check(match) is None and pulled == []


class TestAuto:
    def test_off_until_this_machine_chooses_it(self, tmp_path):
        assert not sync.auto(tmp_path)
        sync.set_auto(tmp_path, True)
        assert sync.auto(tmp_path)
        sync.set_auto(tmp_path, False)
        assert not sync.auto(tmp_path)

    def test_a_machine_keeps_its_matches_on_the_server_once_it_chose_to(self, tmp_path):
        (tmp_path / "matches" / "m").mkdir(parents=True)
        assert not sync.active(tmp_path)
        (tmp_path / "matches" / "m" / sync.STATE).write_text("{}")
        assert sync.active(tmp_path)
        (tmp_path / "matches" / "m" / sync.STATE).unlink()
        (tmp_path / sync.SERVER).write_text("{}")
        assert sync.active(tmp_path)
        (tmp_path / sync.SERVER).unlink()
        sync.set_auto(tmp_path, True)
        assert sync.active(tmp_path)


class TestBehind:
    def test_names_the_matches_newer_on_the_server(self, tmp_path, monkeypatch):
        found = []
        for name, version in (("same", 3), ("behind", 2), ("unsent", 0)):
            match = tmp_path / "matches" / name
            match.mkdir(parents=True)
            sync.remember(match, version, (0, 0.0))
            found.append(match)
        monkeypatch.setattr(sync, "listing", lambda outputs: {"same": {"version": 3, "pushedBy": "pc"}, "behind": {"version": 3, "pushedBy": "mac"}})

        assert sync.behind(found) == {"behind": "mac"}

    def test_nothing_when_this_machine_keeps_no_match_on_the_server(self, tmp_path):
        match = tmp_path / "matches" / "m"
        match.mkdir(parents=True)

        assert sync.behind([match]) == {}


class TestSharedAuto:
    @pytest.fixture
    def outputs(self, tmp_path, monkeypatch):
        server = {}
        monkeypatch.setattr(sync, "server", lambda outputs: {"upload": "root@host:/site/", "key": "k"})
        monkeypatch.setattr(sync, "shared_settings", lambda config: dict(server))
        monkeypatch.setattr(sync, "share_settings", lambda config, changes: server.update(changes))
        return tmp_path, server

    def test_a_choice_reaches_the_server_and_the_other_machine(self, outputs):
        here, server = outputs
        assert sync.set_auto(here, True) and server == {"auto": True}
        other = here / "other"
        other.mkdir()
        assert not sync.auto(other) and sync.refresh_auto(other) and sync.auto(other)

    def test_kept_here_when_the_server_cannot_take_it(self, outputs, monkeypatch):
        here, _ = outputs

        def refuse(config, changes):
            raise RuntimeError("unreachable")

        monkeypatch.setattr(sync, "share_settings", refuse)
        assert not sync.set_auto(here, True) and sync.auto(here)

    def test_a_server_without_the_choice_leaves_this_machine_s(self, outputs):
        here, _ = outputs
        sync.set_auto(here, True)
        outputs[1].clear()
        assert sync.refresh_auto(here)
