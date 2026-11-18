import os

import numpy as np
import pytest

from volleyball_stats import player_table

HEADER = "frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n"
ROWS = "0,2,right,2767.3,839.3,2888.3,1176.8,0.876,2827.8,1176.8,5.45,3.86\n5,7,left,-3.1,0.0,12.5,99.9,0.3,4.2,99.9,-0.0,-12.34\n"


def same(a: dict, b: dict) -> bool:
    """The same columns, to the bit (-0.0 is not 0.0)."""
    return a.keys() == b.keys() and all(a[k].dtype.kind == b[k].dtype.kind and a[k].tobytes() == b[k].tobytes() for k in a)


class TestRead:
    def test_gives_the_columns_as_parsed_then_the_same_from_its_cache(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text(HEADER + ROWS)

        parsed = player_table.read(path)

        assert parsed["frame"].tolist() == [0, 5] and parsed["team"].tolist() == ["right", "left"]
        assert parsed["x1"].tolist() == [2767.3, -3.1] and parsed["conf"].tolist() == [0.876, 0.3]
        assert np.signbit(parsed["court_x"][1]) and parsed["court_y"].tolist() == [3.86, -12.34]
        assert (tmp_path / player_table.CACHE).exists()
        assert same(player_table.read(path), parsed)

    def test_reads_again_a_players_csv_made_again(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text(HEADER + ROWS)
        player_table.read(path)

        path.write_text(HEADER + ROWS.replace("2767.3", "1.5"))
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1))

        assert player_table.read(path)["x1"].tolist() == [1.5, -3.1]

    def test_keeps_as_they_are_the_numbers_with_more_decimals(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text(HEADER + ROWS.replace("2767.3", "2767.3456"))

        assert player_table.read(path)["x1"].tolist() == [2767.3456, -3.1]
        assert player_table.read(path)["x1"].tolist() == [2767.3456, -3.1]

    def test_an_empty_one_has_empty_columns(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text(HEADER)

        assert all(len(v) == 0 for v in player_table.read(path).values())
        assert all(len(v) == 0 for v in player_table.read(path).values())

    def test_refuses_other_columns(self, tmp_path):
        path = tmp_path / "players.csv"
        path.write_text("frame,track\n0,1\n")

        with pytest.raises(ValueError):
            player_table.read(path)
