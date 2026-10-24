"""Score the identity step against hand-labelled player identities.

    uv run --group bench python benchmarks/identity/bench.py CLIP ... [--sweep] [--squad N[,N]] [--baseline]

Each CLIP reads data/CLIP.mp4 and the outputs of `match.py --players` in outputs/CLIP/ (players.csv,
rallies.csv) and benchmarks/identity/ground_truth/CLIP.csv: the identity of every tracked on-court
player on frames 2 s apart (`?` unsure, `X` not a player). Scores, per clip and pooled:
- IDF1 (IDP, IDR): labelled boxes whose identity is the one paired with their player, players and
  identities paired one to one by shared boxes; a box on a non-player counts against precision;
- dots right: labelled player boxes showing their player's paired number (IDR);
- splits: identities per player (each identity counted for the player holding most of its boxes);
- merges: players per identity (each player counted for the identity holding most of their boxes);
- ceilings: IDF1 when every track, then every segment, takes the player holding most of its boxes.
--sweep runs a grid of the module's constants given as GRID="NAME=v1,v2 NAME=v1" in the environment;
--baseline tracks scores the tracks alone (each its own identity), --baseline colour replaces the
re-ID embedding with a colour one (Lab median of 8 horizontal stripes of the box's middle half).
"""

import argparse
import csv
import itertools
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics.utils.ops import linear_sum_assignment

from volleyball_stats import identity
from volleyball_stats.attribution import read_players
from volleyball_stats.players import Row


def truth(clip: str) -> list[dict]:
    with open(f"benchmarks/identity/ground_truth/{clip}.csv") as f:
        return [r for r in csv.DictReader(f) if r["player"] != "?"]


def match_rows(labels: list[dict], rows: list[Row]) -> list[Row | None]:
    """The player row of each labelled box: same frame, IoU of 0.5 or more."""
    by_frame: dict[int, list[Row]] = {}
    for r in rows:
        by_frame.setdefault(r.frame, []).append(r)

    def iou(a, b) -> float:
        w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        return w * h / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h)

    out = []
    for label in labels:
        box = tuple(float(label[k]) for k in ("x1", "y1", "x2", "y2"))
        best = max(by_frame.get(int(label["frame"]), []), key=lambda r: iou(r.box, box), default=None)
        out.append(best if best is not None and iou(best.box, box) >= 0.5 else None)
    return out


def scores(players: list[str], predicted: list) -> dict:
    """IDF1, IDP, IDR, splits and merges of `predicted` identities (None: no identity) against the
    labelled `players` (X: not a player)."""
    names = sorted({p for p in players if p != "X"})
    ids = sorted({q for q in predicted if q is not None}, key=str)
    shared = np.zeros((len(names), len(ids)))
    for p, q in zip(players, predicted):
        if p != "X" and q is not None:
            shared[names.index(p), ids.index(q)] += 1
    rows, cols = linear_sum_assignment(-shared) if shared.size else ([], [])
    tp = float(shared[rows, cols].sum())
    gt = sum(p != "X" for p in players)
    pred = sum(q is not None for q in predicted)
    owners = Counter(int(np.argmax(shared[:, j])) for j in range(len(ids)) if shared[:, j].any())
    mains = Counter(int(np.argmax(shared[i])) for i in range(len(names)) if shared[i].any())
    return {
        "IDF1": 2 * tp / max(gt + pred, 1),
        "IDP": tp / max(pred, 1),
        "IDR": tp / max(gt, 1),
        "splits": sum(owners.values()) / max(len(owners), 1),
        "merges": sum(mains.values()) / max(len(mains), 1),
        "players": len(names),
        "identities": sum(owners.values()),
        "boxes": gt,
    }


def ceiling(players: list[str], keys: list) -> float:
    """IDF1 when each key (track or segment) takes its majority player."""
    votes: dict = {}
    for p, k in zip(players, keys):
        if k is not None:
            votes.setdefault(k, Counter())[p] += 1
    return scores(players, [votes[k].most_common(1)[0][0] if k is not None else None for k in keys])["IDF1"]


