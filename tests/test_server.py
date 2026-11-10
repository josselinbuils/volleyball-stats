import time

import pytest

from volleyball_stats import backup, server


class TestServer:
    LISTING = "/dev/sda1 40458684 25425388 15016912 63% /\n{\"keep\": 2}\n2026-01-01/\n2026-01-02/\n2026-01-03/\n2026-01-01/a/source.json\n2026-01-02/a/source.json\n2026-01-03/b/source.json\n"

    @pytest.fixture
    def remote(self, monkeypatch):
        sent = []

        def ssh(found, command, timeout=30):
            sent.append(command)
            if command.startswith("rm "):
                return ""
            sizes = "::sizes\n2026-01-01 1767225600 100\n2026-01-02 1767312000 200\n2026-01-03 1767398400 300\n2048\n" if "::sizes" in command else ""
            return self.LISTING + sizes

        monkeypatch.setattr(server.sync, "server", lambda outputs: {"upload": "root@h:/site/", "key": "k"})
        monkeypatch.setattr(server, "ssh", ssh)
        monkeypatch.setattr(server.sync, "share_settings", lambda found, changes: sent.append(changes))
        return sent

    def test_lists_each_copy_with_its_own_size_and_the_matches_it_holds_the_newest_of(self, remote, tmp_path):
        found = server.copies(tmp_path)
        assert (found["free"], found["used"], found["keep"]) == (14.3, 2048 * 1024, 2)
        assert found["days"] == [
            {"day": "2026-01-03", "saved": None, "matches": ["b"], "size": 300, "newest": ["b"]},
            {"day": "2026-01-02", "saved": None, "matches": ["a"], "size": 200, "newest": ["a"]},
            {"day": "2026-01-01", "saved": None, "matches": ["a"], "size": 100, "newest": []},
        ]

    def test_an_hours_copy_says_when_it_was_last_saved_while_its_hour_lasted(self):
        at = time.mktime((2026, 11, 10, 22, 57, 52, 0, 0, -1))
        assert server.saved_at("2026-11-10T22", at) == "2026-11-10T22:57:52"
        # Moved later (a rename): only its hour is known; a daily copy has none.
        assert server.saved_at("2026-11-10T21", at) is None
        assert server.saved_at("2026-11-10", at) is None

    def test_never_removes_a_match_s_newest_copy(self, remote, tmp_path):
        with pytest.raises(PermissionError):
            server.delete(tmp_path, "2026-01-02")
        server.delete(tmp_path, "2026-01-01")
        assert remote[-1] == f"rm -rf {backup.ROOT}/2026-01-01"
        with pytest.raises(ValueError):
            server.delete(tmp_path, "../x")

    def test_tells_what_a_count_removes_before_removing_it(self, remote, tmp_path):
        assert server.keep(tmp_path, 1, False) == ["2026-01-01"] and not any(c.startswith("rm ") for c in remote if isinstance(c, str))
        assert server.keep(tmp_path, 1, True) == ["2026-01-01"]
        assert {"keep": 1} in remote and remote[-1] == f"rm -rf {backup.ROOT}/2026-01-01"
        with pytest.raises(ValueError):
            server.keep(tmp_path, 0, False)
