"""Rally windows scored on the rallies a match's review checked, labels of the whole match.

    uv run --group bench python benchmarks/rallies/checked.py outputs/matches/MATCH --video VIDEO --court COURT_JSON
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import actions, attribution, learn, match, rallies, review
from volleyball_stats.court import Calibration

Window = tuple[int, int]


def score(windows: list[Window], found: list[int], spans: list[Window], touches: list[int], lead: int, within: int) -> dict[str, int]:
    """Touches with a contact in a window, contacts in windows that are no touch, windows on no rally, rallies with no window."""
    inside = [f for f in found if any(start - lead <= f <= end for start, end in windows)]
    return {
        "touches": sum(learn.near(t, inside, within) is not None for t in touches),
        "of": len(touches),
        "no touch": sum(learn.near(f, touches, within) is None for f in inside),
        "false windows": sum(not any(a <= end + within and start - within <= b for a, b in spans) for start, end in windows),
        "rallies missed": sum(not any(a <= end and start <= b for start, end in windows) for a, b in spans),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    args = parser.parse_args()

    fps = cv2.VideoCapture(str(args.video)).get(cv2.CAP_PROP_FPS)
    calibration = Calibration.load(args.court)
    net_x = float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    page = review.page_data(args.match / "review")
    keys = set(review.checked(review.load_log(args.match / "identity_answers.json")))
    checked = {k: r for k, r in enumerate(page["rallies"]) if r["key"] in keys}
    lead = round(actions.LEAD_S * fps)
    spans = [(round(r["start"] * fps) - lead, round(r["end"] * fps)) for r in checked.values()]
    positions = [(r.frame, *r.court) for r in attribution.read_players(args.match / "players.csv")]
    whistles = rallies.whistles(rallies.read_audio(args.video))
    windows, found, _ = match.rally_windows(rallies.load_track(args.match / "ball.csv"), whistles, fps, net_x, calibration, positions)
    first, last = min(start for start, _ in spans) - round(actions.SERVE_BEFORE_S * fps), max(end for _, end in spans)
    within = round(learn.SAME_S * fps)
    touches = [c["f"] for c in page["contacts"] if c["rally"] in checked]
    print(score([w for w in windows if first <= w[0] <= last], sorted(c[0] for c in found), spans, touches, lead, within))


if __name__ == "__main__":
    main()
