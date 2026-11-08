"""The pipeline's windows (`match.rally_windows`, as bench.py's `pipeline`) with their ends moved by a clip model's P(play)
(`play.py`), scored on the labelled spans of the first match.

    uv run python benchmarks/rallies/play_ends.py MODEL_TAG [--grid] [--checked MATCH]

`--checked` scores the windows match.py writes on MATCH's checked rallies (`checked.py`) with MODEL_TAG's P(play) on it.
"""

import argparse
import csv
import json
import sys
from itertools import product
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import bench  # noqa: E402
import play  # noqa: E402

from volleyball_stats import actions, rallies  # noqa: E402
from volleyball_stats.court import Calibration  # noqa: E402
from volleyball_stats.match import rally_windows  # noqa: E402

MATCH = "2026-10-29-aspom-1-vs-aspom-2"
SPANS = {"26-36": ("first_match_26_36", 1560, 2160), "50-60": ("first_match_50_60", 3000, 3600)}


def windows(name: str) -> tuple[list[tuple[int, int]], float, list]:
    cache = play.OUT / name / "windows.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return [tuple(w) for w in d["windows"]], d["fps"], d["whistles"]
    d = play.match_dir(name)
    source = json.loads((d / "source.json").read_text())
    video, cal = Path(source["video"]), Calibration.load(Path(source["court"]))
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    with open(d / "players.csv") as f:
        players = [(int(r["frame"]), float(r["court_x"]), float(r["court_y"])) for r in csv.DictReader(f)]
    whistle_times = rallies.whistles(rallies.read_audio(video))
    out = rally_windows(rallies.load_track(d / "ball.csv"), whistle_times, fps, float(cal.to_image(np.array([[0.0, 0.0]]))[0, 0]), cal, players)[0]
    cache.write_text(json.dumps({"windows": out, "fps": fps, "whistles": whistle_times}))
    return out, fps, whistle_times


def moved(wins, fps, times, p, threshold=0.3, back_s=10.0, ahead_s=15.0, offset_s=0.0, gap_s=1.0, margin_s=1.5, cut=False, extend=True):
    """Each window's end moved where P(play) over `threshold` (dips under `gap_s` bridged) says play stops, when it says so
    `margin_s` or more away: on through a live run up to `ahead_s` after it, back to the last live moment up to `back_s`
    before it; never before the window's start + MIN_RALLY_S nor into the next window. A window P never finds live stays."""
    live = p > threshold
    step = times[1] - times[0]
    # Bridge short dips.
    for a, b in rallies.runs(~live, 0, 1):
        if b - a + 1 <= gap_s / step and a > 0 and b + 1 < len(live):
            live[a : b + 1] = True
    out = []
    for k, (start, end) in enumerate(wins):
        following = wins[k + 1][0] - round(actions.LEAD_S * fps) if k + 1 < len(wins) else 1 << 40
        t_start, t_end = start / fps, end / fps
        lo, hi = max(t_start + rallies.MIN_RALLY_S, t_end - back_s), min(t_end + ahead_s, following / fps)
        inside = (times >= t_start) & (times <= t_end)
        i = min(int(np.searchsorted(times, t_end)), len(times) - 1)
        new = t_end
        if not live[inside].any():
            pass
        elif live[i]:
            if extend:
                while i + 1 < len(times) and live[i + 1] and times[i + 1] <= hi:
                    i += 1
                new = times[i] + offset_s
        elif cut:
            while i > 0 and not live[i] and times[i] >= lo:
                i -= 1
            if live[i]:
                new = times[i] + offset_s
        if abs(new - t_end) < margin_s:
            new = t_end
        new = min(max(new, lo), hi) if lo <= hi else t_end
        out.append((start, round(new * fps)))
    return out


def scores(wins, fps):
    out = {}
    for key, (gt, a, b) in SPANS.items():
        lo, hi = round(a * fps), round(b * fps)
        truth = [(s, e) for s, e in bench.load_ground_truth(Path(f"benchmarks/rallies/ground_truth/{gt}.csv")) if lo <= s < hi]
        pred = [(s, e) for s, e in wins if lo <= s < hi]
        s1, s2 = bench.score(pred, truth, round(fps), fps), bench.score(pred, truth, round(2 * fps), fps)
        ends = [abs(p[1] - t[1]) / fps for t, p in bench.match(pred, truth, round(30 * fps)) if p is not None]
        out[key] = (round(s1["F1"], 2), round(s2["F1"], 2), round(float(np.mean(ends)), 2))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--grid", action="store_true")
    parser.add_argument("--checked")
    args = parser.parse_args()
    if args.checked:
        checked_scores(args.checked, args.tag)
        return
    wins, fps, _ = windows(MATCH)
    d = np.load(play.OUT / "models" / args.tag / f"{MATCH}.npz")
    times, p = (d["starts"] + play.T / 2) / play.FPS, d["p"]
    print("pipeline", scores(wins, fps))
    print("moved", scores(moved(wins, fps, times, p), fps))
    if args.grid:
        for th, off, gap, margin in product((0.3, 0.5, 0.7), (-0.5, 0.0, 0.5), (0.0, 1.0, 2.0), (0.0, 1.0, 1.5, 2.0)):
            kw = dict(threshold=th, offset_s=off, gap_s=gap, margin_s=margin, cut=True)
            print(kw, scores(moved(wins, fps, times, p, **kw), fps))


if __name__ == "__main__":
    main()


def checked_scores(name: str, tag: str, **kw) -> None:
    """checked.py's score of the windows match.py writes, the ends as they are and moved by P(play)."""
    import checked

    from volleyball_stats import attribution, learn, match, review

    d = play.match_dir(name)
    source = json.loads((d / "source.json").read_text())
    video, cal = Path(source["video"]), Calibration.load(Path(source["court"]))
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    net_x = float(cal.to_image(np.array([[0.0, 0.0]]))[0, 0])
    page = review.page_data(d / "review")
    keys = set(review.checked(review.load_log(d / "identity_answers.json")))
    ch = {k: r for k, r in enumerate(page["rallies"]) if r["key"] in keys}
    lead = round(actions.LEAD_S * fps)
    spans = [(round(r["start"] * fps) - lead, round(r["end"] * fps)) for r in ch.values()]
    rows = attribution.read_players(d / "players.csv")
    whistle_times = windows(name)[2]
    track = rallies.load_track(d / "ball.csv")
    base, found, crossings = match.rally_windows(track, whistle_times, fps, net_x, cal, [(r.frame, *r.court) for r in rows])
    z = np.load(play.OUT / "models" / tag / f"{name}.npz")
    times, p = (z["starts"] + play.T / 2) / play.FPS, z["p"]
    first, last = min(s for s, _ in spans) - round(actions.SERVE_BEFORE_S * fps), max(e for _, e in spans)
    within = round(learn.SAME_S * fps)
    touches = [c["f"] for c in page["contacts"] if c["rally"] in ch]
    for label, wins in (("as is", base), ("moved", moved(base, fps, times, p, **kw))):
        wins, typed = match.typed_windows(wins, found, crossings, fps, net_x, cal, rows, track, whistle_times)
        rally = [match.rally_of(t[0], wins, lead) for t in typed]
        typed, _ = actions.mark_dead(typed, [c[0][2] if c else None for c in attribution.ranked(typed, rows, fps)], rally)
        idle = actions.no_play(typed, rally, wins, crossings, fps)
        wins = [w for k, w in enumerate(wins) if k not in idle]
        print(name, label, checked.score([w for w in wins if first <= w[0] <= last], [t[0] for t in typed], spans, touches, lead, within), flush=True)
