import json

from volleyball_stats import files, jerseys
from volleyball_stats.jerseys import agreed, load, number


class TestNumber:
    def test_keeps_one_or_two_digits_read_with_confidence(self):
        assert number([([0], "10", 0.99)]) == 10
        assert number([([0], "8", 0.95), ([0], "V", 0.97)]) == 8

    def test_drops_doubtful_long_or_several_readings(self):
        assert number([([0], "10", 0.6)]) is None
        assert number([([0], "123", 0.99)]) is None
        assert number([([0], "10", 0.99), ([0], "23", 0.99)]) is None
        assert number(None) is None


class TestAgreed:
    def test_needs_two_readings_and_no_other_number(self):
        assert agreed([9, 9, 9]) == 9
        assert agreed([9]) is None
        assert agreed([9, 9, 6]) is None


class TestLoad:
    def test_drops_the_rarely_read_numbers(self, tmp_path):
        rows = ["frame,track,number"] + [f"{f},1,22" for f in range(60)] + ["100,2,2"]
        (tmp_path / "jerseys.csv").write_text("\n".join(rows) + "\n")

        assert set(load(tmp_path).values()) == {22}


class TestCacheStamp:
    def test_changes_with_the_video_the_code_and_what_is_given(self, tmp_path):
        video, code = tmp_path / "v.mp4", tmp_path / "code.py"
        video.write_bytes(b"12")
        code.write_text("a")
        first = files.cache_stamp(video, [code])

        assert files.cache_stamp(video, [code]) == first
        assert files.cache_stamp(video, [code], "other") != first
        code.write_text("b")
        changed = files.cache_stamp(video, [code])
        assert changed != first
        video.write_bytes(b"123")
        assert files.cache_stamp(video, [code]) != changed


class TestPicturesRead:
    def test_readings_of_another_stamp_or_of_the_old_format_are_out_of_date(self, tmp_path):
        path = tmp_path / jerseys.PICTURES
        path.write_text(json.dumps({"stamp": "a", "read": {"1:0,0,1,1": 8}}))

        assert jerseys.pictures_read(tmp_path, "a") == {"1:0,0,1,1": 8}
        assert jerseys.pictures_read(tmp_path, "b") == {}
        path.write_text(json.dumps({"1:0,0,1,1": 8}))
        assert jerseys.pictures_read(tmp_path, "a") == {}

    def test_only_new_pictures_are_read(self, tmp_path):
        path = tmp_path / jerseys.PICTURES
        path.write_text(json.dumps({"stamp": "a", "read": {"1:0,0,1,1": 8}}))
        asked = []

        jerseys.read_pictures(tmp_path, [(1, (0, 0, 1, 1))], lambda *args: asked.append(args), "a")

        assert asked == []
