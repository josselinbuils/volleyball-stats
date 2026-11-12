"""The uses of P(play) on the pipeline's windows, each alone and together, scored as `checked.py` does (and on the labelled spans of the
first match), the model always held out.

    uv run python benchmarks/rallies/play_uses.py MATCH P_NPZ [--uses ends starts keep alive ends,starts,keep,alive]

P_NPZ is the held-out model's output on MATCH (`play.py` / `play_candidates.py`).
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import checked  # noqa: E402
import play  # noqa: E402
import play_ends  # noqa: E402

from volleyball_stats import actions, attribution, learn, match, playing, rallies, review  # noqa: E402
from volleyball_stats.court import Calibration  # noqa: E402


def run(name: str, npz: Path, combos: list[tuple[str, ...]]) -> None:
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
    whistle_times = play_ends.windows(name)[2]
    track = rallies.load_track(d / "ball.csv")
    base, found, crossings = match.rally_windows(track, whistle_times, fps, net_x, cal, [(r.frame, *r.court) for r in rows])
    times, p, _ = playing.load(npz)
    first, last = min(s for s, _ in spans) - round(actions.SERVE_BEFORE_S * fps), max(e for _, e in spans)
    within = round(learn.SAME_S * fps)
    touches = [c["f"] for c in page["contacts"] if c["rally"] in ch]
    for uses in [(), *combos]:
        wins = playing.moved(base, fps, times, p, uses) if uses else base
        alive = playing.goes_on(times, p, fps) if "alive" in uses else None
        wins, typed = match.typed_windows(wins, found, crossings, fps, net_x, cal, rows, track, whistle_times, alive)
        rally = [match.rally_of(t[0], wins, lead) for t in typed]
        typed, _ = actions.mark_dead(typed, [c[0][2] if c else None for c in attribution.ranked(typed, rows, fps)], rally, alive)
        idle = actions.no_play(typed, rally, wins, crossings, fps, playing.confirmed(wins, fps, times, p) if "keep" in uses else None)
        wins = [w for k, w in enumerate(wins) if k not in idle]
        result = checked.score([w for w in wins if first <= w[0] <= last], [t[0] for t in typed], spans, touches, lead, within)
        line = {"uses": "+".join(uses) or "none", "windows": len(wins), **result}
        if name.startswith("2026-10-29"):
            line["spans F1 1s/2s/end MAE"] = play_ends.scores(wins, fps)
        print(line, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("match")
    ap.add_argument("npz", type=Path)
    ap.add_argument("--uses", nargs="*", default=[*playing.USES, "ends,starts", "ends,starts,keep", ",".join(playing.USES)])
    args = ap.parse_args()
    run(args.match, args.npz, [tuple(u.split(",")) for u in args.uses])


if __name__ == "__main__":
    main()
