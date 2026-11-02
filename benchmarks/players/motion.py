"""How natural the page's players move, from a match's tracking to `web.natural_motion`.

    uv run python benchmarks/players/motion.py outputs/first_match --video data/first_match.mp4 --court outputs/courts/aspom_begles.json

No ground truth: moves over 7 m/s are noise, the step in speed from one sample to the next is what looks jerky, and the
named player's distance to the ball at their touch (`ball3d.js` of the review's page) says whether they stay where they played,
the count of players whether a hole filled shows a body twice.
"""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from volleyball_stats import web
from volleyball_stats.court import Calibration


def report(name: str, samples: list[list[float]], data: dict, step: int, places: dict[int, list[float]]) -> None:
    seconds = step / data["fps"]
    inside = np.zeros(len(samples), bool)
    for r in data["rallies"]:
        inside[int(r["start"] / seconds) : int(r["end"] / seconds) + 1] = True
    tracks: dict[int, np.ndarray] = {}
    for k, flat in enumerate(samples):
        for person, x, y in zip(flat[0::3], flat[1::3], flat[2::3]):
            tracks.setdefault(person, np.full((len(samples), 2), np.nan))[k] = (x, y)
    speeds, steps = [], []
    for track in tracks.values():
        moves = np.diff(track, axis=0)
        speed = np.hypot(*moves.T) / seconds
        speeds.append(speed[np.isfinite(speed) & inside[:-1]])
        change = np.hypot(*np.diff(moves, axis=0).T)
        steps.append(change[np.isfinite(change) & inside[:-2]])
    speed, change = np.concatenate(speeds), np.concatenate(steps)
    near = []
    for i, c in enumerate(data["contacts"]):
        k = round(c["t"] / seconds)
        if c.get("person") in tracks and c["type"] in ("pass", "set", "dig", "attack") and i in places and k < len(samples) and np.isfinite(tracks[c["person"]][k, 0]):
            near.append(np.hypot(*(tracks[c["person"]][k] - places[i][:2])))
    shown = np.array([len(samples[k]) // 3 for k in np.flatnonzero(inside)])
    packed = sum(len(gzip.compress(f.encode(), 9)) for f in web.position_files({"step": step, "samples": samples}, data["fps"]))
    print(f"{name:8} over 7 m/s {100 * (speed > 7).mean():.2f}%, speed p50 {np.median(speed):.2f} p99 {np.percentile(speed, 99):.1f} m/s, "
          f"speed step p99 {np.percentile(change, 99):.2f} m, to the ball p50 {np.median(near):.2f} p90 {np.percentile(near, 90):.2f} m ({len(near)} touches), "
          f"12 players on {100 * (shown == 12).mean():.0f}% of moments, over on {100 * (shown > 12).mean():.0f}%, under on {100 * (shown < 12).mean():.0f}%, {packed / 1000:.0f} KB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    args = parser.parse_args()
    data, players = web.match_data(args.match, args.video, Calibration.load(args.court))
    text = (args.match / "review" / "ball3d.js").read_text()
    flat = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
    places = {int(flat[k]): np.array(flat[k + 1 : k + 4]) for k in range(0, len(flat), 4)}
    report("tracked", players["samples"], data, players["step"], places)
    report("natural", web.natural_motion(players["samples"], players["step"] / data["fps"], {int(person): q["team"] for person, q in data["people"].items()}), data, players["step"], places)


if __name__ == "__main__":
    main()
