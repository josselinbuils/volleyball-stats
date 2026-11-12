"""The corrections the owner makes in the review, counted for the pipeline's current code on the reviewed matches.

    uv run python benchmarks/corrections/bench.py freeze [MATCH]
    uv run python benchmarks/corrections/bench.py run RUN [MATCH] [--ball PATH] [--play PATH]
    uv run python benchmarks/corrections/bench.py score RUN [MATCH] [--compare OTHER] [--folder PATH]

MATCH is a prefix of a match folder's name (default: every reviewed match). Everything is written under
outputs/benchmarks/corrections/MATCH/; the real match folders are only read.
"""

import argparse
import contextlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import cv2

from volleyball_stats import actions, learn, review, web

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "outputs/matches"
BASE = ROOT / "outputs/benchmarks/corrections"
# What a rerun does not read (pictures, films, backups, the page's assets); review/data.js is kept for `rekey`.
SKIP = ("films", "voice", "backup-*", "before-rerun", "photo_*", "site", "experiments", "crops", "review", "hosted*.json", "publish.json", "feedback.log", "undone-report*", "first_match*", "jersey_pictures.json")
KINDS = ("add", "remove", "type", "player", "winner")


def matches(prefix: str | None) -> list[str]:
    found = sorted(p.name for p in MATCHES.iterdir() if (p / "identity_answers.json").exists() and (not prefix or p.name.startswith(prefix)))
    if not found:
        sys.exit(f"No reviewed match starts with {prefix!r}")
    return found


def source(name: str) -> tuple[Path, Path]:
    given = json.loads((MATCHES / name / "source.json").read_text())
    return ROOT / given["video"], ROOT / given["court"]


def freeze(name: str) -> None:
    """The truth of the checked rallies, from the reviewed page, written once."""
    video, _ = source(name)
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    page = review.page_data(MATCHES / name / "review")
    keys = set(review.checked(review.load_log(MATCHES / name / "identity_answers.json")))
    people = {str(k): v for k, v in page["people"].items()}
    out = []
    for k, r in enumerate(page["rallies"]):
        if r["key"] not in keys:
            continue
        touches = []
        for c in page["contacts"]:
            if c["rally"] == k:
                person = people.get(str(c.get("person"))) or {}
                touches.append({"t": c["t"], "frame": round(c["t"] * fps), "type": c["type"], "team": c["team"], "result": c.get("result"), "name": person.get("name"), "person_team": person.get("team")})
        out.append({"key": r["key"], "start": r["start"], "end": r["end"], "start_frame": round(r["start"] * fps), "end_frame": round(r["end"] * fps), "winner": r.get("winner"), "redo": bool(r.get("redo")), "touches": touches})
    path = BASE / name / "truth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"match": name, "fps": fps, "frozen": time.strftime("%Y-%m-%d %H:%M"), "checked_keys": len(keys), "rallies": out}, indent=1) + "\n")
    print(f"{name}: {len(out)} rallies, {sum(len(r['touches']) for r in out)} touches -> {path}")


