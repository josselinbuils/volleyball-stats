"""Score the teams step against hand-labelled jersey colours.

    uv run --group bench python benchmarks/teams/bench.py CLIP ... [--sweep]

Each CLIP reads data/CLIP.mp4, its player tracks (outputs/players/CLIP_players.csv, else
outputs/CLIP/players.csv) and benchmarks/teams/ground_truth/CLIP.csv: per rally window, the jersey
colour on each side of the net. Scores, pooled over the clips given:
- side map: rallies whose left team has the labelled jersey colour, and changes of ends found;
- colour vs side: player frames whose torso colour group (2-means) plays on the side its group holds
  in that rally (players never cross the net, so a disagreement is a colour error: liberos, mixed
  crops, mixed kits);
- tracks: tracks matched to the identity labels of benchmarks/players/ground_truth/CLIP_sequence.csv
  (W* white, N* navy) whose team has the label's colour, colour group alone then with the side;
- attribution: attribution.attribute's typed contacts (as benchmarks/attribution) with the toucher
  searched among players.py's sides, the colour groups, or the teams;
- sets: the set starts found.
--sweep compares samples per track and torso boxes on colour vs side. --mixed scores the side map
again with mixed kits: each player of the clip's identities.csv (outputs/CLIP/) gets a random shirt
and shorts colour, over 5 seeds. --same does it with one kit for every player of both teams (two
teams of one club).
"""

import argparse
import csv
import importlib.util
from collections import Counter
from pathlib import Path

import numpy as np

from volleyball_stats import actions, attribution, contacts, teams
from volleyball_stats.players import Row

