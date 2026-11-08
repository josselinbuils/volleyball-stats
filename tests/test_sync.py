import json

import pytest

from volleyball_stats import backup, sync, sync_remote


class TestRemote:
    def test_a_free_match_is_claimed_and_another_machine_is_refused_unless_it_forces(self, tmp_path):
        root = str(tmp_path)

        first = sync_remote.run(root, "claim", "m", "mac")
        refused = sync_remote.run(root, "claim", "m", "pc")
        forced = sync_remote.run(root, "claim", "m", "pc", force=True)

        assert first["ok"] and first["owner"] == "mac"
        assert not refused["ok"] and refused["owner"] == "mac"
        assert forced["ok"] and forced["owner"] == "pc"

    def test_a_push_goes_from_the_server_version_only_and_moves_it(self, tmp_path):
        root = str(tmp_path)
        sync_remote.run(root, "claim", "m", "mac")

        assert not sync_remote.run(root, "begin", "m", "mac", 1)["ok"]
        assert sync_remote.run(root, "begin", "m", "mac", 0)["ok"]
        assert sync_remote.run(root, "commit", "m", "mac", 0)["version"] == 1
        # The version moved: a push from the old one is refused.
        assert not sync_remote.run(root, "begin", "m", "mac", 0)["ok"]
        assert not sync_remote.run(root, "begin", "m", "pc", 1)["ok"]

    def test_a_push_takes_a_match_nobody_holds(self, tmp_path):
        assert sync_remote.run(str(tmp_path), "begin", "m", "pc", 0)["ok"]
        assert sync_remote.run(str(tmp_path), "claim", "m", "mac")["owner"] == "pc"

    def test_lists_each_match_by_its_newest_copy(self, tmp_path):
        for day in ("2026-11-01", "2026-11-03"):
            (tmp_path / day / "m").mkdir(parents=True)
            (tmp_path / day / "m" / "source.json").write_text("{}")
        (tmp_path / "2026-11-01" / "old").mkdir()
        (tmp_path / "2026-11-01" / "old" / "source.json").write_text("{}")
        (tmp_path / "2026-11-03" / "courts").mkdir()

        found = sync_remote.run(str(tmp_path), "list", "-", "mac")["matches"]

        assert {k: v["day"] for k, v in found.items()} == {"m": "2026-11-03", "old": "2026-11-01"}
        assert found["m"]["version"] == 0 and found["m"]["owner"] is None


class TestMerged:
    @staticmethod
    def player(name, team, jersey, **vectors):
        return {"name": name, "team": team, "jersey": jersey, "vectors": vectors}

    def test_each_match_from_the_machine_that_holds_it(self):
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

        def remote(config, op, match="-", base=0, force=False):
            calls.append((op, base))
            return {"owner": "pc", "since": "2026-11-08T14:02:00+0100", "version": 2, "pushed": None, "pushedBy": None, **answers[op]}

        monkeypatch.setattr(sync, "remote", remote)
        monkeypatch.setattr(sync, "merge_roster", lambda *args, **kwargs: None)
        monkeypatch.setattr(sync.backup, "backup", lambda m: calls.append(("backup", None)))
        return match, calls

    def test_refused_when_another_machine_holds_the_match(self, tmp_path, monkeypatch):
        match, calls = self.setup(tmp_path, monkeypatch, {"begin": {"ok": False}})

        with pytest.raises(sync.Elsewhere) as error:
            sync.push(match)

        assert calls == [("begin", 0)] and error.value.claim == {"machine": "pc", "at": "14:02", "changed": True}

    def test_copies_then_takes_the_new_version(self, tmp_path, monkeypatch):
        match, calls = self.setup(tmp_path, monkeypatch, {"begin": {"ok": True, "version": 0}, "commit": {"ok": True, "version": 1}})

        sync.push(match)

        assert calls == [("begin", 0), ("backup", None), ("commit", 0)] and sync.local(match)["version"] == 1


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
