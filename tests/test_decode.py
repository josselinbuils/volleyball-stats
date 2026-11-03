import subprocess

import cv2
import numpy as np
import pytest

from volleyball_stats.decode import SEEK, frames, frames_at, scaled


class TestScaled:
    def test_scales_a_wide_video_down_to_the_width_with_an_even_height(self):
        assert scaled(3840, 2160) == (1280, 720)
        assert scaled(2704, 1520) == (1280, 720)

    def test_keeps_a_video_no_wider_than_the_width(self):
        assert scaled(1280, 720) == (1280, 720)
        assert scaled(640, 360) == (640, 360)


class TestFrames:
    def video(self, tmp_path, count=12):
        path = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (64, 48))
        rng = np.random.default_rng(0)
        for _ in range(count):
            writer.write(cv2.GaussianBlur(rng.integers(0, 255, (48, 64, 3), np.uint8), (5, 5), 0))
        writer.release()
        return path

    def test_gives_opencvs_pixels_for_every_frame(self, tmp_path):
        path = self.video(tmp_path)
        cap = cv2.VideoCapture(str(path))
        expected = []
        while (read := cap.read())[0]:
            expected.append(read[1])

        found = list(frames(path))

        assert len(found) == len(expected) == 12
        assert all(np.array_equal(a, b) for a, b in zip(found, expected))

    def test_scales_down_and_stops_ffmpeg_when_the_reader_stops(self, tmp_path, monkeypatch):
        # More frames than the pipe holds: ffmpeg waits for the reader until it is stopped.
        started, popen = [], subprocess.Popen
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(popen(*args, **kwargs)) or started[-1])
        decoded = frames(self.video(tmp_path, 300), width=32)

        assert next(decoded).shape == (24, 32, 3)
        decoded.close()
        assert started[-1].poll() is not None

    def expected(self, path):
        cap = cv2.VideoCapture(str(path))
        found = []
        while (read := cap.read())[0]:
            found.append(read[1])
        return found

    def test_frames_at_gives_opencvs_pixels_at_the_wanted_frames_in_order(self, tmp_path):
        path = self.video(tmp_path)
        expected = self.expected(path)

        found = list(frames_at(path, [7, 2, 3, 7]))

        assert [index for index, _ in found] == [2, 3, 7]
        assert all(np.array_equal(image, expected[index]) for index, image in found)

    def test_frames_at_stops_ffmpeg_after_the_last_wanted_frame(self, tmp_path, monkeypatch):
        started, popen = [], subprocess.Popen
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(popen(*args, **kwargs)) or started[-1])

        assert [index for index, _ in frames_at(self.video(tmp_path, 300), [1, 2])] == [1, 2]
        assert started[-1].poll() is not None

    def test_frames_at_seeks_with_opencv_when_it_would_skip_most_of_the_video(self, tmp_path, monkeypatch):
        path = self.video(tmp_path, SEEK + 20)
        expected = self.expected(path)
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("ffmpeg decoded through the gap"))

        found = list(frames_at(path, [SEEK + 10]))

        assert [index for index, _ in found] == [SEEK + 10]
        assert np.array_equal(found[0][1], expected[SEEK + 10])

    def test_frames_at_past_the_end_stops_at_the_last_frame(self, tmp_path):
        assert [index for index, _ in frames_at(self.video(tmp_path), [1, 40])] == [1]

    def test_frames_at_wanting_nothing_gives_nothing(self, tmp_path):
        assert list(frames_at(tmp_path / "none.mp4", [])) == []
