"""A learned order of a touch's candidates: a conditional logit over each candidate's distance to
the ball, box size, wrists, place of the ball on the box, track age and distance on the court to the
ball's 3D place (held out set by set on the first ASPOM match's 692 checked touches: 640 -> 652), trained by
`benchmarks/attribution/ranker.py` on the review's touch answers and the labelled school clips
(attribution_ranker.json beside this module). First ASPOM match, each set held out in turn: 117 of 139 answered
touches right against 107 for the rule (`attribution.wrist_order`); on the 720p school clips it
loses 2-5 of 120, so it runs on footage of MIN_HEIGHT pixels or more only.
"""

import json
from pathlib import Path

import numpy as np

WEIGHTS = Path(__file__).with_name("attribution_ranker.json")
MIN_HEIGHT = 1440
BELOW_HEAD = {"pass", "set", "dig", "relance"}
# The width's misfit says no more past WIDTH_FAR, and is read again up to WIDTH_NEAR (log of a ratio).
WIDTH_FAR, WIDTH_NEAR = 0.6, 0.2


def features(
    ball: tuple[float, float], kind: str, candidate: tuple[float, float, int], best: float, rank: int, box: tuple, tallest: float, wrist: float | None, own: bool, age: float,
    court_m: float = 0.0, width: float | None = None,
) -> list[float]:
    """One candidate's features (box heights, seconds and, `court_m`, metres on the court from the
    ball's 3D place over the nearest candidate's), each again for touches below the head; then
    `width`, the misfit of the ball's width to the candidate's place (`ballsize.Depth.misfits`, None
    when not measured), last so that weights fit without it still read their own columns."""
    x, y = ball
    h = box[3] - box[1]
    seen = wrist is not None
    base = [
        candidate[0] - best, min(candidate[0] - best, 1.0), candidate[1], float(rank == 0), float(rank), h / tallest, float(h == tallest),
        float(seen), min(wrist, 2.0) if seen else 0.0, float(seen and wrist > 0.4), (y - box[1]) / h, abs(x - (box[0] + box[2]) / 2) / h, float(own),
        min(age, 10.0) / 10, float(age < 0.5), court_m, min(court_m, 2.0),
    ]
    below = kind in BELOW_HEAD
    sized = [float(width is not None), min(width or 0.0, WIDTH_FAR), min(width or 0.0, WIDTH_NEAR)]
    return base + [v * below for v in base] + sized + [v * below for v in sized]


def fit(touches: list[tuple[np.ndarray, int]], l2: float = 0.01, steps: int = 3000, rate: float = 0.05) -> dict:
    """Weights maximising each touch's right candidate's softmax share: `touches` as (candidates'
    features, index of the right one)."""
    allx = np.vstack([x for x, _ in touches])
    mean, std = allx.mean(0), allx.std(0) + 1e-6
    xs = [(x - mean) / std for x, _ in touches]
    w = np.zeros(allx.shape[1])
    for _ in range(steps):
        grad = l2 * w
        for x, (_, y) in zip(xs, touches):
            s = x @ w
            p = np.exp(s - s.max())
            p /= p.sum()
            grad += (x.T @ p - x[y]) / len(xs)
        w -= rate * grad
    return {"w": w.tolist(), "mean": mean.tolist(), "std": std.tolist()}


def scores(model: dict, x: np.ndarray) -> np.ndarray:
    """Each candidate's score; weights fit on fewer columns read the first ones."""
    w = np.array(model["w"])
    return ((x[:, : len(w)] - np.array(model["mean"])) / np.array(model["std"])) @ w


def reads_width(model: dict) -> bool:
    """Whether `model` was fit with the ball's width among its columns."""
    return len(model["w"]) > 34


def load(path: Path = WEIGHTS) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
