import pytest

from volleyball_stats.files import replacing, write_text


class TestReplacing:
    def test_keeps_the_previous_file_when_writing_stops_halfway_and_leaves_no_temporary_file(self, tmp_path):
        path = tmp_path / "answers.json"
        write_text(path, "old")

        with pytest.raises(KeyboardInterrupt):
            with replacing(path) as f:
                f.write("half")
                raise KeyboardInterrupt

        assert path.read_text() == "old" and [p.name for p in tmp_path.iterdir()] == ["answers.json"]
        write_text(path, "new")
        assert path.read_text() == "new" and [p.name for p in tmp_path.iterdir()] == ["answers.json"]
