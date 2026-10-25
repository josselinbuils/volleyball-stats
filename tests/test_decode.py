import cv2
import numpy as np

from volleyball_stats.decode import frames, scaled


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

    def test_scales_down_and_stops_ffmpeg_when_the_reader_stops(self, tmp_path):
        decoded = frames(self.video(tmp_path), width=32)

        assert next(decoded).shape == (24, 32, 3)
        decoded.close()
