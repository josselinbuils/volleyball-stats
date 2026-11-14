"""How often the review editor's doubts (`checks.ts`, `doubtful`) sit on a correction, on a scored run of this benchmark:
before and after a team's 2nd-touch set is spared (`relanceSecond`), each doubt's share against chance.

    uv run python benchmarks/corrections/doubts.py MATCH RUN

ponytail: `doubtful` ported by hand, the rally's last touch scoring as points.csv's winner says (the page's reading
is finer): port again when checks.ts changes, or run the TypeScript on the run's touches."""
import json, sys
from collections import Counter
from pathlib import Path
from volleyball_stats import actions, learn, web

BASE = Path("outputs/benchmarks/corrections")
name, run = sys.argv[1], sys.argv[2]
truth = json.loads((BASE / name / "truth.json").read_text())
folder = BASE / name / "runs" / run / name
fixes = json.loads((BASE / name / "runs" / run / "corrections.json").read_text())
fps = truth["fps"]
rows = learn.read_rows(folder / "actions.csv")
windows = learn.read_rows(folder / "rallies.csv")
points = {r["start_frame"]: r for r in learn.read_rows(folder / "points.csv")}
lead, within = round(actions.LEAD_S * fps), round(learn.SAME_S * fps)
DOUBLE_SAME, DOUBLE_OTHER = 0.3, 0.25


def overlapping(start, end):
    best = max(windows, key=lambda w: min(end, int(w["end_frame"])) - max(start, int(w["start_frame"])), default=None)
    return best if best and min(end, int(best["end_frame"])) > max(start, int(best["start_frame"])) else None


def doubtful(touches, exempt):
    """checks.ts `doubtful` on the touches of the ball: [(index, problem)]."""
    out = []
    runs = []
    for n, c in enumerate(touches):
        runs.append(0 if c["type"] == "block" else runs[n - 1] + 1 if n and touches[n - 1]["team"] == c["team"] else 1)
    set_over = lambda n: exempt and touches[n]["type"] == "set" and runs[n] == 2  # noqa: E731
    for n in range(1, len(touches)):
        before, c = touches[n - 1], touches[n]
        same = before["team"] == c["team"]
        blocked = before["type"] == "block" or c["type"] == "block"
        apart = c["t"] - before["t"]
        if (apart <= DOUBLE_SAME) if same else (apart <= DOUBLE_OTHER and not blocked):
            out.append((n, "doubleTouch"))
        if blocked:
            continue
        if same and before["type"] in ("attack", "relance"):
            out.append((n, "overThenSameTeam"))
        if not same and before["type"] == "set" and not set_over(n - 1):
            out.append((n - 1, "setToOtherTeam"))
        if not same and c["type"] == "set":
            out.append((n, "setFirst"))
        if same and c["type"] in ("dig", "pass"):
            out.append((n, "digLater"))
        if same and before["type"] == "set" and c["type"] == "set":
            out.append((n, "twoSets"))
    if touches:
        last = touches[-1]
        if last["type"] == "set" and not set_over(len(touches) - 1):
            out.append((len(touches) - 1, "endsOnSet"))
        elif last["result"] == "point" and last["type"] in ("pass", "dig"):
            out.append((len(touches) - 1, "pointOnTouch"))
    return out


def on_touch(f):
    """A correction on the pipeline touch at frame f: removed, retyped or its player changed."""
    for x in fixes:
        if x["kind"] == "remove" and x["frame"] == f:
            return True
        if x["kind"] == "type" and x["pipe_frame"] == f:
            return True
        if x["kind"] == "player" and abs(x["frame"] - f) <= within:
            return True
    return False


def near(f):
    """Any correction to a touch (not a winner) within 1 s of frame f."""
    return any(x["kind"] != "winner" and abs(x["frame"] - f) <= fps for x in fixes)


all_touches, flags = [], {False: [], True: []}
for r in truth["rallies"]:
    w = overlapping(r["start_frame"], r["end_frame"])
    winner = points.get(w["start_frame"], {}).get("winner") if w else None
    auto = [x for x in rows if r["start_frame"] - lead <= int(x["frame"]) <= r["end_frame"] and x["type"] not in web.NO_PLAYER and x["type"] != "fault"]
    touches = [{"type": x["type"], "team": x["team"], "t": int(x["frame"]) / fps, "f": int(x["frame"]), "result": "play"} for x in auto]
    if touches and winner:
        touches[-1]["result"] = "point" if touches[-1]["team"] == winner else "error"
    all_touches += touches
    for exempt in (False, True):
        flags[exempt] += [(touches[n]["f"], p) for n, p in doubtful(touches, exempt)]

chance = (sum(on_touch(c["f"]) for c in all_touches), sum(near(c["f"]) for c in all_touches), len(all_touches))
print(f"{name} [{run}]: {chance[2]} pipeline touches in {len(truth['rallies'])} checked rallies; by chance {chance[0] / chance[2]:.0%} on the touch, {chance[1] / chance[2]:.0%} within 1 s")
for exempt in (False, True):
    fl = flags[exempt]
    print(f"\n{'after' if exempt else 'before'} (2nd-touch set exempt: {exempt}): {len(fl)} flags, {sum(on_touch(f) for f, _ in fl) / len(fl):.0%} on the touch, {sum(near(f) for f, _ in fl) / len(fl):.0%} within 1 s")
    for p, n in Counter(p for _, p in fl).most_common():
        hits = [f for f, q in fl if q == p]
        print(f"  {p:18} {n:4}  on the touch {sum(map(on_touch, hits)):3} ({sum(map(on_touch, hits)) / n:.0%})  within 1 s {sum(map(near, hits)):3} ({sum(map(near, hits)) / n:.0%})")
dropped = [f for f in {x for x in flags[False]} - set(flags[True])]
print(f"\ndropped: {len(dropped)}: {Counter(p for _, p in dropped)}, on the touch {sum(on_touch(f) for f, _ in dropped)}, within 1 s {sum(near(f) for f, _ in dropped)}")
for f, p in sorted(dropped):
    print(f"  {p} at {f / fps:.2f} s: {[x['kind'] + ':' + str(x.get('truth_type', '')) for x in fixes if x['kind'] != 'winner' and abs(x['frame'] - f) <= fps]}")
