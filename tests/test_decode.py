import subprocess

import cv2
import numpy as np
import pytest

from volleyball_stats import decode
from volleyball_stats.decode import SEEK, frame_at, frames, frames_at, scaled


def test_nvenc_is_false_for_an_encoder_ffmpeg_lacks():
    assert decode.nvenc("nonexistent") is False


class TestScaled:
    def test_scales_a_wide_video_down_to_the_width_with_an_even_height(self):
        assert scaled(3840, 2160) == (1280, 720)
        assert scaled(2704, 1520) == (1280, 720)

    def test_keeps_a_video_no_wider_than_the_width(self):
        assert scaled(1280, 720) == (1280, 720)
        assert scaled(640, 360) == (640, 360)


class TestFrames:
    def video(self, tmp_path, count=12):
        raw, path = tmp_path / "raw.mp4", tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 25, (64, 48))
        rng = np.random.default_rng(0)
        for _ in range(count):
            writer.write(cv2.GaussianBlur(rng.integers(0, 255, (48, 64, 3), np.uint8), (5, 5), 0))
        writer.release()
        # H.264, which every decoder gives bit for bit (NVDEC's MPEG-4 part 2 rounds otherwise).
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(raw), "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", str(path)], check=True)
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

    def test_frames_at_gives_the_same_pixels_over_a_long_gap_by_timestamp(self, tmp_path):
        path = self.video(tmp_path, SEEK + 40)
        expected = self.expected(path)

        found = list(frames_at(path, [3, SEEK + 10, SEEK + 12]))

        assert [index for index, _ in found] == [3, SEEK + 10, SEEK + 12]
        assert all(np.array_equal(image, expected[index]) for index, image in found)

    def test_frames_at_selects_scattered_frames_in_one_run_and_after_a_seek(self, tmp_path):
        path = self.video(tmp_path, 80)
        expected = self.expected(path)
        wanted = [0, 1, 2, 9, 30, 31, 79]

        found = list(frames_at(path, wanted))

        assert [index for index, _ in found] == wanted
        assert all(np.array_equal(image, expected[index]) for index, image in found)
        assert [index for index, _ in frames_at(path, [40, 42, 45])] == [40, 42, 45]
        assert all(np.array_equal(image, expected[index]) for index, image in frames_at(path, [40, 42, 45]))

    def test_frames_at_restarts_after_selected_runs(self, tmp_path, monkeypatch):
        path = self.video(tmp_path, 30)
        expected = self.expected(path)
        monkeypatch.setattr(decode, "SELECTED", 2)
        started, popen = [], subprocess.Popen
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(popen(*args, **kwargs)) or started[-1])

        found = list(frames_at(path, [1, 2, 5, 8, 9, 20]))

        assert [index for index, _ in found] == [1, 2, 5, 8, 9, 20]
        assert all(np.array_equal(image, expected[index]) for index, image in found)
        assert len([p for p in started if "rawvideo" in p.args]) == 2

    def test_frames_at_stops_at_the_video_s_end(self, tmp_path):
        assert [index for index, _ in frames_at(self.video(tmp_path), [3, 11, 12, 13])] == [3, 11]

    def test_frames_at_goes_by_each_frame_s_own_timestamp(self, tmp_path):
        # A video whose frames do not fall on its average rate.
        path = self.video(tmp_path, 40)
        irregular = tmp_path / "irregular.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "setpts='if(gte(N,20),PTS+0.4/TB,PTS)'", "-fps_mode", "passthrough", "-c:v", "libx264", "-crf", "0", str(irregular)], check=True)
        assert decode.timestamps(irregular)[20] - decode.timestamps(irregular)[19] > 0.3
        expected = self.expected(irregular)
        assert np.array_equal(frame_at(irregular, 30), expected[30])

    def test_frame_at_past_the_end_is_none(self, tmp_path):
        assert frame_at(self.video(tmp_path), 40) is None

    def test_frames_at_past_the_end_stops_at_the_last_frame(self, tmp_path):
        assert [index for index, _ in frames_at(self.video(tmp_path), [1, 40])] == [1]

    def test_frames_at_wanting_nothing_gives_nothing(self, tmp_path):
        assert list(frames_at(tmp_path / "none.mp4", [])) == []


class TestApart:
    def test_reads_the_frames_with_several_readers_and_on_the_processor_when_the_gpu_refuses(self, tmp_path, monkeypatch):
        path = TestFrames().video(tmp_path, 40)
        expected = TestFrames().expected(path)
        # A decoder the machine cannot start, as a GPU busy with other work refuses one.
        monkeypatch.setattr(decode, "hardware", lambda video: ("-hwaccel", "nosuchdevice"))

        found = dict(decode.frames_apart(path, [0, 3, 17, 18, 39], workers=3))

        assert sorted(found) == [0, 3, 17, 18, 39]
        assert all(np.array_equal(found[f], expected[f]) for f in found)
