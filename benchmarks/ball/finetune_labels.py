"""Pseudo-labels for the ball fine-tuning set, from the teachers' candidates and the reviewed touches.

Between two consecutive reviewed touches the ball flies free: a smooth path in the image. Each
flight gets a robust (RANSAC) polynomial path through the candidates of both teachers; frames then
read `ball` (an inlier candidate, the 1024 teacher's position preferred), `unsure` (the path is
accepted, no candidate on it: the ball may be hidden, and the pipeline's pick elsewhere turns it `skip`) or `skip` (path refused, a guard around the
touches, outside the flights); `offscreen` is `unsure` where the path leaves the 4K frame. Dead-time clips take the pretrained 512 model's pick (`clip_ball`) or
`clip_none`. Writes MATCH/labels.csv and MATCH/label_stats.json.

    uv run python benchmarks/ball/finetune_labels.py MATCH
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from volleyball_stats import ball

sys.path.insert(0, str(Path(__file__).parent))
import finetune_data as data  # noqa: E402

TOL = 45.0
GUARD = 6
MIN_SHARE = 0.4
MIN_TRAVEL = 100.0
ITERATIONS = 300
FIT_SPLIT = 40
CUBIC_FROM = 25
EXTRAPOLATE = 10
NATIVE_H = 2160
PICK = ball.THRESHOLD[1]
rng = np.random.default_rng(0)


def vander(t: np.ndarray, degree: int) -> np.ndarray:
    return np.stack([t**k for k in range(degree + 1)], axis=1)


def refit(cand: np.ndarray, t: np.ndarray, coef: np.ndarray, degree: int, tol: float, rounds: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Least squares on the candidates within `tol` of the path (the nearest per frame), repeated."""
    inside = near(cand, t, coef, degree, tol)
    for _ in range(rounds):
        if inside.sum() < degree + 1:
            break
        v = vander(t[inside], degree)
        coef = np.stack([np.linalg.lstsq(v, cand[inside, c], rcond=None)[0] for c in (3, 4)], axis=1)
        inside = near(cand, t, coef, degree, tol)
    return coef, inside


def near(cand: np.ndarray, t: np.ndarray, coef: np.ndarray, degree: int, tol: float) -> np.ndarray:
    pred = vander(t, degree) @ coef
    return np.hypot(cand[:, 3] - pred[:, 0], cand[:, 4] - pred[:, 1]) <= tol


