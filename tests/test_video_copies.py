import subprocess

import numpy as np
import pytest

from volleyball_stats import framing, timeline, video_copies


def clip(path, seconds=2, size="640x360"):
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r=50:d={seconds}", "-f", "lavfi", "-i", f"sine=d={seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)]
    subprocess.run(command, check=True)


def stream(path):
    run = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,height,r_frame_rate", "-of", "csv=p=0", str(path)]
    return subprocess.run(run, capture_output=True, text=True, check=True).stdout.strip()


def test_makes_the_three_copies_on_the_sources_timeline_with_its_sound(tmp_path):
    video = tmp_path / "m.mp4"
    clip(video)

    made = video_copies.make(video, {"map": [], "camera": []})

    assert stream(made["light"]) == "h264,1440,25/1"
    assert stream(made["av1"]) == "av1,1440,25/1"
    assert stream(made["small"]) == "h264,720,25/1"
    assert all(video_copies.duration(path) == pytest.approx(2.0, abs=0.1) for path in made.values())
    assert sorted(p.name for p in (tmp_path / "reencoded").iterdir()) == ["m_1440p.mp4", "m_720p.mp4", "m_av1.mp4"]
    sound = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(made["light"])]
    assert subprocess.run(sound, capture_output=True, text=True).stdout.strip() == "aac"


def test_a_copy_cut_short_does_not_appear(tmp_path, monkeypatch):
    video = tmp_path / "m.mp4"
    clip(video)
    monkeypatch.setattr(video_copies, "TOLERANCE_S", -1.0)

    with pytest.raises(RuntimeError, match="lasts"):
        video_copies.make(video, {"map": [], "camera": []})

    assert sorted(p.name for p in tmp_path.iterdir()) == ["m.mp4", "reencoded"] and not any((tmp_path / "reencoded").iterdir())


def test_a_frame_is_cut_where_the_camera_looks():
    # A 16x8 picture, its luma the column's number: zoomed 2x on its right half's middle.
    w, h = 16, 8
    luma = np.tile(np.arange(w, dtype=np.uint8) * 10, (h, 1))
    frame = np.concatenate([luma.ravel(), np.full(w * h // 2, 128, np.uint8)])

    out = np.frombuffer(video_copies.cut(frame, (w, h), (w, h), np.array([0.75, 0.5, 2.0])), np.uint8)

    columns = out[: w * h].reshape(h, w)[h // 2]
    # The right half's 8 columns, each shown twice, at sub-pixel precision.
    assert columns[0] == pytest.approx(80 - 2.5, abs=2) and columns[-1] == pytest.approx(150 + 2.5, abs=3)
    assert np.all(np.diff(columns.astype(int)) >= 0)


def test_the_copies_play_along_their_map(tmp_path):
    video = tmp_path / "m.mp4"
    clip(video, seconds=4)
    # The first second, the next at x2, half a second at half speed, a held frame, a cut to the last second.
    pieces = [[0, 1, 0, 1], [1, 2, 1, 1.5], [2, 2.5, 1.5, 2.5], [2.5, 2.5, 2.5, 3.5], [3.5, 4, 3.5, 4]]

    made = video_copies.make(video, {"map": pieces, "camera": []})

    assert video_copies.duration(made["light"]) == pytest.approx(4, abs=0.1)
    # The cut's fade: black at the cut.
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "3.5", "-i", str(made["light"]), "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    assert np.frombuffer(frame, np.uint8).mean() < 30
    sound = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=duration", "-of", "csv=p=0", str(made["light"])]
    assert float(subprocess.run(sound, capture_output=True, text=True).stdout) == pytest.approx(4, abs=0.1)


def test_how_they_were_made_goes_with_its_copy_only(tmp_path):
    light = tmp_path / "m_1440p.mp4"
    light.write_bytes(b"made")
    camera = framing.camera_spans(np.array([[0.5, 0.5, 1.0], [0.4, 0.5, 1.5], [0.5, 0.5, 1.0]]))
    made = {"map": [[0, 10, 0, 10]], "camera": camera}

    video_copies.record(tmp_path, light, made)

    assert video_copies.recorded(tmp_path, light) == made
    light.write_bytes(b"made again")
    assert video_copies.recorded(tmp_path, light) is None
    assert video_copies.recorded(tmp_path, tmp_path / "other.mp4") is None
