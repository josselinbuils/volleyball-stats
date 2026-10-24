"""Score contact and net crossing detectors against hand-labelled rallies.

    uv run --group bench python benchmarks/contacts/bench.py score TRACK:GROUND_TRUTH ... [--verbose]
    uv run --group bench python benchmarks/contacts/bench.py sweep TRACK:GROUND_TRUTH ...

`score` runs `contacts.detect` with its defaults; `sweep` searches the threshold, window and
minimum gap of every candidate on the pooled rallies. Both clips run at 29.97 fps with the net at x=612.
"""

import argparse
import csv
import random
from pathlib import Path

import numpy as np

from volleyball_stats import contacts

FPS = 29.97
NET_X = 612
TOLERANCES = (2, 4)
# Slowest incoming or outgoing velocity, in px/frame, whose direction the angle candidate trusts.
MIN_SPEED = 3
WINDOWS = (0.10, 0.13, 0.17, 0.20, 0.27)
GAPS = (0.10, 0.15, 0.20)
THRESHOLDS = {
    "angle": [float(d) for d in range(10, 95, 5)],
    "delta_v": [float(v) for v in range(100, 620, 20)],
    "residual": [0.5 * i for i in range(2, 41)],
}


def angle(track: np.ndarray, fps: float, threshold: float, window: float, gap: float) -> list[int]:
    """Degrees between the incoming and outgoing velocities, when both are faster than MIN_SPEED."""
    w = max(2, round(window * fps))
    frames = np.arange(len(track))
    signal = np.full(len(track), np.nan)
    for t in range(w, len(track) - w):
        before = contacts.fit_velocity(frames[t - w : t], track[t - w : t])
        after = contacts.fit_velocity(frames[t + 1 : t + 1 + w], track[t + 1 : t + 1 + w])
        if before and after:
            a, b = before[0], after[0]
            if min(np.hypot(*a), np.hypot(*b)) >= MIN_SPEED:
                signal[t] = np.degrees(np.arccos(np.clip(a @ b / (np.hypot(*a) * np.hypot(*b)), -1, 1)))
    return contacts.peaks(signal, threshold, round(gap * fps))


def delta_v(track: np.ndarray, fps: float, threshold: float, window: float, gap: float) -> list[int]:
    """The module's detector: velocity change with gravity removed, in px/s."""
    return [t for t, _, _ in contacts.detect_contacts(track, fps, threshold, window, gap)]


def residual(track: np.ndarray, fps: float, threshold: float, window: float, gap: float) -> list[int]:
    """RMS residual in px of one parabola fitted on the frames around each frame."""
    w = max(2, round(window * fps))
    signal = np.full(len(track), np.nan)
    for t in range(w, len(track) - w):
        points = track[t - w : t + w + 1]
        ok = ~np.isnan(points[:, 0])
        if ok.sum() < 5:
            continue
        s = np.arange(-w, w + 1)[ok]
        rx = points[ok, 0] - np.polyval(np.polyfit(s, points[ok, 0], 1), s)
        ry = points[ok, 1] - np.polyval(np.polyfit(s, points[ok, 1], 2), s)
        signal[t] = np.sqrt(np.mean(rx**2 + ry**2))
    return contacts.peaks(signal, threshold, round(gap * fps))


CANDIDATES = {"angle": angle, "delta_v": delta_v, "residual": residual}


def load_ground_truth(path: Path) -> list[dict]:
    """One dict per rally: start, end, contacts {frame: type}, net [frames]."""
    rallies: dict[str, dict] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rally = rallies.setdefault(row["rally"], {"contacts": {}, "net": []})
            frame = int(row["frame"])
            if row["event"] in ("start", "end"):
                rally[row["event"]] = frame
            elif row["event"] == "contact":
                rally["contacts"][frame] = row["type"]
            else:
                rally["net"].append(frame)
    return list(rallies.values())


def match(detected: list[int], truth: list[int], start: int, end: int, tolerance: int) -> tuple[list[int], list[int], list[int]]:
    """Matched truth frames, missed truth frames, false detections inside the rally."""
    free = [d for d in detected if start <= d <= end]
    hits, misses = [], []
    for t in sorted(truth):
        near = [d for d in free if abs(d - t) <= tolerance]
        if near:
            free.remove(min(near, key=lambda d: abs(d - t)))
            hits.append(t)
        else:
            misses.append(t)
    return hits, misses, free


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def bootstrap(counts: list[tuple[int, int, int]], rounds: int = 1000) -> tuple[float, float]:
    """95% interval of F1 over rallies resampled with replacement."""
    rng = random.Random(0)
    scores = sorted(prf(*map(sum, zip(*(rng.choice(counts) for _ in counts))))[2] for _ in range(rounds))
    return scores[int(0.025 * rounds)], scores[int(0.975 * rounds)]


