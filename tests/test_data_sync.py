import threading

import pytest

from volleyball_stats import data_sync


class TestExchange:
    @staticmethod
    def waiting(root, code="abcdefgh"):
        server = data_sync.serving(root, code, host="127.0.0.1", port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, data_sync.Peer(f"127.0.0.1:{server.server_address[1]}", code)

    def test_each_side_gets_what_only_the_other_has(self, tmp_path):
        mac, pc = tmp_path / "mac", tmp_path / "pc"
        (mac / "matches" / "m1").mkdir(parents=True)
        (pc / "matches" / "m2").mkdir(parents=True)
        (mac / "matches" / "m1" / "video.mp4").write_bytes(b"one" * 1000)
        (pc / "matches" / "m2" / "video.mp4").write_bytes(b"two" * 1000)
        (mac / ".DS_Store").write_bytes(b"x")
        server, peer = self.waiting(mac)

        differ = data_sync.exchange(peer, pc)
        server.shutdown()

        assert differ == []
        for root in (mac, pc):
            assert (root / "matches" / "m1" / "video.mp4").read_bytes() == b"one" * 1000
            assert (root / "matches" / "m2" / "video.mp4").read_bytes() == b"two" * 1000
        assert not (pc / ".DS_Store").exists()
        assert (pc / "matches" / "m1" / "video.mp4").stat().st_mtime == (mac / "matches" / "m1" / "video.mp4").stat().st_mtime

    def test_a_copy_cut_short_resumes(self, tmp_path):
        mac, pc = tmp_path / "mac", tmp_path / "pc"
        mac.mkdir()
        (pc / "m").mkdir(parents=True)
        (pc / "m" / "video.mp4").write_bytes(b"0123456789")
        (mac / "m").mkdir()
        (mac / "m" / ".video.mp4.part").write_bytes(b"01234")
        server, peer = self.waiting(mac)

        data_sync.exchange(peer, pc)
        server.shutdown()

        assert (mac / "m" / "video.mp4").read_bytes() == b"0123456789" and not (mac / "m" / ".video.mp4.part").exists()

    def test_a_file_that_differs_is_left_and_named(self, tmp_path):
        mac, pc = tmp_path / "mac", tmp_path / "pc"
        for root, body in ((mac, b"a" * 10), (pc, b"b" * 10)):
            root.mkdir()
            (root / "video.mp4").write_bytes(body)
        server, peer = self.waiting(mac)

        assert data_sync.exchange(peer, pc) == ["video.mp4"]
        server.shutdown()
        assert (pc / "video.mp4").read_bytes() == b"b" * 10

    def test_a_wrong_code_reads_nothing(self, tmp_path):
        server, _ = self.waiting(tmp_path)

        with pytest.raises(PermissionError):
            data_sync.Peer(f"127.0.0.1:{server.server_address[1]}", "wrong").json("GET", "/manifest")
        server.shutdown()


class TestInside:
    @pytest.mark.parametrize("rel", ["../outputs/roster.json", "/etc/passwd", "m/../../x", "m/.video.mp4.part", ""])
    def test_nothing_outside_the_folder_nor_hidden(self, tmp_path, rel):
        with pytest.raises(ValueError):
            data_sync.inside(tmp_path, rel)

    def test_a_file_in_it(self, tmp_path):
        assert data_sync.inside(tmp_path, "matches/m/video.mp4") == tmp_path / "matches" / "m" / "video.mp4"
