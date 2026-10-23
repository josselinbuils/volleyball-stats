"""Run ball tracker candidates on a video and score them against ground truth.

    uv run --group bench python benchmarks/ball/bench.py run VIDEO [--only NAME ...]
    uv run --group bench python benchmarks/ball/bench.py score VIDEO GROUND_TRUTH_CSV [--tolerance PX]
    uv run --group bench python benchmarks/ball/bench.py compare VIDEO:GROUND_TRUTH_CSV ... [--tolerance PX]
    uv run --group bench python benchmarks/ball/bench.py hits VIDEO:GROUND_TRUTH_CSV ... [--tolerance PX]
"""

import argparse
import csv
import json
import math
import time
from pathlib import Path

from candidates import CANDIDATES, DEVICE

OUT = Path("outputs/bench")
THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]
# WASB's online tracker: blobs farther than this from the last ball are ignored, for 1280 px wide.
MAX_DISP = 300 / 1280


def run(video: Path, names: list[str]) -> None:
    out = OUT / video.stem
    out.mkdir(parents=True, exist_ok=True)
    timings_path = out / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    for name in names:
        start = time.perf_counter()
        frames = CANDIDATES[name](video)
        elapsed = time.perf_counter() - start
        device = getattr(CANDIDATES[name], "device", DEVICE)
        timings[name] = {"seconds": round(elapsed, 1), "fps": round(len(frames) / elapsed, 1), "device": device}
        with open(out / f"{name}.jsonl", "w") as f:
            for blobs in frames:
                f.write(json.dumps([[round(v, 4) for v in b] for b in blobs]) + "\n")
        print(f"{name}: {timings[name]}")
        timings_path.write_text(json.dumps(timings, indent=2))


def select_top(frames, threshold, width):
    """Highest-peak blob of each frame."""
    return [max((b for b in blobs if b[2] >= threshold), key=lambda b: b[2], default=None) for blobs in frames]


def select_online(frames, threshold, width):
    """WASB's online tracker: the heaviest blob near the previous ball."""
    picks, last = [], None
    for blobs in frames:
        blobs = [b for b in blobs if b[2] >= threshold]
        if last:
            blobs = [b for b in blobs if math.dist(b[:2], last[:2]) < MAX_DISP * width]
        last = max(blobs, key=lambda b: b[3], default=None)
        picks.append(last)
    return picks


POLICIES = {"top": select_top, "online": select_online}


def load_ground_truth(path: Path) -> dict[int, tuple[float, float] | None]:
    with open(path) as f:
        return {int(r["frame"]): (float(r["x"]), float(r["y"])) if r["visible"] == "1" else None for r in csv.DictReader(f)}


def f1(picks, truth, tolerance: float) -> tuple[float, float, float]:
    """Precision, recall, F1. A pick farther than `tolerance` from the ball is both FP and FN."""
    tp = fp = fn = 0
    for frame, ball in truth.items():
        p = picks[frame]
        hit = p is not None and ball is not None and math.dist(p[:2], ball) <= tolerance
        tp += hit
        fp += p is not None and not hit
        fn += ball is not None and not hit
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def score(video: Path, truth_path: Path, tolerance: float) -> None:
    import cv2

    width = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_WIDTH)
    out = OUT / video.stem
    truth = load_ground_truth(truth_path)
    timings = json.loads((out / "timings.json").read_text())
    visible = sum(b is not None for b in truth.values())
    print(f"{video.stem}: {len(truth)} annotated frames, {visible} with the ball, tolerance {tolerance:g} px\n")
    print(f"{'candidate':18} {'policy':7} {'F1':>6} {'thr':>5} {'P':>6} {'R':>6} {'fps':>7}")
    rows = []
    for name in CANDIDATES:
        path = out / f"{name}.jsonl"
        if not path.exists():
            continue
        frames = [json.loads(line) for line in path.open()]
        for policy, select in POLICIES.items():
            thr, (p, r, best) = max(
                ((t, f1(select(frames, t, width), truth, tolerance)) for t in THRESHOLDS), key=lambda x: x[1][2]
            )
            rows.append((best, name, policy, thr, p, r, timings[name]["fps"]))
    for best, name, policy, thr, p, r, fps in sorted(rows, reverse=True):
        print(f"{name:18} {policy:7} {best:6.3f} {thr:5.2f} {p:6.3f} {r:6.3f} {fps:7.1f}")


