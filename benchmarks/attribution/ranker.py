"""Train the learned candidate order (volleyball_stats.ranker) on the review's touch answers of the
matches given and the labelled school clips, score it with each group held out in turn (each set of
a match, each clip) against the rule (attribution.by_wrists without it), then write the weights fit
on everything to src/volleyball_stats/attribution_ranker.json.

    uv run --group bench python benchmarks/attribution/ranker.py outputs/2026-10-29-aspom-1-vs-aspom-2:data/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4:outputs/courts/aspom_begles.json [--clips side_club side_long side_holdout] [--write]

The poses are kept in outputs/ranker/ (first run: about a second per touch).
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import bench  # noqa: E402

from volleyball_stats import actions, attribution, ball3d, contacts, identity, ranker, web  # noqa: E402
from volleyball_stats.court import Calibration  # noqa: E402

CACHE = Path("outputs/ranker")


def candidates_features(video: Path, typed: list, rows: list, fps: float, cache: Path, places: dict | None = None) -> tuple[list, list, list]:
    """Each touch's candidates, their features as by_wrists computes them, and the rule's order."""
    found = attribution.ranked(typed, rows, fps)
    # The poses of every touch with two candidates or more, kept for the next runs.
    attribution.by_wrists(video, typed, found, rows, fps, cache, learned={"w": [0.0] * 34, "mean": [0.0] * 34, "std": [1.0] * 34})
    rule = attribution.by_wrists(video, typed, found, rows, fps, cache)
    kept = json.loads(cache.read_text()) if cache.exists() else {}
    by_track, gap = attribution.tracks(rows), round(attribution.GAP_S * fps)
    feet = attribution.feet_on_court(rows) if places else {}
    feats = []
    for (frame, x, y, kind, side), c in zip(typed, found):
        if len(c) < 2:
            feats.append(None)
            continue
        poses = [[(tuple(b), np.array(k)) for b, k in f] for f in kept.get(f"{frame}:{x}:{y}", [])]
        boxes = {k[2]: attribution.box_at(by_track[k[2]][1], frame, gap) for k in c}
        tallest = max(b[3] - b[1] for b in boxes.values())
        metres = attribution.court_metres((places or {}).get(frame), frame, c, feet, gap)
        feats.append(np.array([
            ranker.features((x, y), kind, k, c[0][0], r, boxes[k[2]], tallest, attribution.wrist_distance((x, y), boxes[k[2]], poses), by_track[k[2]][0] == side, (frame - min(by_track[k[2]][1])) / fps, metres[k[2]])
            for r, k in enumerate(c)
        ]))
    return found, feats, rule


def from_match(match: Path, video: Path, court: Path | None = None) -> list[dict]:
    """The answered touches of a match: group "MATCH set N"; with its `court`, the ball's 3D places
    are among the features."""
    fps = 50.0
    rows_csv = {int(r["frame"]): r for r in web.read_csv(match / "actions.csv")}
    answers = json.loads((match / "identity_answers.json").read_text())
    table = identity.read_identities(match / "identities.csv")
    given = identity.named(table, identity.read_names(match))
    by_name = {(team, g["name"]): n for (team, n), g in given.items() if g.get("name")}
    last = {a["frame"]: a for a in answers["touch"] if a["frame"] in rows_csv and a["identity"] is not None}
    truth = {f: (a["team"], by_name.get((a["team"], a.get("name")), a["identity"])) for f, a in last.items()}
    typed = [(f, int(rows_csv[f]["x"]), int(rows_csv[f]["y"]), rows_csv[f]["type"], rows_csv[f]["side"]) for f in sorted(truth)]
    rows = attribution.read_players(match / "players.csv")
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in web.read_csv(match / "rallies.csv")]
    every = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in web.read_csv(match / "actions.csv")]
    places = ball3d.flight_places(every, windows, round(actions.LEAD_S * fps), match / "ball.csv", Calibration.load(court), fps) if court else None
    found, feats, rule = candidates_features(video, typed, rows, fps, CACHE / f"{match.name}_wrists.json", places)
    by_track = defaultdict(list)
    for r in table:
        by_track[r[0]].append(r)
    sets = [(int(r["start_frame"]), r["set"]) for r in web.read_csv(match / "rallies.csv")]
    out = []
    for t, c, x, ru in zip(typed, found, feats, rule):
        if not c:
            continue
        right = [identity.lookup(by_track[k[2]], k[2], t[0]) == truth[t[0]] for k in c]
        group = f"{match.name} set {max((s for s0, s in sets if s0 - 50 <= t[0]), default='1')}"
        out.append({"group": group, "tracks": [k[2] for k in c], "x": x, "right": right, "rule": ru[0][2]})
    return out


def from_clip(clip: str) -> list[dict]:
    """The labelled touches of a school clip (the attribution bench's `truth`)."""
    fps = bench.FPS
    cal = bench.calibration()
    rows = attribution.read_players(Path(f"outputs/players/{clip}_players.csv"))
    touchers = bench.load_touchers(Path(f"benchmarks/attribution/ground_truth/{clip}.csv"))
    filled = contacts.interpolate(contacts.read_track(Path(f"outputs/ball/{clip}_ball.csv")))
    typed = []
    for rally in bench.load_contacts(Path(f"benchmarks/contacts/ground_truth/{clip}.csv")):
        given = [(f, round(filled[f, 0]), round(filled[f, 1])) for f in rally["contacts"]]
        typed += [(f, x, y, rally["contacts"][f], side) for f, x, y, _, side in actions.classify_rally(given, rally["net"], fps, bench.NET_X, cal)]
    typed = [t for t in typed if touchers[t[0]]["toucher"] != "none" and t[3] not in attribution.NO_PLAYER]
    found, feats, rule = candidates_features(Path(f"data/benchmarks/{clip}.mp4"), typed, rows, fps, CACHE / f"{clip}_wrists.json")
    by_track, gap = attribution.tracks(rows), round(attribution.GAP_S * fps)
    out = []
    for t, c, x, ru in zip(typed, found, feats, rule):
        if c:
            right = [bench.matches(attribution.box_at(by_track[k[2]][1], t[0], gap), touchers[t[0]]) for k in c]
            out.append({"group": clip, "tracks": [k[2] for k in c], "x": x, "right": right, "rule": ru[0][2]})
    return out


def pick(model: dict, d: dict) -> int:
    return 0 if d["x"] is None else int(np.argmax(ranker.scores(model, d["x"])))


def trainable(data: list[dict]) -> list[tuple[np.ndarray, int]]:
    return [(d["x"], d["right"].index(True)) for d in data if d["x"] is not None and any(d["right"])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matches", nargs="*", help="MATCH_DIR:VIDEO[:COURT_JSON], answered in the review")
    parser.add_argument("--clips", nargs="*", default=["side_club", "side_long", "side_holdout"])
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--write", action="store_true", help=f"Write the weights fit on everything to {ranker.WEIGHTS}")
    parser.add_argument("--if-better", action="store_true", help="With --write, only when the matches' held-out touches gain on the rule")
    parser.add_argument("--summary", type=Path, help="Write the matches' held-out scores there (JSON: touches, rule, learned, kept)")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    data = [d for m in args.matches for d in from_match(*map(Path, m.split(":")))] + [d for c in args.clips for d in from_clip(c)]
    total, matches = [0, 0, 0], [0, 0, 0]
    for g in sorted({d["group"] for d in data}):
        test = [d for d in data if d["group"] == g]
        model = ranker.fit(trainable([d for d in data if d["group"] != g]), args.l2)
        rule = sum(d["right"][d["tracks"].index(d["rule"])] for d in test)
        learned = sum(d["right"][pick(model, d)] for d in test)
        print(f"{g:24} {len(test):4} touches: rule {rule:4}, learned {learned:4}")
        total = [total[0] + len(test), total[1] + rule, total[2] + learned]
        # The school clips are 720p: the model runs on the matches' footage only.
        if g not in args.clips:
            matches = [matches[0] + len(test), matches[1] + rule, matches[2] + learned]
    print(f"{'held out, all':24} {total[0]:4} touches: rule {total[1]:4}, learned {total[2]:4}")
    kept = args.write and (not args.if_better or matches[2] > matches[1])
    if kept:
        ranker.WEIGHTS.parent.mkdir(exist_ok=True)
        ranker.WEIGHTS.write_text(json.dumps({**ranker.fit(trainable(data), args.l2), "touches": len(trainable(data))}) + "\n")
        print(f"{ranker.WEIGHTS} written")
    elif args.write:
        print(f"{ranker.WEIGHTS} kept: no gain on the rule held out ({matches[2]} against {matches[1]} of {matches[0]})")
    if args.summary:
        args.summary.write_text(json.dumps({"touches": matches[0], "rule": matches[1], "learned": matches[2], "kept": kept}) + "\n")


if __name__ == "__main__":
    main()
