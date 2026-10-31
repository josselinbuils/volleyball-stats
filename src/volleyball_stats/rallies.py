"""Rally segmentation from the ball track and the referee's whistle.

A rally is a run of ball motion that starts with a serve (the ball flies across the court within a
second) and is closed by a whistle: the referee whistles every dead ball 0.1-1 s after it, and the
ball itself keeps bouncing, rolling or being thrown back for up to 8 s after that. See
benchmarks/rallies/README.md for the numbers behind the constants.
"""

import argparse
import csv
import subprocess
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import Calibration

SAMPLE_RATE = 16000
# STFT: 1024-point Hann windows every 10 ms, BLOCK windows at a time (~80 MB of spectrum).
FFT_SIZE, HOP = 1024, 160
BLOCK = 8192
# A whistle is a narrow peak between 2.7 and 4.3 kHz (3.3-4.3 on the school match, 2.9-3.3 on the
# first ASPOM match), 30x the median of the 1.5-6 kHz band, for at least 80 ms. Peaks under 15
# (rfft magnitude of float PCM) are too far away to be the referee's.
WHISTLE_BAND = (2700, 4300)
# The referee's whistles are the ones within PITCH_TOLERANCE of the most common pitch of a video's
# whistles, in PITCH_BIN steps; the others come from other courts.
PITCH_BIN, PITCH_TOLERANCE = 100, 500
NOISE_BAND = (1500, 6000)
TONALITY = 30
MIN_PEAK = 15
MIN_WHISTLE_S = 0.08
# Dips shorter than this inside a whistle do not split it.
WHISTLE_GAP_S = 0.2
# Pixel constants for a court COURT_PX long from end line to end line (the school match, 1280x720);
# `scale` is a video's court length over COURT_PX.
COURT_PX = 1032
# Ball motion, in frame pixels per frame over a 3-frame lag: a rolling ball stays under 6, and
# above 60 the tracker jumped to another ball.
LAG = 3
MIN_SPEED, MAX_SPEED = 6, 60
BRIDGE_S = 1.5
MIN_RUN_S = 0.67
MIN_TRAVEL = 300
# A serve covers 200 px of width within a second.
SERVE_TRAVEL = 200
# The closing whistle is the first one at least 0.5 s after the serve, at most 2 s after the last
# ball motion, that is not followed 1-3 s later by a ball still flying at 15 px/frame.
MIN_RALLY_S, WHISTLE_AFTER_S = 0.5, 2.0
LIVE_SPEED = 15
LIVE_WINDOW_S = (1.0, 3.0)
# A server stands behind an end line (court x past SERVER_X meters, inside the sidelines'
# extension) for SERVER_S or more, gaps up to SERVER_GAP_S bridged. The serve leaves as the stand
# ends: the ball is on the server's side of the net then and on the other side within SERVE_FLIGHT_S.
SERVER_X, SERVER_MAX_X, HALF_WIDTH = 9.3, 14.0, 4.5
SERVER_S, SERVER_GAP_S, SERVE_FLIGHT_S = 1.5, 0.5, 3.0
# Two serves under SAME_SERVE_S apart with no whistle between them are one serve seen twice.
SAME_SERVE_S = 8.0

Rally = tuple[int, int]