FPS = 29.97
TOLERANCE = 20
spec = importlib.util.spec_from_file_location("attribution_bench", Path(__file__).parents[1] / "attribution" / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def players(clip: str) -> list[Row]:
    path = Path(f"outputs/players/{clip}_players.csv")
    return attribution.read_players(path if path.exists() else Path(f"outputs/{clip}/players.csv"))


def truth(clip: str) -> list[dict]:
    with open(f"benchmarks/teams/ground_truth/{clip}.csv") as f:
        return list(csv.DictReader(f))


def two_means(colours: dict[int, np.ndarray], weights: dict[int, float], rounds: int = 20) -> dict[int, int]:
    """Group (0 or 1) of each colour by 2-means weighted by `weights`, started from the darker and
    the lighter half by weight; group 0 is the darker."""
    tracks = sorted(colours, key=lambda t: colours[t][0])
    x = np.array([colours[t] for t in tracks], float)
    w = np.array([weights[t] for t in tracks], float)
    labels = (np.cumsum(w) > w.sum() / 2).astype(int)
    for _ in range(rounds):
        if labels.min() == labels.max():
            break
        centres = np.array([np.average(x[labels == k], axis=0, weights=w[labels == k]) for k in (0, 1)])
        labels = np.argmin(((x[:, None] - centres[None]) ** 2).sum(axis=2), axis=1)
    if labels.max() and x[labels == 0, 0].mean() > x[labels == 1, 0].mean():
        labels = 1 - labels
    return dict(zip(tracks, labels.tolist()))


def colour_lefts(rows: list[Row], windows: list[tuple[int, int]], group: dict[int, int]) -> list[int | None]:
    """Per rally window, the colour group on the left: the one with the most frames of its tracks on
    the left half plus frames of the other group's on the right."""
    out: list[int | None] = []
    frames = np.array([r.frame for r in rows])
    left = np.array([r.court[0] < 0 for r in rows])
    groups = np.array([group.get(r.track, -1) for r in rows])
    for start, end in windows:
        inside = (frames >= start) & (frames <= end) & (groups >= 0)
        votes = [(groups[inside] == g) == left[inside] for g in (0, 1)]
        zero, one = int(votes[0].sum()), int(votes[1].sum())
        out.append(None if zero == one else 0 if zero > one else 1)
    return out


def colour_vs_side(rows: list[Row], windows: list[tuple[int, int]], group: dict[int, int], left: list[int | None]) -> tuple[int, int]:
    """Player frames inside the rallies whose colour group holds their side, and all of them."""
    agree = total = 0
    for (start, end), g in zip(windows, left):
        for r in rows:
            if start <= r.frame <= end and r.track in group and g is not None:
                total += 1
                agree += (group[r.track] == g) == (r.court[0] < 0)
    return agree, total


def track_truth(clip: str, rows: list[Row]) -> dict[int, str]:
    """Labelled colour (white, navy) of each track matched to the identity labels, by majority."""
    path = Path(f"benchmarks/players/ground_truth/{clip}_sequence.csv")
    if not path.exists():
        return {}
    by_frame: dict[int, list[Row]] = {}
    for r in rows:
        by_frame.setdefault(r.frame, []).append(r)
    votes: dict[int, Counter] = {}
    with open(path) as f:
        labels = list(csv.DictReader(f))
    for frame in sorted({int(l["frame"]) for l in labels}):
        here = [l for l in labels if int(l["frame"]) == frame]
        pairs = sorted((float(np.hypot(r.feet[0] - float(l["x"]), r.feet[1] - float(l["y"]))), i, j) for i, l in enumerate(here) for j, r in enumerate(by_frame.get(frame, [])))
        used_l, used_r = set(), set()
        for d, i, j in pairs:
            if d <= TOLERANCE and i not in used_l and j not in used_r:
                used_l.add(i)
                used_r.add(j)
                track = by_frame[frame][j].track
                votes.setdefault(track, Counter())["white" if here[i]["player"].startswith("W") else "navy"] += 1
    return {t: v.most_common(1)[0][0] for t, v in votes.items()}


def attribution_hits(clip: str, rows: list[Row], side_of: dict[int, str]) -> tuple[int, int, int]:
    """Right typed contacts on the labelled contacts and on the detected ones, with the toucher
    searched among the tracks given as `side_of` (track -> side of the net)."""
    rows = [Row(r.frame, r.track, r.box, r.conf, r.feet, r.court, side_of.get(r.track, "")) for r in rows]
    cal, gap = bench.calibration(), round(attribution.GAP_S * FPS)
    by_track = attribution.tracks(rows)
    touchers = bench.load_touchers(Path(f"benchmarks/attribution/ground_truth/{clip}.csv"))
    track = contacts.read_track(Path(f"outputs/ball/{clip}_ball.csv"))
    filled = contacts.interpolate(track)
    found, crossings = contacts.detect(track, FPS, bench.NET_X)
    on_truth, detected, labels, matched = [], [], {}, {}
    for rally in bench.load_contacts(Path(f"benchmarks/contacts/ground_truth/{clip}.csv")):
        labels |= rally["contacts"]
        given = [(f, round(filled[f, 0]), round(filled[f, 1])) for f in rally["contacts"]]
        on_truth += [(f, x, y, rally["contacts"][f], side) for f, x, y, _, side in actions.classify_rally(given, rally["net"], FPS, bench.NET_X, cal)]
        inside = [c for c in found if rally["start"] <= c[0] <= rally["end"]]
        typed = actions.classify_rally(inside, [c for c in crossings if rally["start"] <= c <= rally["end"]], FPS, bench.NET_X, cal)
        detected += typed
        matched |= bench.pair([t[0] for t in typed], list(rally["contacts"]))
    a = dict(zip([t[0] for t in on_truth], attribution.attribute(on_truth, rows, FPS)))
    b = dict(zip([t[0] for t in detected], attribution.attribute(detected, rows, FPS)))

    def hit(f: int, k: int | None) -> bool:
        return bench.right(k, touchers[f], None if k is None else attribution.box_at(by_track[k][1], f, gap))

    typed_frames = [f for f, kind in labels.items() if kind and touchers[f]["toucher"] != "none"]
    return sum(hit(f, a[f]) for f in typed_frames), sum(f in matched and hit(f, b[matched[f]]) for f in typed_frames), len(typed_frames)


def score(clips: list[str]) -> None:
    totals: Counter = Counter()
    for clip in clips:
        rows, labelled = players(clip), truth(clip)
        windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in labelled]
        looks, _ = teams.sample(Path(f"data/{clip}.mp4"), rows)
        lengths = {t: len(r) for t, r in teams.by_track(rows).items()}
        group = two_means({t: look[:3] for t, look in looks.items()}, lengths)
        found = teams.assign(Path(f"data/{clip}.mp4"), rows, windows, FPS)
        name = {t: teams.hex_name(c) for t, c in found.colours.items()}
        left = [name[g] if g else None for g in found.left]
        right_map = sum(l == r["left"] for l, r in zip(left, labelled))
        changes = sum(a["left"] != b["left"] for a, b in zip(labelled, labelled[1:]))
        found_changes = sum(a != b for a, b in zip(left, left[1:]))
        agree, frames = colour_vs_side(rows, windows, group, colour_lefts(rows, windows, group))
        print(f"{clip}: side map {right_map}/{len(labelled)}, changes of ends {found_changes} found / {changes} labelled; colour vs side {agree}/{frames} ({agree / max(1, frames):.3f}); teams {name}")
        totals.update(rallies=len(labelled), right_map=right_map, agree=agree, frames=frames)

        # A colour group stands for the team holding most of its tracks.
        group_team = {g: Counter(found.tracks[t] for t in group if group[t] == g).most_common(1)[0][0] for g in set(group.values())}
        labels = track_truth(clip, rows)
        if labels:
            colour_only = sum(name[group_team[group[t]]] == c for t, c in labels.items())
            final = sum(name[found.tracks[t]] == c for t, c in labels.items())
            wrong = [t for t, c in labels.items() if name[group_team[group[t]]] != c]
            print(f"  tracks: colour alone {colour_only}/{len(labels)}, with the side {final}/{len(labels)}; colour misses: tracks {wrong}")
            totals.update(tracks=len(labels), colour_only=colour_only, final=final)

        if Path(f"benchmarks/attribution/ground_truth/{clip}.csv").exists():
            # ponytail: the teams keep their ends in the three attribution clips, so a team's side is
            # the one it holds at the first rally.
            def side(team: int) -> str:
                return "left" if team == found.left[0] else "right"

            variants = {
                "players.py sides": {t: r[0].team for t, r in teams.by_track(rows).items()},
                "colour groups": {t: side(group_team[g]) for t, g in group.items()},
                "teams": {t: side(team) for t, team in found.tracks.items()},
            }
            for label, side_of in variants.items():
                on_truth, on_detected, n = attribution_hits(clip, rows, side_of)
                print(f"  attribution, {label}: truth {on_truth}/{n}, detected {on_detected}/{n}")
                totals.update({f"{label} truth": on_truth, f"{label} detected": on_detected})
            totals.update(contacts=n)

        starts = teams.set_starts(windows, found.left, FPS)
        print(f"  set starts: {[teams.clock(s) for s in starts]}")
    print(f"\nall: side map {totals['right_map']}/{totals['rallies']}, colour vs side {totals['agree']}/{totals['frames']} ({totals['agree'] / max(1, totals['frames']):.3f})")
    if totals["tracks"]:
        print(f"tracks: colour alone {totals['colour_only']}/{totals['tracks']}, with the side {totals['final']}/{totals['tracks']}")
    if totals["contacts"]:
        for label in ("players.py sides", "colour groups", "teams"):
            print(f"attribution, {label}: truth {totals[f'{label} truth']}/{totals['contacts']}, detected {totals[f'{label} detected']}/{totals['contacts']}")


