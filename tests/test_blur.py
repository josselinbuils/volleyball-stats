import cv2
import numpy as np
import pytest

from volleyball_stats.blur import boxes, pixelate, write


class TestBoxes:
    def test_carries_a_track_across_a_short_gap_and_holds_it_at_its_ends(self):
        # At 4 fps a gap of 1 s is 4 frames, holding 0.5 s is 2.
        found = boxes([(10, 1, (0.0, 0.0, 10.0, 10.0)), (14, 1, (4.0, 0.0, 14.0, 10.0))], 4.0)

        assert sorted(found) == [8, 9, 10, 11, 12, 13, 14, 15, 16]
        assert found[12] == [(2.0, 0.0, 12.0, 10.0)]
        assert found[8] == [(0.0, 0.0, 10.0, 10.0)] and found[16] == [(4.0, 0.0, 14.0, 10.0)]

    def test_carries_a_track_across_a_stitched_gap(self):
        # players.stitch joins pieces up to 2 s apart: 1.5 s here.
        found = boxes([(0, 1, (0.0, 0.0, 1.0, 1.0)), (6, 1, (0.0, 0.0, 1.0, 1.0))], 4.0)

        assert set(range(7)) <= set(found)

    def test_holds_both_sides_of_a_long_gap_and_leaves_its_middle_open(self):
        found = boxes([(0, 1, (0.0, 0.0, 1.0, 1.0)), (40, 1, (0.0, 0.0, 1.0, 1.0))], 4.0)

        assert {0, 1, 2, 38, 39, 40} <= set(found) and 20 not in found


class TestWrite:
    def test_refuses_players_tracked_on_a_larger_copy_of_the_video(self, tmp_path):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(5):
            writer.write(np.zeros((48, 64, 3), np.uint8))
        writer.release()
        (tmp_path / "tracks.csv").write_text("track,team\n1,1\n")
        # A box of the 4K original, far past this copy's 64 px.
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2\n0,1,left,100,10,200,40\n")

        with pytest.raises(ValueError):
            write(tmp_path, video, {1}, tmp_path / "out.mp4")
        assert not (tmp_path / "out.mp4").exists()


class TestPixelate:
    def test_hides_the_boxes_details_and_leaves_the_rest(self):
        rng = np.random.default_rng(0)
        image = rng.integers(0, 255, (100, 100, 3), np.uint8)
        before = image.copy()

        pixelate(image, [(20.0, 20.0, 60.0, 80.0)])

        # Blocks of 7 px (a tenth of the enlarged 72 px height): neighbours inside one block match.
        assert np.array_equal(image[30, 30], image[30, 31])
        assert np.array_equal(image[95:, :], before[95:, :])
