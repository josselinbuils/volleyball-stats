"""The review's applies (the server is review_server.py, the questions review_questions.py, the answers and names
review_answers.py): what an apply takes in, its undo, the rallies checked, locked and commented, and how long a run takes.

    uv run python -m volleyball_stats.review_server outputs/matches/VIDEO --video VIDEO --court COURT_JSON [--squad N[,N]] [--theme NAME] [--roster PATH] [--port PORT]

Builds the match page like web.py, with the video and every player's picture, into MATCH/review/,
apart from the page to publish (MATCH/site/, rebuilt with its own choices on "apply"), then serves
it on this machine only, with a review mode at /review: one question at a time from identity_candidates.json, the player outlined on the video
beside pictures of the identities they could be. Each answer is saved at once to
identity_answers.json as hard constraints (identity.py); "apply" and "undo" rerun the identity step
and rebuild the page, in seconds. The review also names the players: each identity's name and
jersey number go to player_names.json, applied likewise. Answers and names refer to pieces of
player tracks, so they hold until the players are tracked again.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from volleyball_stats import analysis, film, files, web
from volleyball_stats.review_answers import KINDS, checked, corrections, load_log, reviewed, save, state, touch_answer

# ponytail: web.framed imports CROP_MARGIN from here, and the pictures' scores stamp (web.scores_stamp) reads its source:
# importing it from review_questions there would score every match's pictures again. Move it with the next change to scoring.
from volleyball_stats.review_questions import CROP_MARGIN  # noqa: F401


# What the identities were last computed from (`state`), to tell what an apply would change.
APPLIED = "identity_applied.json"
# Marks a review page waiting for its players' pictures, for after a restart.
STALE_PHOTOS = "photos_stale"


def pooled_runs(outputs: Path) -> list[dict]:
    """The analysis runs (learn.json) of all the matches in `outputs`, in time order, each scored on
    every match measured so far, at its latest run then: progress since the beginning, a match joining
    it adding its answers rather than starting a new curve."""
    runs = []
    for path in sorted(outputs.glob("*/learn.json")):
        runs += [(run["time"], path.parent.name, run) for run in json.loads(path.read_text())]
    latest: dict[str, dict] = {}
    out = []
    for _, name, run in sorted(runs, key=lambda r: r[:2]):
        latest[name] = run["scores"]
        scores: dict[str, list[int]] = {}
        for found in latest.values():
            for key, (right, total) in found.items():
                sums = scores.setdefault(key, [0, 0])
                sums[0], sums[1] = sums[0] + right, sums[1] + total
        out.append({"time": run["time"], "commit": run["commit"], "match": name, "scores": scores})
    return out


def last_comparison(outputs: Path) -> dict | None:
    """The scores of the last update's runs (learn.json, its `update`; the newest run alone before 14 Nov 2026) and of
    the results they replaced, on the same answers, summed over its matches; None if it did not measure them."""
    lasts = [runs[-1] for path in sorted(outputs.glob("*/learn.json")) if (runs := json.loads(path.read_text()))]
    if not lasts:
        return None
    newest = max(lasts, key=lambda r: r["time"])
    same = [r for r in lasts if "before" in r and (r is newest or (newest.get("update") and r.get("update") == newest["update"]))]
    if not same:
        return None

    def summed(found: list[dict]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for scores in found:
            for key, (right, total) in scores.items():
                sums = out.setdefault(key, [0, 0])
                sums[0], sums[1] = sums[0] + right, sums[1] + total
        return out

    return {"before": summed([r["before"] for r in same]), "after": summed([r["scores"] for r in same])}


# The owner's notes on the rallies, by key: outside the answers (no undo or apply touches them), and
# only review.js reads them, so no page holds them.
COMMENTS = "rally_comments.json"


def read_comments(match: Path) -> dict[int, str]:
    path = match / COMMENTS
    return {int(k): v for k, v in json.loads(path.read_text()).items()} if path.exists() else {}


def write_comments(match: Path, comments: dict[int, str]) -> None:
    files.write_text(match / COMMENTS, json.dumps({str(k): v for k, v in sorted(comments.items())}, ensure_ascii=False, indent=1) + "\n")


def commented(comments: dict[int, str], page: dict | None, log: list[dict]) -> dict[int, str]:
    """`comments` by the rallies `page` shows or a split not applied yet starts: one on a rally no
    longer there (joined to the one before, its split undone) goes to the rally holding its start;
    one in no rally (said no play) stays under its key, hidden."""
    rallies = (page or {}).get("rallies", [])
    known = {r.get("key") for r in rallies} | {a["frame"] for e in log for a in e.get("split", [])}
    out = {k: v for k, v in comments.items() if k in known}
    for key in sorted(set(comments) - known):
        holder = next((r["key"] for r in rallies if r["start"] * page["fps"] <= key <= r["end"] * page["fps"]), key)
        out[holder] = f"{out[holder]}\n{comments[key]}" if holder in out else comments[key]
    return out


def pinned(page: dict | None, keys: list[int]) -> list[dict]:
    """An answer pinning the winners `page` shows for the rallies checked (`keys`): they stay
    whatever the rallies around them become (`web.served_next`); a winner the review gives still
    wins. None without one to pin. The page shows them already: applied."""
    found = [{"start": r["key"], "winner": r["winner"]} for r in (page or {"rallies": []})["rallies"] if r.get("key") in set(keys) and r.get("winner")]
    return [{"id": "pin", "choice": "pinned", "pinned": found, "applied": True}] if found else []


def locked(page: dict | None, keys: list[int], given: dict[tuple[int, int], dict]) -> list[dict]:
    """An answer locking the rallies checked (`keys`) as `page` shows them: each touch's named
    player (`touch`), action and result (`action`), the second player of a fault shared (`partner`), and the touches themselves (`locked`: the page
    keeps those, re-adds one a rerun loses and lets in no other but those the review adds). None
    without one to lock. The page shows them already: applied."""
    out: dict[str, list] = defaultdict(list)
    people = (page or {}).get("people") or {}
    for k, r in enumerate((page or {"rallies": []})["rallies"]):
        if r.get("key") not in set(keys):
            continue
        mine = []
        for c in page["contacts"]:
            if c["rally"] != k or c["type"] in web.NO_PLAYER or not c.get("team"):
                continue
            frame = c.get("f", round(c["t"] * page["fps"]))
            mine.append({"frame": frame, "team": c["team"], "type": c["type"]})
            out["action"].append({"frame": frame, "type": c["type"], "result": web.labelled(c), **({"cause": c["cause"]} if c.get("cause") else {})})
            # Keyed by text once read from data.js.
            p = people.get(str(c["person"]), people.get(c["person"])) if c.get("person") is not None else None
            if p and p.get("number") is not None and p["team"] == c["team"]:
                out["touch"] += touch_answer({"frame": frame, "team": c["team"]}, f"player:{p['team']}:{p['number']}", given)["touch"]
            q = people.get(str(c["partner"]), people.get(c["partner"])) if c.get("partner") is not None else None
            if q and q.get("number") is not None:
                out["partner"] += touch_answer({"frame": frame, "team": q["team"]}, f"player:{q['team']}:{q['number']}", given)["touch"]
        out["locked"].append({"start": r["key"], "touches": mine})
    return [{"id": "lock", "choice": "locked", **out, "applied": True}] if out else []


def unlocked(keys: list[int]) -> list[dict]:
    """An answer unlocking the rallies unchecked (`keys`): their touches stay as answered."""
    return [{"id": "unlock", "choice": "unlocked", "locked": [{"start": k, "touches": None} for k in keys], "applied": True}] if keys else []


# Each step's and pipeline stage's duration in seconds before one is measured: the first ASPOM
# match, 4K, on the M4 (1 Nov); "play" and "playTraining" on the RTX 5080 (12 Nov), "pipeline:identity" there too with its
# embeddings computed (17 Nov, 0.39 s per second of video).
TOOK = {
    "reports": 3.0, "training": 270.0, "playTraining": 2400.0, "pipeline": 2400.0, "players": 25.0, "questions": 3.0, "roster": 1.0, "review": 15.0, "page": 10.0, "hosting": 60.0, "hostingAll": 120.0, "copies": 4800.0, "films": 2400.0, "film": 180.0, "highlights": 300.0,
    "pipeline:tracking": 7200.0, "pipeline:play": 620.0, "pipeline:rallies": 25.0, "pipeline:actions": 640.0, "pipeline:wrists": 790.0, "pipeline:gesture": 480.0, "pipeline:teams": 880.0, "pipeline:jerseys": 2400.0, "pipeline:scoreboard": 360.0,
    "pipeline:identity": 1560.0, "pipeline:jumps": 420.0, "pipeline:answers": 60.0,
}
# The pipeline's stages in order (match.stage): "tracking" only when the trackers run again, "play" only with its model
# (`playing.available`) on a match it has not seen, "gesture" only with its model (`gesture.wanted`).
STAGES = ("tracking", "play", "rallies", "actions", "wrists", "gesture", "teams", "jerseys", "scoreboard", "identity", "jumps", "answers")
TIMINGS = "review_timings.json"


def eta(progress: dict, took: dict[str, float], now: float) -> dict:
    """Where a run of steps (`progress`: their names, the one running since when, its stage since when, the share it
    counted, `own`) stands at `now`. Only counted work moves it (the owner's rule): the whole run's share (`fraction`),
    each step and stage weighted by its last duration (`weights`, kept as the run started, else `took`), the running
    one's counted share (`part`, None while it counts nothing: the bar holds); the time spent and left, from the pace
    of the counted share, else the last duration; and whether the step or stage runs longer than it did (`late`)."""
    weights = progress.get("weights") or took
    steps, done, stage, own = progress["steps"], progress["done"], progress.get("stage"), progress.get("own")
    step = steps[done]
    if stage:
        later = [s for s in STAGES[STAGES.index(stage) + 1 :] if s not in ("tracking", "play")] if stage in STAGES else []
        spent, expected = now - progress["stage_since"], weights.get(f"{step}:{stage}", 0.0)
        rest = sum(weights.get(f"{step}:{s}", 0.0) for s in later)
    else:
        spent, expected = now - progress["since"], weights.get(step, 1.0)
        rest = 0.0
    counted = own is not None and own > 0.01
    here = spent * (1 - own) / own if counted else max(0.0, expected - spent)
    left = here + rest + sum(weights.get(s, 1.0) for s in steps[done + 1 :])
    whole = weights.get(step, 1.0)
    within = min(whole, progress.get("passed", 0.0) + (own or 0.0) * (expected if stage else whole))
    fraction = (sum(weights.get(s, 1.0) for s in steps[:done]) + within) / max(sum(weights.get(s, 1.0) for s in steps), 1e-9)
    late = spent / own > expected > 0 if counted else 0 < expected < spent
    return {"steps": steps, "done": done, "stage": stage, "elapsed": now - progress["started"], "left": left, "late": late, "part": own, "fraction": min(1.0, fraction)}


def given(answers: dict) -> dict:
    """The kinds of `answers` with something said: a kind added since the last apply, empty, changes nothing."""
    return {kind: said for kind, said in answers.items() if said}


# What an apply takes in, by what the answers are about (`waiting`'s `toApply`): an answer counts once, under its first.
ABOUT = {
    "players": ("same", "different", "not_player", "cut", "team", "join", "split"),
    "touches": ("touch", "receiver", "partner"),
    "actions": ("action", "added", "wrong", "redo"),
    "rallies": ("rally", "winner", "end", "referee"),
}


def to_apply(log: list[dict], changed: dict[str, bool]) -> list[list]:
    """What an apply takes in, for its button: the answers not applied yet by what they are about, with how many, then
    `changed`'s parts ("answers" when the answers differ with none of those, as after an undo)."""
    counts = dict.fromkeys(ABOUT, 0)
    for e in log:
        said = [kind for kind in KINDS if e.get(kind)]
        if not e.get("applied", True) and said:
            counts[next((a for a, kinds in ABOUT.items() if set(kinds) & set(said)), "rallies")] += 1
    out = [[about, n] for about, n in counts.items() if n]
    return out + [[part, None] for part, on in changed.items() if on and not (part == "answers" and out)]


def applied_too(match: Path, entries: list[dict]) -> None:
    """`entries`, saying what the page shows already, first in what the identities were computed from (APPLIED), as they
    are first in the log: else they would show as answers to apply."""
    computed = match / APPLIED
    if not computed.exists():
        return
    then = json.loads(computed.read_text())
    answers = then.setdefault("answers", {})
    for kind in KINDS:
        said = [x for e in entries for x in e.get(kind, [])]
        if said and kind not in ("pinned", "locked"):
            answers[kind] = said + answers.get(kind, [])
    files.write_text(computed, json.dumps(json.loads(json.dumps(then))))


def waiting(match: Path, log: list[dict], shown: set[str] | frozenset[str] = frozenset()) -> dict:
    """What an apply would take in: the answers saying something not applied yet (those saved
    before the flag were), whether the answers or the jersey numbers, and the names, differ from
    what the identities were computed from (APPLIED); the reports' `corrections` the review's
    page does not show yet (`shown`: the answers it was built with), the rallies `checked`, the
    `films` to make, players' and highlights, and whether the last learning run saw these answers."""
    computed = match / APPLIED
    now, then = state(match, log), files.read_json(computed, {})
    parts = {
        "answers": given(now["answers"]) != given(then.get("answers") or {}),
        # The jersey numbers' time to the second: a copy through the server (`sync`) keeps no less.
        "jerseys": now["jerseys"] != (None if then.get("jerseys") is None else int(then["jerseys"])),
        "timeouts": now["timeouts"] != then.get("timeouts", []),
        "names": now["names"] != then.get("names"),
    }
    return {
        "pending": sum(not e.get("applied", True) and any(e.get(kind) for kind in KINDS) for e in log),
        "changed": parts["answers"] or parts["jerseys"] or parts["timeouts"],
        "namesPending": parts["names"],
        "toApply": to_apply(log, parts),
        "corrections": corrections(log, shown),
        "checked": checked(log),
        "films": film.status(match),
        "due": due(match, log),
    }


def answers_stamp(log: list[dict]) -> str:
    """What the answers say, applied or not: kept with each learning run (learn.json)."""
    said = [{k: v for k, v in e.items() if k != "applied"} for e in log]
    return hashlib.sha256(json.dumps(said, sort_keys=True).encode()).hexdigest()[:16]


def silent(answer: dict) -> bool:
    """Whether `answer` teaches nothing: a report marked handled as the rally stood, no correction, no rally checked."""
    return (
        answer.get("choice") == "report"
        and set(answer) <= {"id", "choice", "applied", "changes"}
        and not any((answer.get("changes") or {}).values())
    )


def learned(match: Path, log: list[dict]) -> bool:
    """Whether the match's last learning run (learn.json) saw the answers as they stand, but for those given since that
    teach nothing (`silent`): a report marked handled no longer asks for the match to be analysed again."""
    path = match / "learn.json"
    runs = files.read_json(path, [])
    if not runs:
        return False
    n = len(log)
    while answers_stamp(log[:n]) != runs[-1].get("answers"):
        if not n or not silent(log[n - 1]):
            return False
        n -= 1
    return True


def due(match: Path, log: list[dict] | None = None) -> str | None:
    """Why the app's update would take `match` (learn.update): "answers" given since it last learned from them, "rules"
    when other code or models made its analysis (analysis.py); None for one up to date, or not analysed yet. A fully
    checked match keeps its labels: only new answers make it wait."""
    if not (match / "report.md").exists():
        return None
    log = load_log(match / "identity_answers.json") if log is None else log
    if log and not learned(match, log):
        return "answers"
    if reviewed(web.page_data(match / "review"), log):
        return None
    return "rules" if analysis.made_by(match) != analysis.fingerprint(match) else None


def rebuilt(match: Path, video: Path, court: Path, theme: str = web.CLUB) -> None:
    """`match`'s pages made again once its pipeline ran again outside the review (learn.update), its answers then
    applied, as the review's own reruns leave them."""
    web.review_page(match, video, court, theme)
    (match / STALE_PHOTOS).unlink(missing_ok=True)
    if (match / "page.json").exists():
        web.publish(match, video, court, theme, {})
    path = match / "identity_answers.json"
    log = [{**e, "applied": True} for e in load_log(path)]
    if path.exists():
        save(path, log)
    files.write_text(match / APPLIED, json.dumps(state(match, log)))


def undo(log: list[dict], history: list[dict]) -> tuple[list[dict], list[dict] | None, str | None, bool]:
    """The answers as they were before the last change of `history` ({"log", "names": None unless
    it moved names, "applied": whether an apply followed it}, popped), else (`history` empty: the
    server restarted) without the last answer. With the names to write back (None to keep them),
    the id of the answer taken away, and whether the identities followed what is undone."""
    if history:
        last = history.pop()
        kept = {e["id"] for e in last["log"]}
        return last["log"], last["names"], next((e["id"] for e in reversed(log) if e["id"] not in kept), None), last["applied"]
    return log[:-1], None, log[-1]["id"], log[-1].get("applied", True)


if __name__ == "__main__":
    # The review's command before review_server.py: a server started by an older app restarts so.
    from volleyball_stats.review_server import main

    main()