def evaluate(detected: dict[str, list[int]], clips: dict[str, list[dict]], key: str, tolerance: int) -> tuple[list[tuple[int, int, int]], list, list]:
    """Per-rally (tp, fp, fn) for `key` ("contacts" or "net"), with the misses and false detections."""
    counts, misses, false = [], [], []
    for stem, rallies in clips.items():
        for rally in rallies:
            truth = rally[key] if key == "net" else list(rally["contacts"])
            hits, missed, extra = match(detected[stem], truth, rally["start"], rally["end"], tolerance)
            counts.append((len(hits), len(extra), len(missed)))
            misses += [(stem, m, rally["contacts"].get(m, "")) for m in missed]
            false += [(stem, f) for f in extra]
    return counts, misses, false


def score(pairs: list[tuple[Path, Path]], verbose: bool) -> None:
    clips = {truth.stem: load_ground_truth(truth) for _, truth in pairs}
    found = {truth.stem: contacts.detect(contacts.read_track(track), FPS, NET_X) for track, truth in pairs}
    contacts_found = {stem: [t for t, _, _ in c] for stem, (c, _) in found.items()}
    crossings_found = {stem: n for stem, (_, n) in found.items()}
    rallies = sum(len(r) for r in clips.values())
    print(f"{rallies} rallies, {sum(len(r['contacts']) for rs in clips.values() for r in rs)} contacts, {sum(len(r['net']) for rs in clips.values() for r in rs)} net crossings\n")
    print(f"{'what':14} {'tol':>3} {'P':>6} {'R':>6} {'F1':>6} {'95% interval':>14}")
    for key, detected in (("contacts", contacts_found), ("net", crossings_found)):
        for tolerance in TOLERANCES:
            counts, misses, false = evaluate(detected, clips, key, tolerance)
            p, r, f1 = prf(*map(sum, zip(*counts)))
            lo, hi = bootstrap(counts)
            print(f"{key:14} {tolerance:>3} {p:6.3f} {r:6.3f} {f1:6.3f} {f'[{lo:.2f}-{hi:.2f}]':>14}")
            if verbose and tolerance == TOLERANCES[0]:
                print(f"  missed: {misses}\n  false: {false}")
    counts, misses, _ = evaluate(contacts_found, clips, "contacts", TOLERANCES[0])
    types = {t for rs in clips.values() for r in rs for t in r["contacts"].values()}
    print(f"\nrecall per type at ±{TOLERANCES[0]}:")
    for kind in sorted(types):
        total = sum(t == kind for rs in clips.values() for r in rs for t in r["contacts"].values())
        missed = sum(m[2] == kind for m in misses)
        print(f"  {kind or '(unknown)':10} {total - missed:3}/{total}")


def sweep(pairs: list[tuple[Path, Path]]) -> None:
    clips = {truth.stem: load_ground_truth(truth) for _, truth in pairs}
    tracks = {truth.stem: contacts.read_track(track) for track, truth in pairs}
    print(f"{'candidate':10} {'window':>6} {'gap':>5} {'thr':>6} {'F1±2':>6} {'P':>6} {'R':>6} {'F1±4':>6}")
    for name, candidate in CANDIDATES.items():
        rows = []
        for window in WINDOWS:
            for gap in GAPS:
                for threshold in THRESHOLDS[name]:
                    detected = {stem: candidate(track, FPS, threshold, window, gap) for stem, track in tracks.items()}
                    tight = prf(*map(sum, zip(*evaluate(detected, clips, "contacts", TOLERANCES[0])[0])))
                    loose = prf(*map(sum, zip(*evaluate(detected, clips, "contacts", TOLERANCES[1])[0])))
                    rows.append((tight[2], name, window, gap, threshold, tight, loose[2]))
        for f1, name, window, gap, threshold, (p, r, _), loose in sorted(rows, reverse=True)[:5]:
            print(f"{name:10} {window:6.2f} {gap:5.2f} {threshold:6.1f} {f1:6.3f} {p:6.3f} {r:6.3f} {loose:6.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("pairs", nargs="+", help="TRACK_CSV:GROUND_TRUTH_CSV")
    score_parser.add_argument("--verbose", action="store_true", help="List the missed and false contacts")
    sweep_parser = sub.add_parser("sweep")
    sweep_parser.add_argument("pairs", nargs="+", help="TRACK_CSV:GROUND_TRUTH_CSV")
    args = parser.parse_args()
    pairs = [tuple(map(Path, p.split(":"))) for p in args.pairs]
    if args.command == "score":
        score(pairs, args.verbose)
    else:
        sweep(pairs)


if __name__ == "__main__":
    main()