def colour_embed(video: Path, rows: list[Row], segments: list, cover: dict, cache=None) -> tuple[np.ndarray, np.ndarray]:
    """Stand-in for identity.embed: per box the Lab median of 8 horizontal stripes of its middle
    half, standardised, averaged per segment and padded to the re-ID size."""
    boxes = {(r.frame, r.track): r.box for r in rows}
    wanted: dict[int, list[int]] = {}
    for k, s in enumerate(segments):
        for f in identity.picks(s, cover):
            wanted.setdefault(f, []).append(k)
    found: list[tuple[int, np.ndarray]] = []
    for frame, image in identity.frames_at(video, wanted):
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(float)
        for k in wanted[frame]:
            x1, y1, x2, y2 = (round(v) for v in boxes[frame, segments[k].track])
            w = x2 - x1
            crop = lab[max(0, y1) : max(y2, y1 + 8), max(0, x1 + w // 4) : max(x2 - w // 4, x1 + w // 4 + 1)]
            found.append((k, np.concatenate([np.median(s.reshape(-1, 3), axis=0) for s in np.array_split(crop, 8, axis=0)])))
    x = np.array([f for _, f in found])
    x = (x - x.mean(0)) / (x.std(0) + 1e-6)
    v, counts = np.zeros((len(segments), identity.DIM)), np.zeros(len(segments))
    for (k, _), f in zip(found, x):
        v[k, : len(f)] += f
        counts[k] += 1
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), np.maximum(counts, 1)


def teams_by_track(rows: list[Row]) -> dict[int, list[Row]]:
    out: dict[int, list[Row]] = {}
    for r in sorted(rows, key=lambda r: r.frame):
        out.setdefault(r.track, []).append(r)
    return out


def evaluate(clip: str, squad=None, quiet: bool = False, tracks_only: bool = False, colour: bool = False) -> tuple[list[str], list, list, list]:
    video, match = Path(f"data/{clip}.mp4"), Path(f"outputs/{clip}")
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    rows = read_players(match / "players.csv")
    with open(match / "rallies.csv") as f:
        rallies = list(csv.DictReader(f))
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rallies]
    left = [int(r["left"]) if r.get("left") else None for r in rallies]
    if tracks_only:
        segments = [identity.Segment(t, [r.frame for r in rs], [], 0, t) for t, rs in teams_by_track(rows).items()]
    else:
        segments, _ = identity.identify(video, rows, windows, left, fps, None if colour else match / "embeddings.npz", squad=squad)
    table = [(s.track, s.start, s.end, s.team, s.identity) for s in segments]
    labels = truth(clip)
    matched = match_rows(labels, rows)
    players = [l["player"] for l in labels]
    predicted = [identity.lookup(table, r.track, r.frame) if r else None for r in matched]
    segment_of = [next((k for k, s in enumerate(segments) if s.identity and s.track == r.track and s.start <= r.frame <= s.end), None) if r else None for r in matched]
    if not quiet:
        print(f"{clip}: {sum(r is None for r in matched)} labelled boxes without a row; {len(segments)} segments")
    return players, predicted, [r.track if r else None for r in matched], segment_of


def report(name: str, players: list[str], predicted: list, tracks: list, segs: list) -> None:
    s = scores(players, predicted)
    teams = {}
    for prefix in sorted({p.split(":")[-1][0] for p in players if p != "X"}):
        keep = [i for i, p in enumerate(players) if p.split(":")[-1].startswith(prefix)]
        teams[prefix] = scores([players[i] for i in keep], [predicted[i] for i in keep])["IDF1"]
    print(
        f"| {name} | {s['IDF1']:.3f} | {s['IDP']:.3f} | {s['IDR']:.3f} | {s['identities']} / {s['players']} | {s['splits']:.2f} | {s['merges']:.2f} | "
        + " / ".join(f"{teams[t]:.3f}" for t in teams)
        + f" | {ceiling(players, tracks):.3f} / {ceiling(players, segs):.3f} | {s['boxes']} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the identity step against labelled identities.")
    parser.add_argument("clips", nargs="+")
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--baseline", choices=["tracks", "colour"], help="tracks: each track its own identity; colour: a colour embedding instead of the re-ID one")
    parser.add_argument("--squad", type=identity.parse_squad)
    args = parser.parse_args()
    if args.baseline == "colour":
        identity.embed = colour_embed
    options = {"tracks_only": args.baseline == "tracks", "colour": args.baseline == "colour"}

    print("| run | IDF1 | IDP | IDR (dots right) | identities / players | splits | merges | IDF1 per team | ceilings: tracks / segments | boxes |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    if not args.sweep:
        pooled = [[], [], [], []]
        for clip in args.clips:
            out = evaluate(clip, args.squad, **options)
            report(clip, *out)
            pooled[0] += [p if p == "X" else f"{clip}:{p}" for p in out[0]]
            for acc, part in zip(pooled[1:], out[1:]):
                acc += [None if x is None else (clip, x) for x in part]
        if len(args.clips) > 1:
            report("pooled", *pooled)
        return
    import os

    grid = {k: [None if x == "None" else float(x) for x in v.split(",")] for k, v in (item.split("=") for item in os.environ.get("GRID", "NEW=0.9").split())}
    for values in itertools.product(*grid.values()):
        for k, x in zip(grid, values):
            setattr(identity, k, int(x) if x is not None and x.is_integer() and k in ("WHITEN", "BATCH", "CROPS") else x)
        for clip in args.clips:
            report(f"{clip} " + " ".join(f"{k} {x}" for k, x in zip(grid, values)), *evaluate(clip, args.squad, quiet=True, **options))


if __name__ == "__main__":
    main()
