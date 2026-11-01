"""Scores the ball's 3D places on a built match, with no 3D truth to hand: how far the path stays from the ball in the
picture against typical heights, the heights each action gets, and each touch's floor position found with its feet
hidden (a third of the touches at a time, so from the flights alone).

    uv run python benchmarks/ball3d/bench.py outputs/first_match outputs/courts/aspom_begles.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats.ball3d import HEIGHTS, OTHER_HEIGHT, camera_place, fit_rally, project, projection, read_sightings
from volleyball_stats.court import Calibration


def main(match: Path, court: Path) -> None:
    calibration = Calibration.load(court)
    P = projection(calibration)
    assert P is not None
    print("camera x, y, height:", camera_place(P).round(2))
    text = (match / "site" / "data.js").read_text()
    data = json.loads(text[text.index("{") : text.rindex("}") + 1])
    rallies = defaultdict(list)
    for c in data["contacts"]:
        if c["type"] != "fault" and c.get("f") is not None:
            rallies[c["rally"]].append(c)
    rallies = {k: sorted(v, key=lambda c: c["f"]) for k, v in rallies.items() if len(v) > 1}
    spans = [(cs[0]["f"], cs[-1]["f"]) for cs in rallies.values()]
    sightings = read_sightings(match / "ball.csv", calibration, spans)
    fps, width = data["fps"], (calibration.size or [3840])[0]
    fitted, guessed = [], []
    heights, hidden = defaultdict(list), defaultdict(list)
    for cs in rallies.values():
        places, errors = fit_rally(cs, sightings, P, fps, width)
        fitted += errors.tolist()
        for c, place in zip(cs, places):
            heights[c["type"]].append(place[2])
        frames = [c["f"] for c in cs]
        typical = np.array([[c["x"] or 0, c["y"] or 0, HEIGHTS.get(c["type"], OTHER_HEIGHT)] for c in cs], float)
        for k in range(len(cs) - 1):
            if frames[k + 1] > frames[k] and (frames[k + 1] - frames[k]) / fps <= 2.2:
                seen = [f for f in range(frames[k] + 1, frames[k + 1]) if f in sightings]
                if seen:
                    u = (np.array(seen) - frames[k]) / (frames[k + 1] - frames[k])
                    at = (1 - u)[:, None] * typical[k] + u[:, None] * typical[k + 1]
                    at[:, 2] += 9.81 * ((frames[k + 1] - frames[k]) / fps) ** 2 * u * (1 - u) / 2
                    guessed += np.hypot(*(project(P, at) - np.array([sightings[f] for f in seen])).T).tolist()
        for part in range(3):
            left_out = {k for k, c in enumerate(cs) if k % 3 == part and c["type"] not in ("floor", "net") and c["x"] is not None}
            if left_out:
                found, _ = fit_rally(cs, sightings, P, fps, width, left_out)
                for k in left_out:
                    hidden[cs[k]["type"]].append(float(np.hypot(found[k, 0] - cs[k]["x"], found[k, 1] - cs[k]["y"])))
    print(f"path to ball in pixels, median and 90%: typical heights {np.percentile(guessed, 50):.0f} {np.percentile(guessed, 90):.0f}, fitted {np.percentile(fitted, 50):.0f} {np.percentile(fitted, 90):.0f}")
    print("action: median height (10-90%), floor position found with feet hidden, median and 90% in m")
    for kind, values in sorted(heights.items()):
        spread = hidden.get(kind)
        found = f"{np.percentile(spread, 50):.2f} {np.percentile(spread, 90):.2f}" if spread else "-"
        print(f"  {kind:8} {np.median(values):.2f} ({np.percentile(values, 10):.2f}-{np.percentile(values, 90):.2f}), {found}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
