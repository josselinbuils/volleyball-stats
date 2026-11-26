"""Score the automatic zoom (framing.camera, which the video's copies are cut by) on analysed matches.

    uv run python benchmarks/framing/bench.py [--slide | --no-spring] [MATCH ...]

Each MATCH (outputs/matches/ names; every one with a review page without any) is read from its review page (data.js's
rallies and touches, video.js) and players.csv. During the rallies, every 0.2 s: the zoom shown, the share of moments
showing every player on the court (within 1 m of its lines) whole, and the share showing the ball where it is seen. The
views and the camera are made again by the code as it stands. --no-spring scores the views averaged without the
spring that follows them, as before 16 Nov; --slide plays the ball as the page did before 15 Nov: the view slid to keep
it in, rather than widened (without the spring).
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

from volleyball_stats import framing, web
from volleyball_stats.web import page_data

# The page's zoom.ts: the ball's place averaged over SMOOTH_S, kept EDGE inside the view, the views averaged over AHEAD_S.
SMOOTH_S, EDGE, AHEAD_S, AHEAD_STEPS = 0.5, 0.15, 1.0, 20
STEP_S, COURT = 0.2, (10.0, 5.5)
SLIDE = "--slide" in sys.argv
NO_SPRING = SLIDE or "--no-spring" in sys.argv


def ball_near(samples: np.ndarray, t: float) -> tuple[float, float] | None:
    near = samples[(samples[:, 0] >= t - SMOOTH_S) & (samples[:, 0] <= t + SMOOTH_S)]
    return (float(near[:, 1].mean()), float(near[:, 2].mean())) if len(near) else None


def frame_at(views: np.ndarray, t: float, ball: tuple[float, float] | None) -> tuple[float, float, float]:
    """zoom.ts's frameAt: the view's centre and width."""
    k = np.searchsorted(views[:, 0], t, side="right") - 1
    _, x, y, w = views[max(k, 0)]
    if not SLIDE and ball is not None:
        # Widened to hold the ball EDGE inside, the players' view in it.
        bx, by = ball
        m = EDGE * w
        x1, y1, x2, y2 = min(x, bx - m), min(y, by - m), max(x + w, bx + m), max(y + w, by + m)
        w2 = min(1.0, max(x2 - x1, y2 - y1))
        x = min(1 - w2, max(0.0, min(x1, max(x2 - w2, (x1 + x2 - w2) / 2))))
        y = min(1 - w2, max(0.0, min(y1, max(y2 - w2, (y1 + y2 - w2) / 2))))
        return x + w2 / 2, y + w2 / 2, w2

    def keep(start: float, at: float | None) -> float:
        moved = start if at is None else min(at - EDGE * w, max(at + EDGE * w - w, start))
        return min(1 - w, max(0.0, moved)) + w / 2

    return keep(x, ball and ball[0]), keep(y, ball and ball[1]), w


def shown_at(views: np.ndarray, samples: np.ndarray, t: float) -> tuple[float, float, float]:
    """smoothFrameAt: frame_at averaged over AHEAD_S around `t`."""
    found = [frame_at(views, a, ball_near(samples, a)) for a in t + AHEAD_S * (2 * np.arange(AHEAD_STEPS + 1) / AHEAD_STEPS - 1)]
    cx, cy, zoom = (sum(v) / len(found) for v in zip(*[(x, y, 1 / w) for x, y, w in found]))
    return cx, cy, 1 / zoom


def drawn(match: Path) -> Path:
    """The review page's video.js, ball.js on a page built before 16 Nov."""
    new = match / "review" / web.VIDEO_JS
    return new if new.exists() else match / "review" / "ball.js"


def score(match: Path) -> dict:
    data = page_data(match / "review")
    text = drawn(match).read_text(encoding="utf-8")
    samples = np.array(json.loads(text[text.index("{") : text.rindex("}") + 1])["samples"], dtype=float).reshape(-1, 3)
    fps = data["fps"]
    width, height = web.decode.size(Path(json.loads((match / "source.json").read_text(encoding="utf-8"))["video"]))
    boxes = framing.read_boxes(match / "players.csv", (width, height), fps)
    views = np.array(framing.views(boxes, data["rallies"], [c for c in data["contacts"] if c["type"] not in web.NO_PLAYER], samples))
    # The people on the court, by time.
    on: dict[float, list] = {}
    step = max(1, round(framing.STEP_S * fps))
    with open(match / "players.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            frame = int(row["frame"])
            if frame % step or row["court_x"] == "" or abs(float(row["court_x"])) > COURT[0] or abs(float(row["court_y"])) > COURT[1]:
                continue
            on.setdefault(round(frame / fps, 1), []).append((float(row["x1"]) / width, float(row["y1"]) / height, float(row["x2"]) / width, float(row["y2"]) / height))
    spans = framing.camera_spans(framing.camera(views.tolist(), samples, data["duration"], framing.bounces(web.line_calls(data), samples, data["rallies"])))
    zooms, players, balls = [], [], []
    for rally in data["rallies"]:
        for t in np.arange(rally["start"], rally["end"], STEP_S):
            if NO_SPRING:
                cx, cy, w = shown_at(views, samples, t)
            else:
                cx, cy, zoom = framing.camera_at(spans, np.array([t]))[0]
                w = 1 / zoom
            x1, y1, x2, y2 = cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2
            zooms.append(1 / w)
            people = on.get(round(round(t / framing.STEP_S) * framing.STEP_S, 1), [])
            if people:
                players.append(all(a >= x1 and b >= y1 and c <= x2 and d <= y2 for a, b, c, d in people))
            near = samples[np.abs(samples[:, 0] - t) <= 0.05]
            if len(near):
                bx, by = near[0, 1:]
                balls.append(x1 <= bx <= x2 and y1 <= by <= y2)
    return {"zoom": float(np.median(zooms)), "players": float(np.mean(players)), "ball": float(np.mean(balls)), "views": len(views)}


def main() -> None:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(p.name for p in Path("outputs/matches").iterdir() if drawn(p).exists() and (p / "players.csv").exists())
    found = {name: score(Path("outputs/matches") / name) for name in names}
    for name, s in found.items():
        print(f"{name}: zoom ×{s['zoom']:.2f}  all players whole {s['players']:.1%}  ball {s['ball']:.1%}  ({s['views']} views)")
    print(f"mean: zoom ×{np.mean([s['zoom'] for s in found.values()]):.2f}  players {np.mean([s['players'] for s in found.values()]):.1%}  ball {np.mean([s['ball'] for s in found.values()]):.1%}")


if __name__ == "__main__":
    main()
