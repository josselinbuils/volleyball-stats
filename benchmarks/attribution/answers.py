"""Score attribution on a match's own review answers: each touch asked in the review and answered
with a player (identity_answers.json's "touch") against the automatic pick (actions.csv's
identity), by why it was asked and by the gap to the next candidate. The spot checks estimate the
wrong picks the doubts miss; the gaps, where to set attribution.DOUBT. With --rerank, also
attribution.ranked as it stands run again on actions.csv's contacts and players.csv (the touch's
identity being its track's in identities.csv), to score a change to the step without rerunning the
pipeline; with --video, attribution.by_wrists after it too (pose on the video).

    uv run python benchmarks/attribution/answers.py outputs/first_match [--rerank [--video data/first_match.mp4]]
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from volleyball_stats import attribution, identity, ranker, web
from volleyball_stats.actions import LEAD_S
from volleyball_stats.players import Row
from volleyball_stats.review import UNKNOWN, doubtful

GAPS = (0.01, 0.02, 0.05, 0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path)
    parser.add_argument("--fps", type=float, default=50.0)
    parser.add_argument("--rerank", action="store_true", help="Also score attribution.ranked run again on players.csv")
    parser.add_argument("--video", type=Path, help="With --rerank, also score attribution.by_wrists on this video")
    args = parser.parse_args()
    actions = web.read_csv(args.match / "actions.csv")
    windows = [(int(r["start_frame"]) - round(LEAD_S * args.fps), int(r["end_frame"])) for r in web.read_csv(args.match / "rallies.csv")]
    why = {r["frame"]: reason for r, reason in doubtful(actions, windows)}
    row = {r["frame"]: r for r in actions}
    path = args.match / "identity_answers.json"
    answers = json.loads(path.read_text()).get("touch", []) if path.exists() else []
    given = identity.named(identity.read_identities(args.match / "identities.csv"), identity.read_names(args.match))
    by_name = {(team, g["name"]): number for (team, number), g in given.items() if g.get("name")}
    by_reason, by_gap, nobody, outside = defaultdict(list), defaultdict(list), 0, 0
    for a in answers:
        r = row.get(str(a["frame"]))
        if r is None:
            continue
        # No touch at all ("nobody", identity None): a contact the detector made up, wrong whoever got it.
        said = None if a["identity"] is None else by_name.get((a["team"], a.get("name")), a["identity"])
        right = said is not None and r["identity"] not in UNKNOWN and int(r["identity"]) == said
        nobody += said is None and a.get("play", True)
        outside += not a.get("play", True)
        by_reason[why.get(r["frame"], "asked before")].append(right)
        if r.get("gap"):
            by_gap[next((g for g in GAPS if float(r["gap"]) < g), None)].append(right)
    print(f"{sum(map(len, by_reason.values()))} touches answered, {nobody} of them no touch at all, {outside} outside the play")
    for reason, hits in sorted(by_reason.items()):
        print(f"  {reason:12} automatic pick right {sum(hits)}/{len(hits)}")
    for g in (*GAPS, None):
        if by_gap[g]:
            print(f"  gap {'< ' + str(g) if g else '>= ' + str(GAPS[-1]):7} right {sum(by_gap[g])}/{len(by_gap[g])}")
    if args.rerank:
        table = identity.read_identities(args.match / "identities.csv")
        # The last answer to a touch wins; "nobody" leaves it out.
        last = {a["frame"]: a for a in answers if str(a["frame"]) in row}
        truth = {f: (a["team"], by_name.get((a["team"], a.get("name")), a["identity"])) for f, a in last.items() if a["identity"] is not None}
        rerank(args.match, [row[str(f)] for f in sorted(truth)], truth, table, args.fps, args.video)


def near_rows(path: Path, frames: set[int], margin: int) -> list[Row]:
    """players.csv's rows within `margin` frames of `frames`."""
    keep = {f + d for f in frames for d in range(-margin, margin + 1)}
    with open(path) as f:
        return [
            Row(int(r["frame"]), int(r["track"]), tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2")), float(r["conf"]),
                (float(r["feet_x"]), float(r["feet_y"])), (float(r["court_x"]), float(r["court_y"])), r["team"])
            for r in csv.DictReader(f) if int(r["frame"]) in keep
        ]


def rerank(match: Path, asked: list[dict], truth: dict[int, tuple[int, int]], table: list, fps: float, video: Path | None) -> None:
    """attribution.ranked (then by_wrists with a video) on the answered touches: the answered player
    first, among the candidates, by type."""
    typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in asked]
    rows = near_rows(match / "players.csv", {t[0] for t in typed}, round(attribution.GAP_S * fps) + 1)
    by_track = defaultdict(list)
    for r in table:
        by_track[r[0]].append(r)
    candidates = attribution.ranked(typed, rows, fps)
    for name, found in (("ranked", candidates), *((("by_wrists", attribution.by_wrists(video, typed, candidates, rows, fps, match / "wrists.json")),) if video else ()),
        *((("learned", attribution.by_wrists(video, typed, candidates, rows, fps, match / "wrists.json", ranker.load())),) if video and ranker.load() else ())):
        first, among, by_type = 0, 0, defaultdict(list)
        for t, c in zip(typed, found):
            ids = [identity.lookup(by_track[k], k, t[0]) for *_, k in c]
            first += bool(ids) and ids[0] == truth[t[0]]
            among += truth[t[0]] in ids
            by_type[t[3]].append(bool(ids) and ids[0] == truth[t[0]])
        print(f"attribution.{name} again: answered player first {first}/{len(typed)}, among the candidates {among}")
        print("  " + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by_type.items())))


if __name__ == "__main__":
    main()
