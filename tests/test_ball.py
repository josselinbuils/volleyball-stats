import numpy as np
import torch
from torch import nn

from volleyball_stats.ball import HEIGHT, WIDTH, WINDOW, best_blob, track_frames


class TestBestBlob:
    def test_returns_the_weighted_centroid_and_peak_of_the_strongest_blob(self):
        heatmap = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        heatmap[100, 200:203] = [0.5, 1.0, 0.5]
        heatmap[50, 50] = 0.3

        x, y, peak = best_blob(heatmap)

        assert (x, y, peak) == (201.0, 100.0, 1.0)

    def test_ignores_a_heatmap_below_the_floor(self):
        assert best_blob(np.full((HEIGHT, WIDTH), 0.05, dtype=np.float32)) is None


class TestTrackFrames:
    class FakeModel(nn.Module):
        """Window w puts the ball of its k-th frame at x = 10 * w + k, with a peak growing with
        k, so a frame's earliest window gives its strongest view."""

        def __init__(self):
            super().__init__()
            self.calls = 0

        def forward(self, batch):
            logits = torch.full((1, WINDOW, HEIGHT, WIDTH), -10.0)
            for k in range(WINDOW):
                logits[0, k, 100, 10 * self.calls + k] = 0.5 + k
            self.calls += 1
            return {0: logits}

    def frames(self, count, scale=1):
        return [np.full((HEIGHT * scale, WIDTH * scale, 3), i, dtype=np.uint8) for i in range(count)]

    def test_with_stride_1_keeps_the_strongest_of_the_windows_seeing_a_frame(self):
        results = list(track_frames(self.frames(5, scale=2), self.FakeModel(), "cpu", stride=1, threshold=0.5))

        assert [int(frame[0, 0, 0]) for frame, _ in results] == list(range(5))
        # Frame i sits last in window i - 2; the padded last window (3) only adds weaker views
        # of frames 3 and 4.
        assert [position for _, position in results] == [(0, 200), (2, 200), (4, 200), (24, 200), (44, 200)]

    def test_with_stride_3_each_frame_is_seen_once(self):
        results = list(track_frames(self.frames(5, scale=2), self.FakeModel(), "cpu", stride=3, threshold=0.5))

        # Frames 3 and 4 come from the padded last window (1).
        assert [position for _, position in results] == [(0, 200), (2, 200), (4, 200), (20, 200), (22, 200)]

    def test_drops_positions_below_the_threshold(self):
        results = list(track_frames(self.frames(3), self.FakeModel(), "cpu", threshold=0.9))

        assert [position for _, position in results] == [None, None, (2, 100)]