def load_track(path: Path) -> np.ndarray:
    """Ball positions by frame, NaN when not visible."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    track = np.full((len(rows), 2), np.nan)
    for row in rows:
        if row["visible"] == "1":
            track[int(row["frame"])] = (float(row["x"]), float(row["y"]))
    return track


def speed(track: np.ndarray) -> np.ndarray:
    """Pixels per frame over LAG frames, NaN when either end is not visible."""
    out = np.full(len(track), np.nan)
    out[LAG:] = np.hypot(*(track[LAG:] - track[:-LAG]).T) / LAG
    return out


def runs(mask: np.ndarray, bridge: int, min_len: int) -> list[Rally]:
    """Inclusive index runs of True, gaps up to `bridge` bridged, shorter than `min_len` dropped."""
    out: list[Rally] = []
    start = last = None
    for i in np.flatnonzero(mask):
        if start is None or i - last - 1 > bridge:
            if start is not None and last - start + 1 >= min_len:
                out.append((int(start), int(last)))
            start = i
        last = i
    if start is not None and last - start + 1 >= min_len:
        out.append((int(start), int(last)))
    return out


def ball_runs(track: np.ndarray, fps: float, scale: float = 1.0) -> list[Rally]:
    """Runs of ball motion that cross the court, trimmed to start at the serve."""
    px = speed(track) / scale
    moving = px >= MIN_SPEED
    # A jump to another ball ends the run instead of joining two.
    pieces = np.split(np.arange(len(track)), np.flatnonzero(px > MAX_SPEED))
    found = []
    for piece in pieces:
        if len(piece):
            offset = int(piece[0])
            found += [(s + offset, e + offset) for s, e in runs(moving[piece], round(BRIDGE_S * fps), round(MIN_RUN_S * fps))]
    out = []
    for start, end in found:
        xs = track[start : end + 1, 0]
        if np.nanmax(xs) - np.nanmin(xs) < MIN_TRAVEL * scale:
            continue
        for f in range(start, end + 1):
            ahead = track[f : f + round(fps) + 1, 0]
            if np.isfinite(track[f, 0]) and np.nanmax(np.abs(ahead - track[f, 0])) >= SERVE_TRAVEL * scale:
                start = f
                break
        out.append((start, end))
    return out


def read_audio(video: Path) -> np.ndarray:
    """Mono float PCM at SAMPLE_RATE, through ffmpeg."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    pcm = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768


