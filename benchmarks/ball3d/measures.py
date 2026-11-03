"""Scores a serve's speed and a player's attack height on a built match, with no radar or tape measure to hand: what the
picture's scale gives for gravity and the players' heads, how far each measure moves under what could be wrong (contact
frames, sightings, feet), and whether a player's measures agree with each other.

    uv run python benchmarks/ball3d/measures.py outputs/2026-10-29-aspom-1-vs-aspom-2 outputs/courts/aspom_begles.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats.ball3d import attack_height, camera_place, fit_rally, projection, read_sightings, serve_speed
from volleyball_stats.court import Calibration, undistort

LEAST_SERVES, LEAST_ATTACKS = 5, 5


def main(match: Path, court: Path) -> None:
    calibration = Calibration.load(court)
    P = projection(calibration)
    assert P is not None
    width = (calibration.size or [3840])[0]
    text = (match / "site" / "data.js").read_text()
    data = json.JSONDecoder().raw_decode(text[text.index("{") :])[0]
    fps = data["fps"]
    rallies = defaultdict(list)
    for c in data["contacts"]:
        if c["type"] != "fault" and c.get("f") is not None:
            rallies[c["rally"]].append(c)
    rallies = {k: sorted(v, key=lambda c: c["f"]) for k, v in rallies.items() if len(v) > 1}
    margin = round(0.8 * fps)
    sightings = read_sightings(match / "ball.csv", calibration, [(cs[0]["f"] - margin, cs[-1]["f"] + margin) for cs in rallies.values()])
    rng = np.random.default_rng(1)

    def jittered(c: dict, frames: int) -> dict:
        return {**c, "f": c["f"] + int(rng.integers(-frames, frames + 1))}

    def speeds(seen=sightings, edit=lambda c: c) -> dict:
        return {
            (k, i): v
            for k, cs in rallies.items()
            for i, c in enumerate(cs[:-1])
            if c["type"] == "serve" and (v := serve_speed(edit(c), edit(cs[i + 1]), seen, P, fps, width)) is not None
        }

    def heights(seen=sightings, edit=lambda c: c) -> dict:
        out = {}
        for k, cs in rallies.items():
            changed = [edit(c) for c in cs]
            places = fit_rally(changed, seen, P, fps, width)[0]
            for i, c in enumerate(changed):
                if c["type"] == "attack" and (h := attack_height(c, places[i], seen, fps)) is not None:
                    out[(k, i)] = h
        return out

    def people(values: dict, least: int) -> dict:
        by = defaultdict(list)
        for (k, i), v in values.items():
            if rallies[k][i].get("person") is not None:
                by[rallies[k][i]["person"]].append(v)
        return {p: v for p, v in by.items() if len(v) >= least}

    def agreement(by: dict) -> str:
        odd, even = [np.median(v[0::2]) for v in by.values()], [np.median(v[1::2]) for v in by.values()]
        return f"{len(by)} players, odd and even tries correlate {np.corrcoef(odd, even)[0, 1]:.2f}, spread between players {np.std([np.median(v) for v in by.values()], ddof=1):.2f}"

    fewer = {f: v for f, v in sightings.items() if f % 3}
    moved = lambda dy: lambda c: {**c, "y": c["y"] + dy} if c.get("y") is not None else c

    serves = speeds()
    told = sum(c["type"] == "serve" for cs in rallies.values() for c in cs)
    print(f"serves measured {len(serves)} of {told}; km/h 5, 50, 95%, most: {np.percentile(list(serves.values()), [5, 50, 95, 100]).round(1)}")
    for name, other in (("contact frames +-5", speeds(edit=lambda c: jittered(c, 5))), ("a third fewer sightings", speeds(fewer)), ("feet y +1 m", speeds(edit=moved(1))), ("feet y -1 m", speeds(edit=moved(-1)))):
        change = np.array([100 * (other[x] - serves[x]) / serves[x] for x in serves if x in other])
        print(f"  {name:24} kept {len(other):3}, moves {np.median(abs(change)):.1f}% median, {np.percentile(abs(change), 90):.1f}% at 90%, bias {np.median(change):+.1f}%")
    print(f"  {agreement(people(serves, LEAST_SERVES))}")

    attacks = heights()
    told = sum(c["type"] == "attack" for cs in rallies.values() for c in cs)
    print(f"attacks measured {len(attacks)} of {told}; m 5, 50, 95%: {np.percentile(list(attacks.values()), [5, 50, 95]).round(2)}")
    by_person = people(attacks, LEAST_ATTACKS)
    typical = {p: np.median(v) for p, v in by_person.items()}
    for name, other in (("contact frames +-2", heights(edit=lambda c: jittered(c, 2))), ("a third fewer sightings", heights(fewer)), ("feet y +1 m", heights(edit=moved(1)))):
        touch = np.array([other[x] - attacks[x] for x in attacks if x in other])
        player = np.array([np.median(v) - typical[p] for p, v in people(other, LEAST_ATTACKS).items() if p in typical])
        print(f"  {name:24} kept {len(other):3}; one attack moves {np.median(abs(touch)):.2f} m median, {np.percentile(abs(touch), 90):.2f} at 90%; a player's median {np.median(abs(player)):.2f}, at most {abs(player).max():.2f}")
    print(f"  {agreement(by_person)}")

    # The picture's scale, on what is known without a measure of the ball: heads and gravity.
    inv = np.linalg.inv(P[:, :3])
    origin = camera_place(P) * np.array([1, 1, -1])

    def height_at(pixels: np.ndarray, y: np.ndarray) -> np.ndarray:
        rays = np.c_[pixels, np.ones(len(pixels))] @ inv.T
        return -(origin[2] + (y - origin[1]) / rays[:, 1] * rays[:, 2])

    tracks = {}
    with open(match / "actions.csv") as f:
        next(f)
        for line in f:
            row = line.strip().split(",")
            tracks[int(row[0])] = row[5]
    heads = defaultdict(list)
    with open(match / "players.csv") as f:
        next(f)
        for line in f:
            if int(line[: line.index(",")]) % 25 == 0:
                row = line.strip().split(",")
                if row[1] and row[10] and row[11] and abs(float(row[10])) <= 9 and abs(float(row[11])) <= 4.5:
                    heads[row[1]].append(((float(row[3]) + float(row[5])) / 2, float(row[4]), float(row[11])))
    tall = {}
    for track, seen in heads.items():
        seen = np.array(seen)
        tall[track] = height_at(undistort(seen[:, :2], calibration.lens) if calibration.lens else seen[:, :2], seen[:, 2])
    print(f"heads on court, m 10, 50, 90%: {np.percentile(np.concatenate(list(tall.values())), [10, 50, 90]).round(2)}")
    samples = defaultdict(list)
    for cs in rallies.values():
        for c in cs:
            if c.get("person") is not None and tracks.get(c["f"]) in tall:
                samples[c["person"]].extend(tall[tracks[c["f"]]])
    stature = {p: np.median(v) for p, v in samples.items() if len(v) >= 40}
    shared = [p for p in typical if p in stature]
    print(f"  a player's attack height against their own head: correlate {np.corrcoef([typical[p] for p in shared], [stature[p] for p in shared])[0, 1]:.2f} over {len(shared)} players, above the head {np.median([typical[p] - stature[p] for p in shared]):.2f} m")

    gravity = defaultdict(list)
    for cs in rallies.values():
        for a, b in zip(cs, cs[1:]):
            frames = [f for f in range(a["f"] + 3, b["f"] - 2) if f in sightings]
            flight = (b["f"] - a["f"]) / fps
            if a["y"] is None or b["y"] is None or a["x"] is None or b["x"] is None or not 0.5 < flight <= 2.2 or len(frames) < max(20, 0.7 * (b["f"] - a["f"])):
                continue
            pixels = np.array([sightings[f] for f in frames])
            along = (np.array(frames) - a["f"]) / (b["f"] - a["f"])
            found = height_at(pixels, a["y"] + along * (b["y"] - a["y"]))
            gravity[a["type"]].append(-2 * np.polyfit(np.array(frames) / fps, found, 2)[0])
    print("gravity found, m/s2:", {k: round(float(np.median(v)), 2) for k, v in sorted(gravity.items()) if len(v) >= 8})


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