def bootstrap_f1(picks, truth, tolerance: float, rounds: int = 1000) -> tuple[float, float]:
    """95% interval of F1 over frames resampled with replacement."""
    import random

    rng = random.Random(0)
    frames = list(truth)
    scores = []
    for _ in range(rounds):
        sample = [rng.choice(frames) for _ in frames]
        tp = fp = fn = 0
        for frame in sample:
            p, ball = picks[frame], truth[frame]
            hit = p is not None and ball is not None and math.dist(p[:2], ball) <= tolerance
            tp += hit
            fp += p is not None and not hit
            fn += ball is not None and not hit
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    scores.sort()
    return scores[int(0.025 * rounds)], scores[int(0.975 * rounds)]


def compare(pairs: list[tuple[Path, Path]], tolerance: float) -> None:
    """One threshold per candidate for every video, chosen on their mean F1."""
    import cv2

    clips = []
    for video, truth_path in pairs:
        width = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_WIDTH)
        clips.append((video.stem, width, load_ground_truth(truth_path)))
    header = " ".join(f"{stem:>22}" for stem, _, _ in clips)
    print(f"tolerance {tolerance:g} px, F1 [95% interval] per clip\n")
    print(f"{'candidate':18} {'thr':>5} {'mean':>6} {header}")
    rows = []
    for name in CANDIDATES:
        paths = [OUT / stem / f"{name}.jsonl" for stem, _, _ in clips]
        if not all(p.exists() for p in paths):
            continue
        frames = [[json.loads(line) for line in p.open()] for p in paths]

        def mean_f1(t):
            return sum(f1(select_top(fr, t, w), truth, tolerance)[2] for fr, (_, w, truth) in zip(frames, clips)) / len(clips)

        thr = max(THRESHOLDS, key=mean_f1)
        cells = []
        for fr, (_, w, truth) in zip(frames, clips):
            picks = select_top(fr, thr, w)
            lo, hi = bootstrap_f1(picks, truth, tolerance)
            cells.append(f"{f1(picks, truth, tolerance)[2]:.3f} [{lo:.2f}-{hi:.2f}]")
        rows.append((mean_f1(thr), name, thr, cells))
    for mean, name, thr, cells in sorted(rows, reverse=True):
        print(f"{name:18} {thr:5.2f} {mean:6.3f} " + " ".join(f"{c:>22}" for c in cells))


def hit_rate(pairs: list[tuple[Path, Path]], tolerance: float) -> None:
    """On labelled ball frames only: share where the strongest blob is within `tolerance`.

    Needs no "no ball" labels, so it holds on clips where those are unreliable.
    """
    import cv2

    clips = []
    for video, truth_path in pairs:
        width = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FRAME_WIDTH)
        balls = {f: b for f, b in load_ground_truth(truth_path).items() if b is not None}
        clips.append((video.stem, width, balls))
    print(f"tolerance {tolerance:g} px, share of ball frames hit by the strongest blob\n")
    print(f"{'candidate':18} {'mean':>6} " + " ".join(f"{s} ({len(b)})".rjust(18) for s, _, b in clips))
    rows = []
    for name in CANDIDATES:
        paths = [OUT / stem / f"{name}.jsonl" for stem, _, _ in clips]
        if not all(p.exists() for p in paths):
            continue
        rates = []
        for path, (_, width, balls) in zip(paths, clips):
            picks = select_top([json.loads(line) for line in path.open()], 0.0, width)
            rates.append(sum(picks[f] is not None and math.dist(picks[f][:2], b) <= tolerance for f, b in balls.items()) / len(balls))
        rows.append((sum(rates) / len(rates), name, rates))
    for mean, name, rates in sorted(rows, reverse=True):
        print(f"{name:18} {mean:6.3f} " + " ".join(f"{r:18.3f}" for r in rates))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("video", type=Path)
    run_parser.add_argument("--only", nargs="+", choices=list(CANDIDATES), default=list(CANDIDATES))
    score_parser = sub.add_parser("score")
    score_parser.add_argument("video", type=Path)
    score_parser.add_argument("truth", type=Path)
    score_parser.add_argument("--tolerance", type=float, default=10.0, help="In video pixels")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("pairs", nargs="+", help="VIDEO:GROUND_TRUTH_CSV")
    compare_parser.add_argument("--tolerance", type=float, default=10.0, help="In video pixels")
    hits_parser = sub.add_parser("hits")
    hits_parser.add_argument("pairs", nargs="+", help="VIDEO:GROUND_TRUTH_CSV")
    hits_parser.add_argument("--tolerance", type=float, default=10.0, help="In video pixels")
    args = parser.parse_args()
    if args.command == "run":
        run(args.video, args.only)
    elif args.command == "score":
        score(args.video, args.truth, args.tolerance)
    elif args.command == "compare":
        compare([tuple(map(Path, p.split(":"))) for p in args.pairs], args.tolerance)
    else:
        hit_rate([tuple(map(Path, p.split(":"))) for p in args.pairs], args.tolerance)


if __name__ == "__main__":
    main()