def whistles(audio: np.ndarray) -> list[tuple[float, float]]:
    """(onset, end) in seconds of every sustained narrow-band peak in the whistle band at the
    referee's pitch."""
    if len(audio) < FFT_SIZE:
        return []
    frames = np.lib.stride_tricks.sliding_window_view(audio, FFT_SIZE)[::HOP]
    freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
    in_noise = (freqs >= NOISE_BAND[0]) & (freqs <= NOISE_BAND[1])
    in_band = (freqs >= WHISTLE_BAND[0]) & (freqs <= WHISTLE_BAND[1])
    window = np.hanning(FFT_SIZE)
    tonal, pitch = np.zeros(len(frames), bool), np.zeros(len(frames))
    for start in range(0, len(frames), BLOCK):
        spectrum = np.abs(np.fft.rfft(frames[start : start + BLOCK] * window, axis=1))
        noise, band = spectrum[:, in_noise], spectrum[:, in_band]
        peak = band.max(axis=1)
        tonal[start : start + BLOCK] = (peak >= MIN_PEAK) & (peak >= TONALITY * np.median(noise, axis=1)) & (peak >= noise.max(axis=1))
        pitch[start : start + BLOCK] = freqs[in_band][band.argmax(axis=1)]
    step = HOP / SAMPLE_RATE
    found = runs(tonal, round(WHISTLE_GAP_S / step), round(MIN_WHISTLE_S / step))
    if not found:
        return []
    pitches = np.array([np.median(pitch[start : end + 1][tonal[start : end + 1]]) for start, end in found])
    common = np.bincount((pitches // PITCH_BIN).astype(int)).argmax() * PITCH_BIN + PITCH_BIN / 2
    return [(start * step, (end + 1) * step) for (start, end), p in zip(found, pitches) if abs(p - common) <= PITCH_TOLERANCE]


def segment(track: np.ndarray, whistle_times: list[tuple[float, float]], fps: float, scale: float = 1.0) -> list[Rally]:
    """Ball runs closed by a whistle; the whistle caps the end when it comes first.

    ponytail: no whistle, no rally. The dead ball keeps bouncing, rolling and being thrown back for
    up to 8 s, and only the court module's floor position could retire it without the whistle.
    """
    fast = speed(track) >= LIVE_SPEED * scale
    onsets = np.array([w[0] for w in whistle_times])
    out = []
    for start, end in ball_runs(track, fps, scale):
        candidates = onsets[(onsets >= start / fps + MIN_RALLY_S) & (onsets <= end / fps + WHISTLE_AFTER_S)]
        for onset in candidates:
            lo, hi = (round((onset + s) * fps) for s in LIVE_WINDOW_S)
            if not fast[lo:hi].any():
                out.append((start, min(end, round(onset * fps))))
                break
    return out


def stands(players: list[tuple[int, float, float]], frames: int, fps: float) -> list[tuple[int, int, int]]:
    """(start, end, side) of each stand of a player behind an end line, side -1 for the left end;
    `players` holds (frame, court x, court y) rows."""
    out = []
    for side in (-1, 1):
        mask = np.zeros(frames, bool)
        mask[[f for f, x, y in players if f < frames and SERVER_X < side * x < SERVER_MAX_X and abs(y) < HALF_WIDTH]] = True
        out += [(start, end, side) for start, end in runs(mask, round(SERVER_GAP_S * fps), round(SERVER_S * fps))]
    return sorted(out)


def court_scale(calibration: Calibration) -> float:
    """The court's length in the image over COURT_PX."""
    ends = calibration.to_image(np.array([[-9.0, 0.0], [9.0, 0.0]]))
    return float(np.hypot(*(ends[1] - ends[0]))) / COURT_PX


def served(players: list[tuple[int, float, float]], track: np.ndarray, whistle_times: list[tuple[float, float]], fps: float, calibration: Calibration) -> list[tuple[int, int, int]]:
    """(start, end, side) of each rally, from its serve (side -1 from the left end) to the first
    whistle at least MIN_RALLY_S later and before the next serve, other than the referee's go for a
    serve (a whistle during the stand that ends in a serve). Without one, the rally ends with the
    ball run of its serve, at the latest as the next server takes position."""
    net_x = float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    lead, flight, gap = round(fps), round(SERVE_FLIGHT_S * fps), round(SERVER_GAP_S * fps)
    found = [
        (start, end, side) for start, end, side in stands(players, len(track), fps)
        if np.any(side * (track[max(0, end - lead) : end + 1, 0] - net_x) > 0) and np.any(side * (track[end : end + flight + 1, 0] - net_x) < 0)
    ]
    onsets = [round(w[0] * fps) for w in whistle_times]
    closing = np.array([o for o in onsets if not any(start - gap <= o <= end + gap for start, end, _ in found)], dtype=int)
    kept: list[tuple[int, int, int]] = []
    for stand, frame, side in found:
        if kept and frame - kept[-1][1] < SAME_SERVE_S * fps and not np.any((closing > kept[-1][1]) & (closing < frame)):
            continue
        kept.append((stand, frame, side))
    flights = ball_runs(track, fps, court_scale(calibration))
    out = []
    for (_, frame, side), (stand, following, _) in zip(kept, [*kept[1:], (len(track), len(track), 0)]):
        ends = closing[(closing >= frame + MIN_RALLY_S * fps) & (closing < following)]
        if len(ends):
            out.append((frame, int(ends[0]), side))
        else:
            flight_end = next((end for start, end in flights if start <= frame + lead and end > frame), frame + lead)
            out.append((frame, min(flight_end, stand) if stand > frame else flight_end, side))
    return out


def with_serves(rallies: list[Rally], serves: list[tuple[int, int, int]]) -> list[Rally]:
    """`rallies` and the served ones that overlap none of them."""
    return sorted(rallies + [(s, e) for s, e, _ in serves if not any(s <= end and start <= e for start, end in rallies)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Find the rallies of a volleyball video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("track", type=Path, help="Ball track CSV from ball.py")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    fps = cv2.VideoCapture(str(args.video)).get(cv2.CAP_PROP_FPS)
    rallies = segment(load_track(args.track), whistles(read_audio(args.video)), fps)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / f"{args.video.stem}_rallies.csv", "w", newline="") as f:
        rows = csv.writer(f)
        rows.writerow(["start_frame", "end_frame"])
        rows.writerows(rallies)
    print(f"{len(rallies)} rallies")


if __name__ == "__main__":
    main()