def ransac(cand: np.ndarray, t: np.ndarray, degree: int, tol: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Best path (coefficients per axis, inlier mask) over candidates with columns frame, teacher, rank, x, y, peak."""
    frames = np.unique(cand[:, 0])
    if len(frames) < degree + 1:
        return None
    best, best_score = None, 0
    parts = np.array_split(frames, degree + 1)
    for _ in range(ITERATIONS):
        picks = [rng.choice(p) for p in parts]
        rows = [rng.choice(np.nonzero(cand[:, 0] == f)[0]) for f in picks]
        v = vander(t[rows], degree)
        try:
            coef = np.linalg.solve(v, cand[rows][:, 3:5])
        except np.linalg.LinAlgError:
            continue
        inside = near(cand, t, coef, degree, tol)
        score = len(np.unique(cand[inside, 0]))
        if score > best_score:
            best, best_score = coef, score
    if best is None:
        return None
    return refit(cand, t, best, degree, tol)


def chosen(cand: np.ndarray, t: np.ndarray, coef: np.ndarray, degree: int, inside: np.ndarray) -> dict[int, int]:
    """Per frame, the row on the path: the 1024 teacher's nearest, else the 512 teacher's."""
    pred = vander(t, degree) @ coef
    dist = np.hypot(cand[:, 3] - pred[:, 0], cand[:, 4] - pred[:, 1])
    pick: dict[int, int] = {}
    for row in np.nonzero(inside)[0]:
        f = int(cand[row, 0])
        key = (-cand[row, 1], dist[row])
        if f not in pick or key < (-cand[pick[f], 1], dist[pick[f]]):
            pick[f] = row
    return pick


def accepted(first: int, last: int, frames: list[int], coef: np.ndarray, degree: int, fps: float) -> bool:
    frames = [f for f in frames if first <= f <= last]
    length = last - first + 1
    if len(frames) < MIN_SHARE * length:
        return False
    quarters = {min(3, 4 * (f - first) // length) for f in frames}
    if len(quarters) < 3:
        return False
    t = (np.arange(min(frames), max(frames) + 1) - first) / fps
    return bool(np.hypot(*np.ptp(vander(t, degree) @ coef, axis=0)) >= MIN_TRAVEL)


def fit_flight(cand: np.ndarray, first: int, last: int, fps: float, degrees=None, depth: int = 0) -> list[dict]:
    """Paths covering the flight: one accepted fit, else its two halves (if long enough). Each:
    first, last, degree, coef, pick (frame -> candidate row), cand, t."""
    if not len(cand):
        return []
    best = None
    t = (cand[:, 0] - first) / fps
    degrees = degrees or ((3,) if last - first + 1 >= CUBIC_FROM else (2,))
    for degree in degrees:
        result = ransac(cand, t, degree, TOL)
        if result is None:
            continue
        coef, inside = result
        pick = chosen(cand, t, coef, degree, inside)
        if accepted(first, last, list(pick), coef, degree, fps):
            best = dict(first=first, last=last, degree=degree, coef=coef, pick=pick, cand=cand, t=t)
    if best:
        return [best]
    if last - first + 1 >= 2 * FIT_SPLIT and depth < 2:
        mid = (first + last) // 2
        halves = [(first, mid), (mid + 1, last)]
        return [p for a, b in halves for p in fit_flight(cand[(cand[:, 0] >= a - 5) & (cand[:, 0] <= b + 5)], a, b, fps, degrees, depth + 1)]
    return []


def load_cand(path: Path) -> tuple[int, int, np.ndarray]:
    z = np.load(path)
    return int(z["first"]), int(z["last"]), z["cand"]


def pipeline_pick(cand: np.ndarray, frame: int) -> np.ndarray | None:
    rows = cand[(cand[:, 0] == frame) & (cand[:, 1] == 0) & (cand[:, 2] == 0) & (cand[:, 5] >= PICK)]
    return rows[0] if len(rows) else None


def at(p: dict, f: int) -> np.ndarray:
    return (vander(np.array([(f - p["first"]) / p["fps"]]), p["degree"]) @ p["coef"])[0]


def label_rally(rally: dict, cand: np.ndarray, first: int, last: int, fps: float) -> tuple[list[tuple], dict, list[tuple]]:
    """Rows (frame, kind, x, y, flight, teacher, residual, also512) for every stored frame."""
    touches = sorted(t["frame"] for t in rally["touches"])
    bounds = touches + [rally["end_frame"]]
    best: dict[int, tuple] = {}
    paths_of: dict[int, list[dict]] = {}
    flights = accepted_n = 0
    for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
        if b <= a:
            continue
        flights += 1
        a, b = max(a, first), min(b, last)
        paths = fit_flight(cand[(cand[:, 0] >= a - 3) & (cand[:, 0] <= b + 3)], a, b, fps)
        accepted_n += bool(paths)
        for p in paths:
            p["fps"] = fps
            for f in range(p["first"], p["last"] + 1):
                px, py = at(p, f)
                if f in p["pick"]:
                    r = p["cand"][p["pick"][f]]
                    same = (cand[:, 0] == f) & (cand[:, 1] == 0) & (cand[:, 2] == 0) & (cand[:, 5] >= PICK) & (np.hypot(cand[:, 3] - r[3], cand[:, 4] - r[4]) <= TOL)
                    row = (f, "ball", int(r[3]), int(r[4]), k, "1024" if r[1] else "512", float(np.hypot(r[3] - px, r[4] - py)), bool(same.any()))
                elif min(f - a, b - f) >= GUARD and min(p["pick"]) - EXTRAPOLATE <= f <= max(p["pick"]) + EXTRAPOLATE:
                    inside = 0 <= px < data.NATIVE_W and 0 <= py < NATIVE_H
                    row = (f, "unsure" if inside else "offscreen", int(round(px)), int(round(py)), k, "path", 0.0, False)
                else:
                    continue
                old = best.get(f)
                if old is None or (row[1] == "ball" and (old[1] != "ball" or row[6] < old[6])):
                    best[f] = row
                    paths_of[f] = [p]
    off = off_total = 0
    offs = []
    for f, row in list(best.items()):
        pk = pipeline_pick(cand, f)
        if pk is not None:
            px, py = at(paths_of[f][0], f)
            off_total += 1
            if np.hypot(pk[3] - px, pk[4] - py) > TOL:
                off += 1
                offs.append((f, int(pk[3]), int(pk[4]), float(pk[5]), int(round(px)), int(round(py))))
                if row[1] in ("unsure", "offscreen"):
                    best[f] = (f, "skip", "", "", -1, "", "", False)
    rows = [best.get(f, (f, "skip", "", "", -1, "", "", False)) for f in range(first, last + 1)]
    return rows, dict(flights=flights, accepted=accepted_n, off=off, off_total=off_total), offs


def label_clip(cand: np.ndarray, first: int, last: int) -> list[tuple]:
    out = []
    for f in range(first, last + 1):
        pk = pipeline_pick(cand, f)
        out.append((f, "clip_ball", int(pk[3]), int(pk[4]), -2, "512", 0.0, True) if pk is not None else (f, "clip_none", "", "", -2, "", "", False))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    _, truth = data.match_info(args.match)
    fps = truth["fps"]
    rallies = {f"rally_{r['key']}": r for r in truth["rallies"]}
    folder = data.OUT / args.match
    names = sorted(p.stem for p in folder.glob("*.npz"))
    stats = dict(frames=0, flights=0, accepted=0, off=0, off_total=0, ball=0, unsure=0, offscreen=0, skip=0, ball_with512=0, ball_only1024=0, clip_ball=0, clip_none=0, clip_frames=0, rallies=0)
    off_rows: list[tuple] = []
    with (folder / "labels.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["unit", "frame", "kind", "x", "y", "flight", "teacher", "residual", "also512"])
        for name in names[: args.limit]:
            path = folder / f"{name}.npz"
            if not path.exists():
                continue
            first, last, cand = load_cand(path)
            if name.startswith("rally"):
                rows, s, offs = label_rally(rallies[name], cand, first, last, fps)
                off_rows += [(name, *o) for o in offs]
                stats["rallies"] += 1
                for k in ("flights", "accepted", "off", "off_total"):
                    stats[k] += s[k]
            else:
                rows = label_clip(cand, first, last)
            for r in rows:
                writer.writerow([name, r[0], r[1], r[2], r[3], r[4], r[5], f"{r[6]:.1f}" if r[6] != "" else "", int(r[7])])
                stats["frames" if name.startswith("rally") else "clip_frames"] += 1
                stats[r[1]] += 1
                if r[1] == "ball":
                    stats["ball_only1024" if r[5] == "1024" and not r[7] else "ball_with512"] += 1
    with (folder / "offpath.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["unit", "frame", "x", "y", "peak", "path_x", "path_y"])
        writer.writerows(off_rows)
    (folder / "label_stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