def run(name: str, run_name: str, ball_path: Path | None = None, play: Path | None = None) -> None:
    """The match folder copied to a scratch folder and the pipeline run again on it, as the review's rerun does (no training).
    With `ball_path`, its ball track replaces the copy's ball.csv; the caches keyed by frame and ball place (wrists.json,
    relances.json, jumps.json) stay, the other contacts' entries unused, and net.csv is rewritten by the run."""
    video, court = source(name)
    scratch = BASE / name / "runs" / run_name / name
    if scratch.exists():
        sys.exit(f"{scratch} exists: pick another run name")
    shutil.copytree(MATCHES / name, scratch, ignore=shutil.ignore_patterns(*SKIP))
    (scratch / "review").mkdir()
    if ball_path:
        shutil.copy2(ball_path, scratch / "ball.csv")
        (scratch / "net.csv").unlink(missing_ok=True)
    if play:
        shutil.copy2(play, scratch / "play.npz")
    shutil.copy2(MATCHES / name / "review" / "data.js", scratch / "review" / "data.js")
    start, stages = time.perf_counter(), {}
    last = ["start", start]

    def on_stage(label: str) -> None:
        now = time.perf_counter()
        stages[last[0]] = round(now - last[1], 1)
        last[:] = [label, now]
        print(f"[{now - start:7.0f} s] {label}", flush=True)

    with open(scratch.parent / "run.log", "w") as log, contextlib.redirect_stdout(log):
        os.chdir(ROOT)
        learn.rerun(scratch, video, court, on_stage)
    on_stage("end")
    seconds = time.perf_counter() - start
    page, _ = web.match_data(scratch, video, __import__("volleyball_stats.court", fromlist=["Calibration"]).Calibration.load(court))
    kept = set(review.checked(review.load_log(scratch / "identity_answers.json")))
    now = {r["key"] for r in page["rallies"]}
    info = {"seconds": round(seconds, 1), "stages": stages, "commit": learn.commit(), "checked_keys_after": len(kept), "checked_rallies_on_page": len(kept & now), "rallies": len(page["rallies"])}
    (scratch.parent / "run.json").write_text(json.dumps(info, indent=1) + "\n")
    print(f"{name}: rerun {seconds / 60:.1f} min; checked rallies on the new page {info['checked_rallies_on_page']} (keys kept {len(kept)})")


def overlapping(windows: list[dict], start: int, end: int) -> dict | None:
    best = max(windows, key=lambda w: min(end, int(w["end_frame"])) - max(start, int(w["start_frame"])), default=None)
    return best if best and min(end, int(best["end_frame"])) > max(start, int(best["start_frame"])) else None


def corrections(folder: Path, truth: dict) -> tuple[dict, list[dict], dict[int, int]]:
    """The checked metrics, every correction and each rally's count, `folder`'s pipeline output against the frozen truth."""
    fps = truth["fps"]
    rows = learn.read_rows(folder / "actions.csv")
    _, by_name = learn.players(folder)
    names = {(team, number): name for (team, name), number in by_name.items()}
    windows = learn.read_rows(folder / "rallies.csv")
    points = {r["start_frame"]: r for r in learn.read_rows(folder / "points.csv")} if (folder / "points.csv").exists() else {}
    lead, within = round(actions.LEAD_S * fps), round(learn.SAME_S * fps)
    found = kept = typed = player = asked = won = shown = mine = nonredo = 0
    out, per = [], {}
    for r in truth["rallies"]:
        auto = [x for x in rows if r["start_frame"] - lead <= int(x["frame"]) <= r["end_frame"]]
        frames = [int(x["frame"]) for x in auto]
        shown, mine = shown + len(r["touches"]), mine + len(auto)
        matched, mine_here = set(), []

        def add(kind: str, **fields) -> None:
            mine_here.append({"rally": r["key"], "kind": kind, **fields})

        for c in r["touches"]:
            f = learn.near(c["frame"], frames, within)
            if f is None:
                nearest = learn.near(c["frame"], frames, 10**6)
                add("add", frame=c["frame"], t=c["t"], truth_type=c["type"], truth_team=c["team"], truth_name=c["name"], nearest_s=None if nearest is None else round(abs(nearest - c["frame"]) / fps, 2))
                continue
            found += 1
            matched.add(f)
            x = auto[frames.index(f)]
            same = x["type"] == c["type"]
            typed += same
            if not same:
                add("type", frame=c["frame"], t=c["t"], truth_type=c["type"], pipe_type=x["type"], pipe_frame=f)
            if c["name"] and x["type"] not in web.NO_PLAYER:
                asked += 1
                right = x["identity"] not in review.UNKNOWN and by_name.get((c["person_team"], c["name"])) == int(x["identity"]) and x["team"] == str(c["person_team"])
                player += right
                if not right:
                    unknown = x["identity"] in review.UNKNOWN
                    add("player", frame=c["frame"], t=c["t"], truth_type=c["type"], pipe_type=x["type"], truth_name=c["name"], truth_team=c["person_team"], pipe_team=x["team"],
                        pipe_identity=None if unknown else int(x["identity"]), pipe_name=None if unknown else names.get((int(x["team"]), int(x["identity"])) if x["team"] else None), track=x.get("track"))
        kept += len(matched)
        for x in auto:
            if int(x["frame"]) not in matched:
                nearest = learn.near(int(x["frame"]), [c["frame"] for c in r["touches"]], 10**6)
                add("remove", frame=int(x["frame"]), t=round(int(x["frame"]) / fps, 2), pipe_type=x["type"], pipe_team=x["team"], nearest_s=None if nearest is None else round(abs(nearest - int(x["frame"])) / fps, 2))
        w = overlapping(windows, r["start_frame"], r["end_frame"])
        p = points.get(w["start_frame"], {}) if w else {}
        if not r["redo"]:
            nonredo += 1
            ok = r["winner"] is not None and p.get("winner") == str(r["winner"])
            won += ok
            if not ok:
                add("winner", truth_winner=r["winner"], pipe_winner=p.get("winner") or None, window=None if w is None else int(w["start_frame"]), t=r["start"])
        out += mine_here
        per[r["key"]] = len(mine_here)
    metrics = {
        "checked: rallies": (len(truth["rallies"]),) * 2,
        "checked: touches found": (found, shown),
        "checked: pipeline touches kept": (kept, mine),
        "checked: types": (typed, found),
        "checked: named players": (player, asked),
        "checked: winners": (won, nonredo),
    }
    return metrics, out, per


