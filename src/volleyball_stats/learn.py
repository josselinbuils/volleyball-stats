"""Every step scored on a match's review answers, against the previous run's scores (learn.json in
the match folder): what the answers teach, after each review or pipeline change.

- attribution: the answered touches' automatic player;
- contacts: the touches the review added that the pipeline now finds, the false ones it removed
  that it still makes;
- actions: the types the review set;
- rallies: the windows the review kept or dropped, the labelled serves of the rallies benchmark
  (`benchmarks/rallies/ground_truth/MATCH_*.csv`) and their servers and winners;
- checked: the rallies checked in the Match tab, labels in full: their touches, types, players and
  winner on the page against the pipeline's own.

    uv run python -m volleyball_stats.learn outputs/VIDEO --video VIDEO --court COURT_JSON [--rerun]

With --rerun (the review's "Apprendre de mes réponses"), the learned attribution is trained again on the
answers (`train`), the pipeline runs again and the answers move onto its rally windows.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import cv2

from volleyball_stats import actions, files, film, identity, review, web
from volleyball_stats.court import Calibration

ROOT = Path(__file__).resolve().parents[2]
HISTORY = "learn.json"
# The learned attribution's last training: its held-out scores (`train`).
RANKER = "ranker.json"
# How far a pipeline contact may be from a touch the review gave.
SAME_S = 0.2
# How far a window's start may be from its labelled serve.
SERVE_S = 1.5

Score = tuple[int, int]


def read_rows(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def players(match: Path) -> tuple[list, dict[tuple[int, str], int]]:
    """identities.csv's table and each named player's identity, by team and name."""
    table = identity.read_identities(match / "identities.csv")
    given = identity.named(table, identity.read_names(match))
    return table, {(team, g["name"]): number for (team, number), g in given.items() if g.get("name")}


def near(frame: int, frames: list[int], within: int) -> int | None:
    found = min(frames, key=lambda f: abs(f - frame), default=None)
    return found if found is not None and abs(found - frame) <= within else None


def from_answers(match: Path, fps: float) -> dict[str, Score]:
    """The scores on the answers: right, asked."""
    if not (match / "identity_answers.json").exists():
        return {}
    answers = json.loads((match / "identity_answers.json").read_text())
    rows = read_rows(match / "actions.csv")
    by_frame = {int(r["frame"]): r for r in rows}
    frames = sorted(by_frame)
    within = round(SAME_S * fps)
    _, by_name = players(match)
    out: dict[str, Score] = {}

    last = {a["frame"]: a for a in answers.get("touch", [])}
    picked = [(by_frame[f], a) for f, a in last.items() if f in by_frame and a["identity"] is not None]
    right = 0
    for r, a in picked:
        said = by_name.get((a["team"], a.get("name")), a["identity"])
        right += r["identity"] not in review.UNKNOWN and r["team"] == str(a["team"]) and int(r["identity"]) == said
    out["attribution: answered touches"] = (right, len(picked))
    added = list({a["frame"]: a for a in answers.get("added", [])}.values())
    out["contacts: added touches found"] = (sum(near(a["frame"], frames, within) is not None for a in added), len(added))
    false = [f for f, a in last.items() if a["identity"] is None and a.get("play", True)]
    out["contacts: false ones gone"] = (sum(f not in by_frame for f in false), len(false))
    types = {a["frame"]: a["type"] for a in answers.get("action", []) if "type" in a}
    out["actions: types set"] = (sum(by_frame.get(f, {}).get("type") == kind for f, kind in types.items()), len(types))
    starts = {int(r["start_frame"]) for r in read_rows(match / "rallies.csv")}
    said = {a["start"]: a["play"] for a in answers.get("rally", [])}
    out["rallies: kept"] = (sum(s in starts for s, play in said.items() if play), sum(said.values()))
    out["rallies: dropped"] = (sum(s not in starts for s, play in said.items() if not play), sum(not p for p in said.values()))
    return out


def from_labels(match: Path, fps: float, name: str) -> dict[str, Score]:
    """The scores on the rallies benchmark's labels of the match, if any: serves with a window,
    their servers and winners (the end serving next)."""
    labels = []
    for path in sorted((ROOT / "benchmarks/rallies/ground_truth").glob(f"{name}_*.csv")):
        span = [(int(r["start_frame"]), "left" if r["note"].startswith("left serves") else "right") for r in read_rows(path)]
        labels += [(start, side, after[1] if after else None) for (start, side), after in zip(span, [*span[1:], None])]
    if not labels:
        return {}
    windows = read_rows(match / "rallies.csv")
    points = {r["start_frame"]: r for r in read_rows(match / "points.csv")} if (match / "points.csv").exists() else {}
    found = served = won = asked = 0
    for start, server, winner in labels:
        w = min(windows, key=lambda w: abs(int(w["start_frame"]) - start), default=None)
        if w is None or abs(int(w["start_frame"]) - start) > SERVE_S * fps:
            continue
        p = points.get(w["start_frame"], {})

        def side(team: str | None) -> str | None:
            return None if not team or not w.get("left") else "left" if team == w["left"] else "right"

        found += 1
        served += side(p.get("server")) == server
        if winner:
            asked += 1
            won += side(p.get("winner")) == winner
    return {"rallies: labelled serves with a window": (found, len(labels)), "points: labelled servers": (served, found), "points: labelled winners": (won, asked)}


def from_checked(match: Path, page: dict, fps: float) -> dict[str, Score]:
    """The scores on the rallies checked in the Match tab: the page's touches (the review's) found by
    the pipeline, the pipeline's kept, their types and players, the rallies' winners."""
    keys = set(review.checked(review.load_log(match / "identity_answers.json")))
    rallies = [(k, r) for k, r in enumerate(page["rallies"]) if r["key"] in keys]
    if not rallies:
        return {}
    rows = read_rows(match / "actions.csv")
    _, by_name = players(match)
    points = {int(r["start_frame"]): r for r in read_rows(match / "points.csv")} if (match / "points.csv").exists() else {}
    lead, within = round(actions.LEAD_S * fps), round(SAME_S * fps)
    people = {str(k): v for k, v in page["people"].items()}
    found = kept = typed = player = asked = won = 0
    shown = mine = 0
    for k, r in rallies:
        start, end = round(r["start"] * fps), round(r["end"] * fps)
        truth = [c for c in page["contacts"] if c["rally"] == k]
        auto = [x for x in rows if start - lead <= int(x["frame"]) <= end]
        frames = [int(x["frame"]) for x in auto]
        shown, mine = shown + len(truth), mine + len(auto)
        matched = set()
        for c in truth:
            f = near(round(c["t"] * fps), frames, within)
            if f is None:
                continue
            found += 1
            matched.add(f)
            x = auto[frames.index(f)]
            typed += x["type"] == c["type"]
            person = people.get(str(c.get("person")))
            if person and person.get("name") and x["type"] not in web.NO_PLAYER:
                asked += 1
                player += x["identity"] not in review.UNKNOWN and by_name.get((person["team"], person["name"])) == int(x["identity"]) and x["team"] == str(person["team"])
        kept += len(matched)
        p = points.get(r["key"], {})
        won += r.get("winner") is not None and p.get("winner") == str(r["winner"])
    return {
        "checked: rallies": (len(rallies), len(rallies)),
        "checked: touches found": (found, shown),
        "checked: pipeline touches kept": (kept, mine),
        "checked: types": (typed, found),
        "checked: named players": (player, asked),
        "checked: winners": (won, sum(not r.get("redo") for _, r in rallies)),
    }


def commit() -> str:
    run = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return run.stdout.strip()


def from_training(match: Path) -> dict[str, Score]:
    """The learned attribution's held-out scores at its last training, against the rule's."""
    path = match / RANKER
    if not path.exists():
        return {}
    found = json.loads(path.read_text())
    return {"attribution: held out, learned": (found["learned"], found["touches"]), "attribution: held out, rule": (found["rule"], found["touches"])}


def scores(match: Path, video: Path, court: Path, name: str | None = None) -> dict[str, Score]:
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    page, _ = web.match_data(match, video, Calibration.load(court))
    return {**from_answers(match, fps), **from_training(match), **from_labels(match, fps, name or match.name), **from_checked(match, page, fps)}


def report(now: dict[str, Score], before: dict[str, Score] | None) -> str:
    lines = []
    for name, (right, total) in now.items():
        then = (before or {}).get(name)
        change = "" if then is None or tuple(then) == (right, total) else f"  (was {then[0]}/{then[1]})"
        lines.append(f"{name:42} {right}/{total}{change}")
    return "\n".join(lines)


def train(match: Path, video: Path, court: Path) -> None:
    """The learned order of who touched the ball (ranker.py) trained again on the match's answers
    and the school clips' labels, kept only if it gains on the rule on the match's touches held out
    set by set; its held-out scores in ranker.json for `scores`."""
    subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/attribution/ranker.py"), f"{match}:{video}:{court}", "--write", "--if-better", "--summary", str(match / RANKER)],
        cwd=ROOT, stdin=subprocess.DEVNULL, check=True,
    )


def rerun(match: Path, video: Path, court: Path, on_stage: Callable[[str], None] = lambda _: None) -> dict[str, Score]:
    """The pipeline run again on the match (match.py, the trackers' outputs and the poses kept), the
    answers moved onto its rally windows (`rekey`), then every step scored, kept in learn.json with
    what the replaced results scored on the same answers (the held-out scores are the training's).
    `on_stage` is told each step as it starts (match.STAGE lines), "answers" for the last one."""
    from volleyball_stats import match as pipeline, rekey

    replaced = {k: v for k, v in scores(match, video, court).items() if k not in from_training(match)}
    before = match / "before-rerun"
    before.mkdir(exist_ok=True)
    shutil.copy2(match / "rallies.csv", before / "rallies.csv")
    if (match / "review" / "data.js").exists():
        shutil.copy2(match / "review" / "data.js", before / "review-data.js")
    with subprocess.Popen(
        [sys.executable, "-m", "volleyball_stats.match", str(video), "--court", str(court), "--players", "--no-page", "--out", str(match.parent)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, bufsize=1,
    ) as run:
        for line in run.stdout:
            if line.startswith(pipeline.STAGE):
                on_stage(line.removeprefix(pipeline.STAGE).strip())
            else:
                sys.stdout.write(line)
    if run.returncode:
        raise subprocess.CalledProcessError(run.returncode, run.args)
    on_stage("answers")
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    path = match / "identity_answers.json"
    if not path.exists():
        return record(match, video, court, replaced)
    shutil.copy2(path, before / "identity_answers.json")
    log = rekey.moved(review.load_log(path), rekey.read_windows(before / "rallies.csv"), rekey.read_windows(match / "rallies.csv"), round(actions.LEAD_S * fps))
    review.save(path, log)
    if (match / review.COMMENTS).exists():
        shutil.copy2(match / review.COMMENTS, before / review.COMMENTS)
        review.write_comments(match, rekey.moved_comments(review.read_comments(match), rekey.read_windows(before / "rallies.csv"), rekey.read_windows(match / "rallies.csv"), round(actions.LEAD_S * fps)))
    if (match / film.PICKS).exists():
        shutil.copy2(match / film.PICKS, before / film.PICKS)
        film.write_picks(match, set(rekey.moved_comments(dict.fromkeys(film.read_picks(match), ""), rekey.read_windows(before / "rallies.csv"), rekey.read_windows(match / "rallies.csv"), round(actions.LEAD_S * fps))))
    if (before / "review-data.js").exists():
        page, _ = web.match_data(match, video, Calibration.load(court))
        review.save(path, rekey.with_reports(log, rekey.renamed_reports(rekey.read_page(before / "review-data.js"), page)))
    return record(match, video, court, replaced)


def record(match: Path, video: Path, court: Path, replaced: dict[str, Score] | None = None) -> dict[str, Score]:
    """`scores`, added to learn.json with those of the results they `replaced`; printed against the last ones."""
    path = match / HISTORY
    history = json.loads(path.read_text()) if path.exists() else []
    now = scores(match, video, court)
    print(report(now, history[-1]["scores"] if history else None))
    history.append({"time": time.strftime("%Y-%m-%d %H:%M"), "commit": commit(), "scores": now, **({"before": replaced} if replaced else {})})
    files.write_text(path, json.dumps(history, indent=1) + "\n")
    return now


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    parser.add_argument("--labels", help="The match's name in the rallies benchmark (default: the folder's)")
    parser.add_argument("--rerun", action="store_true", help="Run the pipeline again first, the answers moved onto its rallies")
    args = parser.parse_args()
    if args.rerun:
        train(args.match, args.video, args.court)
        rerun(args.match, args.video, args.court)
    elif args.labels:
        print(report(scores(args.match, args.video, args.court, args.labels), None))
    else:
        record(args.match, args.video, args.court)


if __name__ == "__main__":
    main()
