from volleyball_stats.jerseys import agreed, number


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
