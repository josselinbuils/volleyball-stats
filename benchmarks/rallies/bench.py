"""Score rally segmentation signals against hand-labelled rallies.

    uv run --group bench python benchmarks/rallies/bench.py VIDEO:BALL_TRACK_CSV:GROUND_TRUTH_CSV ... [--show]

Candidates: `ball` (ball track alone), `whistle` (whistle pairs alone), `motion` (global motion
energy alone) and `combined` (rallies.segment: ball runs closed by a whistle).
"""

import argparse
import csv
import random
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import Calibration
from volleyball_stats.rallies import ball_runs, load_track, read_audio, runs, segment, served, whistles, with_serves

OUT = Path("outputs/bench/rallies")
TOLERANCES_S = (1.0, 2.0)
# Whistle pairs: an authorization whistle lasts 0.6 s or more; the serve follows within 40 s.
AUTH_WHISTLE_S = 0.6
SERVE_DELAY_S, END_LEAD_S = 2.5, 0.4
PAIR_GAP_S = (3.0, 40.0)
# Motion energy: mean absolute difference of consecutive 160x90 gray frames, smoothed over 1 s,
# above a multiple of its median for 3 s or more, gaps up to 2 s bridged.
MOTION_FACTORS = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0)
MOTION_BRIDGE_S, MOTION_MIN_S = 2.0, 3.0

Rally = tuple[int, int]


def load_ground_truth(path: Path) -> list[Rally]:
    with open(path) as f:
        return [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]


def motion_energy(video: Path) -> np.ndarray:
    cache = OUT / f"{video.stem}_motion.npy"
    if cache.exists():
        return np.load(cache)
    cap = cv2.VideoCapture(str(video))
    energy, prev = [], None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.cvtColor(cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        energy.append(0.0 if prev is None else float(np.abs(small - prev).mean()))
        prev = small
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, np.array(energy, dtype=np.float32))
    return np.load(cache)


def whistle_rallies(whistle_times: list[tuple[float, float]], fps: float) -> list[Rally]:
    """From each authorization whistle to the next whistle."""
    out = []
    for (onset, end), (next_onset, _) in zip(whistle_times, whistle_times[1:]):
        if end - onset >= AUTH_WHISTLE_S and PAIR_GAP_S[0] <= next_onset - onset <= PAIR_GAP_S[1]:
            out.append((round((end + SERVE_DELAY_S) * fps), round((next_onset - END_LEAD_S) * fps)))
    return out


def motion_rallies(energy: np.ndarray, fps: float, factor: float) -> list[Rally]:
    smooth = np.convolve(energy, np.ones(round(fps)) / round(fps), mode="same")
    return runs(smooth >= factor * np.median(smooth), round(MOTION_BRIDGE_S * fps), round(MOTION_MIN_S * fps))


def match(predicted: list[Rally], truth: list[Rally], tolerance: int) -> list[tuple[Rally, Rally | None]]:
    """Each true rally with the first unused prediction whose boundaries are both within `tolerance`."""
    used, pairs = set(), []
    for true in truth:
        hit = next(
            (i for i, p in enumerate(predicted) if i not in used and abs(p[0] - true[0]) <= tolerance and abs(p[1] - true[1]) <= tolerance),
            None,
        )
        if hit is not None:
            used.add(hit)
        pairs.append((true, predicted[hit] if hit is not None else None))
    return pairs


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def score(predicted: list[Rally], truth: list[Rally], tolerance: int, fps: float) -> dict:
    pairs = match(predicted, truth, tolerance)
    tp = sum(p is not None for _, p in pairs)
    precision, recall, f1 = prf(tp, len(predicted) - tp, len(truth) - tp)
    errors = [abs(p[i] - t[i]) / fps for t, p in pairs if p is not None for i in (0, 1)]
    return {"P": precision, "R": recall, "F1": f1, "MAE": float(np.mean(errors)) if errors else float("nan"), "tp": tp}


def bootstrap_f1(predicted: list[Rally], truth: list[Rally], tolerance: int, rounds: int = 1000) -> tuple[float, float]:
    """95% interval of F1 over rallies resampled with replacement: matched pairs, misses and false alarms."""
    rng = random.Random(0)
    pairs = match(predicted, truth, tolerance)
    units = [(1, 0, 0) if p is not None else (0, 0, 1) for _, p in pairs]
    units += [(0, 1, 0)] * (len(predicted) - sum(p is not None for _, p in pairs))
    scores = []
    for _ in range(rounds):
        sample = [rng.choice(units) for _ in units]
        scores.append(prf(*map(sum, zip(*sample)))[2])
    scores.sort()
    return scores[int(0.025 * rounds)], scores[int(0.975 * rounds)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("triples", nargs="+", help="VIDEO:BALL_TRACK_CSV:GROUND_TRUTH_CSV[:PLAYERS_CSV:COURT_JSON], the players and the court for `served`")
    parser.add_argument("--show", action="store_true", help="Print the predicted rallies of each candidate")
    args = parser.parse_args()

    clips = []
    for triple in args.triples:
        video, track_path, truth_path, *more = map(Path, triple.split(":"))
        fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
        track = load_track(track_path)
        whistle_times = whistles(read_audio(video))
        energy = motion_energy(video)
        candidates = {
            "ball": ball_runs(track, fps),
            "whistle": whistle_rallies(whistle_times, fps),
            "combined": segment(track, whistle_times, fps),
        }
        if more:
            with open(more[0]) as f:
                players = [(int(r["frame"]), float(r["court_x"]), float(r["court_y"])) for r in csv.DictReader(f)]
            serves = served(players, track, whistle_times, fps, Calibration.load(more[1]))
            candidates["served"] = [(s, e) for s, e, _ in serves]
            candidates["combined + served"] = with_serves(candidates["combined"], serves)
        for factor in MOTION_FACTORS:
            candidates[f"motion x{factor:g}"] = motion_rallies(energy, fps, factor)
        clips.append((video.stem, fps, load_ground_truth(truth_path), candidates))

    for stem, fps, truth, candidates in clips:
        print(f"{stem}: {len(truth)} rallies, {sum(e - s for s, e in truth) / fps:.0f} s in play\n")
        print(f"{'candidate':17} {'n':>3} " + " ".join(f"{'±' + f'{t:g}' + ' s':^31}" for t in TOLERANCES_S))
        print(f"{'':21} " + " ".join(f"{'P':>6} {'R':>6} {'F1':>6} {'MAE s':>5} {'[95%]':>10}" for _ in TOLERANCES_S))
        for name, predicted in candidates.items():
            cells = []
            for tol_s in TOLERANCES_S:
                tol = round(tol_s * fps)
                s = score(predicted, truth, tol, fps)
                lo, hi = bootstrap_f1(predicted, truth, tol)
                cells.append(f"{s['P']:6.2f} {s['R']:6.2f} {s['F1']:6.2f} {s['MAE']:5.2f} [{lo:.2f}-{hi:.2f}]")
            print(f"{name:17} {len(predicted):3d} " + " ".join(f"{c:^31}" for c in cells))
            if args.show:
                print("   " + " ".join(f"{s / fps:.1f}-{e / fps:.1f}" for s, e in predicted))
        if args.show:
            print("   truth: " + " ".join(f"{s / fps:.1f}-{e / fps:.1f}" for s, e in truth))
        print()


if __name__ == "__main__":
    main()
