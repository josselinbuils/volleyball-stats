"""The review's answers moved onto the rally windows of a pipeline rerun: the answers name rallies by
their rallies.csv start (`rally`, `added`, `join`, `winner`, `end`, the rallies checked) and the
automatic reports by their page start, which a rerun moves. Each old rally goes to the new window it
overlaps most; one overlapping none keeps its key (the page then leaves its answers out).

    uv run python -m volleyball_stats.rekey outputs/VIDEO --before BACKUP/rallies.csv --page-before BACKUP/review-data.js --video VIDEO --court COURT_JSON
"""

import argparse
import csv
import json
import shutil
from pathlib import Path

from volleyball_stats import review, web
from volleyball_stats.court import Calibration

Window = tuple[int, int]


def read_windows(path: Path) -> list[Window]:
    with open(path) as f:
        return [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]


def overlaps(before: list[Window], after: list[Window], lead: int) -> dict[int, int]:
    """Each window of `before` (by index) to the window of `after` it overlaps most, `lead` frames
    before each start included."""
    out = {}
    for k, (a, b) in enumerate(before):
        best = max(((min(b, d) - max(a - lead, c - lead), j) for j, (c, d) in enumerate(after)), default=(0, None))
        if best[0] > 0:
            out[k] = best[1]
    return out


def moved(log: list[dict], before: list[Window], after: list[Window], lead: int) -> list[dict]:
    """The answers' `log` with their rally starts moved from `before`'s windows to `after`'s; a join
    between two old windows now in one goes. What the answers say of a whole rally (no play, its
    winner, its end) moves only onto a window that is mostly that rally: a false window joined to
    the rally before it is no reason to drop that rally."""
    to = overlaps(before, after, lead)
    starts = {s: after[to[k]][0] for k, (s, _) in enumerate(before) if k in to}

    def mostly(k: int) -> bool:
        (a, b), (c, d) = before[k], after[to[k]]
        return 2 * (min(b, d) - max(a, c) + lead) >= d - c + lead

    whole = {s: after[to[k]][0] for k, (s, _) in enumerate(before) if k in to and mostly(k)}
    index = {s: k for k, (s, _) in enumerate(before)}

    def key(start: int, moves: dict[int, int] = starts) -> int:
        # The review saved its rally questions' answers `lead` frames after the window's start until 1 Nov.
        if start not in index and start - lead in index:
            start -= lead
        return moves.get(start, start)

    def joined(start: int) -> bool:
        k = index.get(start)
        return k is not None and k + 1 < len(before) and to.get(k) is not None and to.get(k) == to.get(k + 1)

    def entry(e: dict) -> dict:
        e = dict(e)
        if "added" in e:
            e["added"] = [{**a, "start": key(a["start"])} for a in e["added"]]
        for kind in ("rally", "winner", "pinned", "end", "redo", "referee"):
            if kind in e:
                e[kind] = [{**a, "start": key(a["start"], whole)} for a in e[kind]]
        if "locked" in e:
            e["locked"] = [{**a, "start": key(a["start"])} for a in e["locked"]]
        if "join" in e:
            e["join"] = [{**a, "start": key(a["start"])} for a in e["join"] if not joined(a["start"])]
        for kind in ("checked", "unchecked"):
            if kind in e:
                e[kind] = sorted({key(s) for s in e[kind]})
        return e

    return [entry(e) for e in log]


def renamed_reports(before: dict, after: dict) -> dict[str, str]:
    """The automatic reports' keys of page `before` (its data.js MATCH) to those of page `after`:
    the same reason on the rally it overlaps most."""
    def windows(page: dict) -> list[Window]:
        return [(round(r["start"] * 100), round(r["end"] * 100)) for r in page["rallies"]]

    to = overlaps(windows(before), windows(after), 0)
    starts_before = {r["start"]: k for k, r in enumerate(before["rallies"])}
    new = {(r["kind"], r["time"]): r["key"] for r in review.unusual(after)}
    out = {}
    for r in review.unusual(before):
        k = to.get(starts_before[r["time"]])
        if k is not None and (r["kind"], after["rallies"][k]["start"]) in new:
            out[r["key"]] = new[(r["kind"], after["rallies"][k]["start"])]
    return out


def with_reports(log: list[dict], keys: dict[str, str]) -> list[dict]:
    """The answers' `log` with the report keys in its ids renamed by `keys`."""
    def renamed(qid: str) -> str:
        if not qid.startswith("report:"):
            return qid
        return "report:" + "+".join(keys.get(k, k) for k in qid.removeprefix("report:").split("+"))

    return [{**e, "id": renamed(e["id"])} for e in log]


def moved_comments(comments: dict[int, str], before: list[Window], after: list[Window], lead: int) -> dict[int, str]:
    """The review's `comments` (by rally key) moved from `before`'s windows to `after`'s: two landing
    on one window are joined; one on no window of `before` (a rally the review started) stays."""
    to = overlaps(before, after, lead)
    index = {s: k for k, (s, _) in enumerate(before)}
    out: dict[int, str] = {}
    for key, text in sorted(comments.items()):
        k = index.get(key)
        new = after[to[k]][0] if k in to else key
        out[new] = f"{out[new]}\n{text}" if new in out else text
    return out


def read_page(path: Path) -> dict:
    """A page's data.js MATCH."""
    text = path.read_text().strip()
    return json.loads(text[text.index("=") + 1 :].rstrip(";"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Move the review's answers onto the rally windows of a pipeline rerun.")
    parser.add_argument("match", type=Path)
    parser.add_argument("--before", type=Path, required=True, help="rallies.csv before the rerun")
    parser.add_argument("--page-before", type=Path, required=True, help="The review page's data.js before the rerun")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    args = parser.parse_args()
    path = args.match / "identity_answers.json"
    shutil.copy2(path, args.match / "identity_answers.before-rekey.json")
    fps = read_page(args.page_before)["fps"]
    log = moved(review.load_log(path), read_windows(args.before), read_windows(args.match / "rallies.csv"), round(web.LEAD_S * fps))
    review.save(path, log)
    review.write_comments(args.match, moved_comments(review.read_comments(args.match), read_windows(args.before), read_windows(args.match / "rallies.csv"), round(web.LEAD_S * fps)))
    page, _ = web.match_data(args.match, args.video, Calibration.load(args.court))
    keys = renamed_reports(read_page(args.page_before), page)
    review.save(path, with_reports(log, keys))
    print(f"{len(keys)} automatic reports renamed")


if __name__ == "__main__":
    main()