def score(name: str, run_name: str, folder: Path | None, other: str | None) -> None:
    truth = json.loads((BASE / name / "truth.json").read_text())
    folder = folder or (MATCHES / name if run_name == "real" else BASE / name / "runs" / run_name / name)
    metrics, found, per = corrections(folder, truth)
    count = {k: sum(c["kind"] == k for c in found) for k in KINDS}
    count["total"] = len(found)
    n = len(truth["rallies"])
    count["per rally"] = round(len(found) / n, 2)
    count["rallies at zero"] = sum(v == 0 for v in per.values())
    summary = {"match": name, "run": run_name, "metrics": metrics, "counts": count, "per_rally": per}
    out = BASE / name / "runs" / run_name
    out.mkdir(parents=True, exist_ok=True)
    (out / "corrections.json").write_text(json.dumps(found, indent=1) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    before = json.loads((BASE / name / "runs" / other / "summary.json").read_text()) if other else None
    print(f"== {name} [{run_name}]")
    for k, (right, total) in metrics.items():
        was = before["metrics"][k] if before else None
        print(f"{k:34} {right}/{total}" + (f"   (was {was[0]}/{was[1]})" if was and tuple(was) != (right, total) else ""))
    for k, v in count.items():
        was = before["counts"][k] if before else None
        print(f"{k:34} {v}" + (f"   (was {was})" if was is not None and was != v else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze").add_argument("match", nargs="?")
    for command in ("run", "score"):
        p = sub.add_parser(command)
        p.add_argument("run", help='Run name ("real" scores the real folder, read-only)' if command == "score" else "Run name")
        p.add_argument("match", nargs="?")
    sub.choices["run"].add_argument("--ball", type=Path, help="Use this ball track (a ball.csv) in the copy instead of the match's")
    sub.choices["run"].add_argument("--play", type=Path, help="A play.npz (the play model's P(play)) for the copy: the scratch folder finds no weights")
    sub.choices["score"].add_argument("--compare", metavar="OTHER_RUN")
    sub.choices["score"].add_argument("--folder", type=Path, help="Score this folder instead of the run's")
    args = parser.parse_args()
    os.chdir(ROOT)
    for name in matches(args.match):
        if args.command == "freeze":
            if (BASE / name / "truth.json").exists():
                print(f"{name}: already frozen (delete truth.json to freeze again)")
            else:
                freeze(name)
        elif args.command == "run":
            run(name, args.run, args.ball, args.play)
        else:
            score(name, args.run, args.folder, args.compare)


if __name__ == "__main__":
    main()
