import numpy as np

from volleyball_stats.blur import boxes, pixelate


class TestBoxes:
    def test_carries_a_track_across_a_short_gap_and_holds_it_at_its_ends(self):
        # At 4 fps a gap of 1 s is 4 frames, holding 0.5 s is 2.
        found = boxes([(10, 1, (0.0, 0.0, 10.0, 10.0)), (14, 1, (4.0, 0.0, 14.0, 10.0))], 4.0)

        assert sorted(found) == [8, 9, 10, 11, 12, 13, 14, 15, 16]
        assert found[12] == [(2.0, 0.0, 12.0, 10.0)]
        assert found[8] == [(0.0, 0.0, 10.0, 10.0)] and found[16] == [(4.0, 0.0, 14.0, 10.0)]

    def test_leaves_a_long_gap_open(self):
        found = boxes([(0, 1, (0.0, 0.0, 1.0, 1.0)), (40, 1, (0.0, 0.0, 1.0, 1.0))], 4.0)

        assert 20 not in found and 0 in found and 40 in found


class TestPixelate:
    def test_hides_the_boxes_details_and_leaves_the_rest(self):
        rng = np.random.default_rng(0)
        image = rng.integers(0, 255, (100, 100, 3), np.uint8)
        before = image.copy()

        pixelate(image, [(20.0, 20.0, 60.0, 80.0)])

        # Blocks of 7 px (a tenth of the enlarged 72 px height): neighbours inside one block match.
        assert np.array_equal(image[30, 30], image[30, 31])
        assert np.array_equal(image[95:, :], before[95:, :])
