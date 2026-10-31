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
