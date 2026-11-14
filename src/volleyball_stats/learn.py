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

    uv run python -m volleyball_stats.learn outputs/matches/VIDEO --video VIDEO --court COURT_JSON [--rerun]
    uv run python -m volleyball_stats.learn --update outputs/matches [--only NAME]

With --rerun, the learned attribution is trained again on every reviewed match's answers (`train`), the pipeline runs
again and the answers move onto its rally windows. --update (the app's "Mettre à jour") does so once for every match
waiting (`review.due`): one training, then each match's pipeline again, a fully checked one only measured. With --only
NAME (the button inside a match's review), that match alone after the same training; the others keep waiting.
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

from volleyball_stats import actions, files, identity, jobs, review, web
from volleyball_stats.court import Calibration

ROOT = Path(__file__).resolve().parents[2]
HISTORY = "learn.json"
# The learned attribution's last training: its held-out scores (`train`).
RANKER = "ranker.json"
# How far a pipeline contact may be from a touch the review gave.
SAME_S = 0.2
# How far a window's start may be from its labelled serve.
SERVE_S = 1.5
# The update's durations here (`update`), and before any: a training, a match's pipeline again, the play model's training.
TIMINGS = "learn_timings.json"
TOOK = {"training": 120.0, "match": 900.0, "play": 900.0}

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


def answered(outputs: Path) -> list[str]:
    """The matches of `outputs` with review answers and their video here, as ranker.py takes them."""
    found = []
    for source in sorted(outputs.glob(f"*/{files.SOURCE}")):
        match, given = source.parent, json.loads(source.read_text())
        if (match / "identity_answers.json").exists() and (ROOT / given["video"]).exists():
            found.append(f"{match}:{ROOT / given['video']}:{ROOT / given['court']}")
    return found


def train(outputs: Path) -> None:
    """The learned order of who touched the ball (ranker.py) trained again on the answers of every
    reviewed match of `outputs` and the school clips' labels, kept only if it gains on the rule on the matches'
    touches held out set by set; each match's held-out scores in its ranker.json for `scores`."""
    subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/attribution/ranker.py"), *answered(outputs), "--write", "--if-better", "--summaries"],
        cwd=ROOT, stdin=subprocess.DEVNULL, check=True,
    )


def play_due(match: Path) -> bool:
    """Whether the play model has something new to learn here (`play_training.due`): a match fully checked since its last training."""
    from volleyball_stats import play_training

    return bool(play_training.due(match))


def train_play(match: Path) -> None:
    """The play model trained again on every match fully checked (`play_training`), in its own process: the review's
    server keeps no model in memory."""
    subprocess.run([sys.executable, "-m", "volleyball_stats.play_training", str(match)], cwd=ROOT, stdin=subprocess.DEVNULL, check=True)


def measured(match: Path, video: Path, court: Path, update: str | None = None) -> dict[str, Score]:
    """The match left as it is, measured in learn.json like a rerun: a fully checked one after a training."""
    return record(match, video, court, {k: v for k, v in scores(match, video, court).items() if k not in from_training(match)}, update)


def rerun(
    match: Path, video: Path, court: Path, on_stage: Callable[[str], None] = lambda _: None, on_share: Callable[[float], None] = lambda _: None, update: str | None = None
) -> dict[str, Score]:
    """The pipeline run again on the match (match.py, the trackers' outputs and the poses kept), the
    answers moved onto its rally windows (`rekey`), then every step scored, kept in learn.json with
    what the replaced results scored on the same answers (the held-out scores are the training's).
    `on_stage` is told each step as it starts (match.STAGE lines), "answers" for the last one, `on_share` the share
    of the pipeline done; `update` names the app's update it is part of."""
    from volleyball_stats import match as pipeline, rekey

    replaced = {k: v for k, v in scores(match, video, court).items() if k not in from_training(match)}
    before = match / "before-rerun"
    before.mkdir(exist_ok=True)
    shutil.copy2(match / "rallies.csv", before / "rallies.csv")
    if (match / "review" / "data.js").exists():
        shutil.copy2(match / "review" / "data.js", before / "review-data.js")
        (before / "review-ball3d.js").unlink(missing_ok=True)
        if (match / "review" / "ball3d.js").exists():
            shutil.copy2(match / "review" / "ball3d.js", before / "review-ball3d.js")
    with subprocess.Popen(
        [sys.executable, "-m", "volleyball_stats.match", str(video), "--court", str(court), "--players", "--no-page", "--out", str(match.parent)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, bufsize=1,
    ) as run:
        for line in run.stdout:
            if line.startswith(pipeline.STAGE):
                on_stage(line.removeprefix(pipeline.STAGE).strip())
            elif line.startswith(jobs.PROGRESS):
                on_share(float(line.removeprefix(jobs.PROGRESS).split()[0]))
            else:
                sys.stdout.write(line)
    if run.returncode:
        raise subprocess.CalledProcessError(run.returncode, run.args)
    on_stage("answers")
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    path = match / "identity_answers.json"
    if not path.exists():
        return record(match, video, court, replaced, update)
    shutil.copy2(path, before / "identity_answers.json")
    lead = round(actions.LEAD_S * fps)
    old, new = rekey.read_windows(before / "rallies.csv"), rekey.read_windows(match / "rallies.csv")
    page_before = before / "review-data.js"
    adopted = rekey.found(rekey.added_rallies(rekey.read_page(page_before), old), old, new, lead) if page_before.exists() else {}
    log = rekey.moved(review.load_log(path), old, new, lead, adopted)
    review.save(path, log)
    if (match / review.COMMENTS).exists():
        shutil.copy2(match / review.COMMENTS, before / review.COMMENTS)
        review.write_comments(match, rekey.moved_comments(review.read_comments(match), old, new, lead, adopted))
    if (before / "review-data.js").exists():
        page, _ = web.match_data(match, video, Calibration.load(court))
        review.save(path, rekey.with_reports(log, rekey.renamed_reports(rekey.read_page(before / "review-data.js"), page, review.read_places(before / "review-ball3d.js"))))
    return record(match, video, court, replaced, update)


def record(match: Path, video: Path, court: Path, replaced: dict[str, Score] | None = None, update: str | None = None) -> dict[str, Score]:
    """`scores`, added to learn.json with those of the results they `replaced` and the app's `update` they are part
    of; printed against the last ones."""
    path = match / HISTORY
    history = json.loads(path.read_text()) if path.exists() else []
    now = scores(match, video, court)
    print(report(now, history[-1]["scores"] if history else None))
    # The answers it saw: the review asks for another run once they change.
    stamp = review.answers_stamp(review.load_log(match / "identity_answers.json"))
    history.append({"time": time.strftime("%Y-%m-%d %H:%M"), "commit": commit(), "scores": now, "answers": stamp, **({"before": replaced} if replaced else {}), **({"update": update} if update else {})})
    files.write_text(path, json.dumps(history, indent=1) + "\n")
    return now


def waiting(outputs: Path) -> list[tuple[Path, Path, Path]]:
    """The matches of `outputs` an update would take (`review.due`), with their video and court, oldest first."""
    found = []
    for source in sorted(outputs.glob(f"*/{files.SOURCE}")):
        match, given = source.parent, json.loads(source.read_text())
        video, court = Path(given["video"]), Path(given["court"])
        if video.exists() and court.exists() and review.due(match):
            found.append((match, video, court))
    return found


def update(outputs: Path, only: str | None = None) -> None:
    """Every match of `outputs` waiting brought up to date, or the one named `only`: the learned order trained once on
    all the matches' answers, then each one's pipeline again with its pages, the answers applied (`review.rebuilt`); a
    fully checked one only measured, the play model then trained again if one taught it something. Its stages told as
    it goes (jobs.Stages)."""
    pick = lambda: [m for m in waiting(outputs) if only is None or m[0].name == only]  # noqa: E731
    found = pick()
    if not found:
        print("Nothing to update.", flush=True)
        return
    told = jobs.Stages(files.root(found[0][0]) / TIMINGS, ["training", *(f"match:{m.name}" for m, *_ in found)], TOOK)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    told.start("training")
    train(outputs)
    # A new learned order makes every match's analysis older: each one not fully checked waits too.
    found = pick()
    told.plan = ["training", *(f"match:{m.name}" for m, *_ in found)]
    taught = None
    for match, video, court in found:
        told.start(f"match:{match.name}")
        print(f"{match.name}:", flush=True)
        if review.reviewed(review.page_data(match / "review"), review.load_log(match / "identity_answers.json")):
            measured(match, video, court, started)
            taught = taught or (match if play_due(match) else None)
        else:
            rerun(match, video, court, on_share=told.share_of_stage, update=started)
            review.rebuilt(match, video, court)
    if taught:
        told.plan.append("play")
        told.start("play")
        train_play(taught)
    told.start(None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    if "--update" in sys.argv:
        parser.add_argument("--update", type=Path, required=True, help="Bring every match of this folder up to date")
        parser.add_argument("--only", help="That match only (its folder's name), after the same training")
        args = parser.parse_args()
        return update(args.update, args.only)
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    parser.add_argument("--labels", help="The match's name in the rallies benchmark (default: the folder's)")
    parser.add_argument("--rerun", action="store_true", help="Run the pipeline again first, the answers moved onto its rallies")
    args = parser.parse_args()
    if args.rerun:
        train(args.match.parent)
        rerun(args.match, args.video, args.court)
    elif args.labels:
        print(report(scores(args.match, args.video, args.court, args.labels), None))
    else:
        record(args.match, args.video, args.court)


if __name__ == "__main__":
    main()