def sweep(clips: list[str]) -> None:
    """Colour vs side for samples per track and torso boxes."""
    for samples in (2, 4, 8, 16):
        for box in ((0.3, 0.7, 0.2, 0.45), (0.25, 0.75, 0.15, 0.5), (0.35, 0.65, 0.25, 0.4), (0.2, 0.8, 0.1, 0.6)):
            teams.TORSO = box
            agree = frames = 0
            for clip in clips:
                rows = players(clip)
                windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in truth(clip)]
                looks, _ = teams.sample(Path(f"data/{clip}.mp4"), rows, samples)
                group = two_means({t: look[:3] for t, look in looks.items()}, {t: len(r) for t, r in teams.by_track(rows).items()})
                a, n = colour_vs_side(rows, windows, group, colour_lefts(rows, windows, group))
                agree, frames = agree + a, frames + n
            print(f"samples {samples:2}, torso {box}: colour vs side {agree}/{frames} ({agree / frames:.3f})")


def mixed(clips: list[str], seeds: int = 5, same: bool = False) -> None:
    """Side map and changes of ends with a random shirt and shorts colour per player, or one for
    every player when `same`."""
    palette = np.array([(240, 128, 128), (30, 128, 128), (128, 128, 128), (90, 170, 150), (80, 140, 90), (60, 135, 100), (200, 125, 200), (120, 175, 110), (150, 100, 160)], float)
    sample = teams.sample
    for clip in clips:
        path = Path(f"outputs/{clip}/identities.csv")
        if not path.exists():
            print(f"{clip}: no {path}")
            continue
        segments: dict[int, list[tuple[int, str, str]]] = {}
        with open(path) as f:
            for r in csv.DictReader(f):
                segments.setdefault(int(r["track"]), []).append((int(r["end_frame"]) - int(r["start_frame"]), r["team"], r["identity"]))
        owner = {t: max(v)[1:] for t, v in segments.items()}
        rows, labelled = players(clip), truth(clip)
        windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in labelled]
        looks, crops = sample(Path(f"data/{clip}.mp4"), rows)
        for seed in range(seeds):
            rng = np.random.default_rng(seed)
            kits: dict[tuple[str, str], np.ndarray] = {}
            dressed = {}
            for t in looks:
                kit = kits.setdefault(("", "") if same else owner.get(t, ("", str(t))), np.concatenate([palette[rng.integers(len(palette))], palette[rng.integers(3)]]))
                dressed[t] = kit + rng.normal(0, 6, 6)
            teams.sample = lambda video, rows, dressed=dressed: (dressed, crops)
            found = teams.assign(Path(f"data/{clip}.mp4"), rows, windows, FPS)
            teams.sample = sample
            # Team colours are random here: a rally is right when its left team is the first rally's
            # exactly when the labels say so.
            right_map = sum((g == found.left[0]) == (r["left"] == labelled[0]["left"]) for g, r in zip(found.left, labelled))
            changes = sum(a["left"] != b["left"] for a, b in zip(labelled, labelled[1:]))
            found_changes = sum(a != b for a, b in zip(found.left, found.left[1:]))
            print(f"{clip} seed {seed}: side map {right_map}/{len(labelled)}, changes of ends {found_changes} found / {changes} labelled")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+", help="Clip stems, e.g. side_club")
    parser.add_argument("--sweep", action="store_true", help="Compare samples per track and torso boxes")
    parser.add_argument("--mixed", action="store_true", help="Score the side map with a random kit per player")
    parser.add_argument("--same", action="store_true", help="Score the side map with one kit for both teams")
    args = parser.parse_args()
    sweep(args.clips) if args.sweep else mixed(args.clips, same=args.same) if args.mixed or args.same else score(args.clips)


if __name__ == "__main__":
    main()
