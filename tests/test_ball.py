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
        k, so the last window covering a frame wins."""

        def __init__(self):
            super().__init__()
            self.calls = 0

        def forward(self, batch):
            logits = torch.full((1, WINDOW, HEIGHT, WIDTH), -10.0)
            for k in range(WINDOW):
                logits[0, k, 100, 10 * self.calls + k] = 0.5 + k
            self.calls += 1
            return {0: logits}

    def test_keeps_for_each_frame_the_strongest_window_and_yields_every_frame(self):
        frames = [np.full((HEIGHT * 2, WIDTH * 2, 3), i, dtype=np.uint8) for i in range(5)]

        results = list(track_frames(frames, self.FakeModel(), "cpu", threshold=0.5))

        assert [int(frame[0, 0, 0]) for frame, _ in results] == list(range(5))
        # Later slots have higher peaks, so each frame keeps its view from the earliest window
        # covering it; the padded last window (3) only adds weaker views of frames 3 and 4.
        assert [position for _, position in results] == [(0, 200), (2, 200), (4, 200), (24, 200), (44, 200)]

    def test_drops_positions_below_the_threshold(self):
        frames = [np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8) for _ in range(3)]

        results = list(track_frames(frames, self.FakeModel(), "cpu", threshold=0.9))

        assert [position for _, position in results] == [None, None, (2, 100)]
