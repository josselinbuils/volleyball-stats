"""The views the review's automatic zoom follows: all the players at the serve, then for the exchange.

The camera is fixed and the court fills most of its picture, so a view gains little over the next:
it is kept while it still fits, to change as rarely as possible.
"""

from pathlib import Path

import numpy as np

# The seconds around the serve whose players its view shows.
SERVE_S = (2.0, 0.2)
# The exchange's view comes this long after the serve, the server having hit the ball.
AFTER_SERVE_S = 0.3
# The view stays this long after a rally's end.
HOLD_S = 1.0
# A shorter exchange keeps the serve's view.
MIN_EXCHANGE_S = 1.0
# A track seen less than this in a moment is no player: a false detection.
MIN_TRACK_S = 0.5
# Around the players, in fractions of the picture; under them only, the rest above for the high balls.
MARGIN = 0.03
# The tightest view, in fractions of the picture, should the tracking lose players.
MIN_VIEW = 0.5
# A view still showing the players, MARGIN or not, is kept unless this much wider than needed.
KEPT_WIDER = 1.3
STEP_S = 0.1


def read_boxes(path: Path, size: tuple[int, int], fps: float) -> np.ndarray:
    """players.csv's [time, track, x1, y1, x2, y2] every STEP_S by time, boxes in fractions of the picture."""
    step = max(1, round(STEP_S * fps))
    rows = []
    with open(path) as f:
        f.readline()
        for line in f:
            frame = int(line[: line.index(",")])
            if frame % step == 0:
                _, track, _, x1, y1, x2, y2 = line.split(",", 7)[:7]
                rows.append((frame / fps, int(track), float(x1) / size[0], float(y1) / size[1], float(x2) / size[0], float(y2) / size[1]))
    boxes = np.array(rows, dtype=float).reshape(-1, 6)
    return boxes[np.argsort(boxes[:, 0], kind="stable")]


def players_box(boxes: np.ndarray, start: float, end: float) -> tuple[float, float, float, float] | None:
    """What the players of `boxes` (`read_boxes`) cover between `start` and `end`, with MARGIN; None without any."""
    here = boxes[np.searchsorted(boxes[:, 0], start) : np.searchsorted(boxes[:, 0], end, side="right")]
    tracks, counts = np.unique(here[:, 1], return_counts=True)
    here = here[np.isin(here[:, 1], tracks[counts * STEP_S >= MIN_TRACK_S])]
    if not len(here):
        return None
    return (max(0, here[:, 2].min() - MARGIN), max(0, here[:, 3].min() - MARGIN), min(1, here[:, 4].max() + MARGIN), min(1, here[:, 5].max() + MARGIN))


def view_of(box: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """The view [x, y, width] showing `box`, at the picture's shape (its width and height the same fraction of the picture), `box` at its bottom."""
    x1, y1, x2, y2 = box
    w = min(1.0, max(x2 - x1, y2 - y1, MIN_VIEW))
    return float(min(1 - w, max(0, (x1 + x2 - w) / 2))), float(min(1 - w, max(0, y2 - w))), float(w)


def views(boxes: np.ndarray, rallies: list[dict], touches: list[dict]) -> list[list[float]]:
    """The views as [from this time, x, y, width], in fractions of the picture, from the rallies and their `touches`
    (data.js's, without the ball's floor and net contacts): each serve's from the rally before's end, the exchange's
    once the serve is hit, the whole picture after the last rally."""
    shown: list[list[float]] = []

    def show(at: float, box: tuple[float, float, float, float] | None) -> None:
        if box is None:
            return
        view = view_of(box)
        if shown:
            _, x, y, w = shown[-1]
            if x <= box[0] + MARGIN and y <= box[1] + MARGIN and x + w >= box[2] - MARGIN and y + w >= box[3] - MARGIN and w <= view[2] * KEPT_WIDER:
                return
        shown.append([round(float(at), 2), *(round(v, 4) for v in view)])

    end = 0.0
    for k, rally in enumerate(rallies):
        own = [t for t in touches if t["rally"] == k]
        served = next((t["t"] for t in own if t["type"] == "serve"), rally["start"])
        show(min(end + HOLD_S, served) if k else 0, players_box(boxes, served - SERVE_S[0], served + SERVE_S[1]))
        answered = next((t["t"] for t in own if t["t"] > served and t["type"] != "serve"), None)
        if answered is not None and rally["end"] - answered >= MIN_EXCHANGE_S:
            show(min(served + AFTER_SERVE_S, answered), players_box(boxes, answered, rally["end"]))
        end = rally["end"]
    if shown:
        shown.append([round(end + HOLD_S, 2), 0, 0, 1])
    return shown
