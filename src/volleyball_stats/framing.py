"""The views the automatic zoom follows, all the players at the serve, then for the exchange, and its camera.

The camera is fixed and the court fills most of its picture, so a view gains little over the next:
it is kept while it still fits, to change as rarely as possible.
"""

from pathlib import Path

import numpy as np

from volleyball_stats import player_table

# The seconds around the serve whose players its view shows.
SERVE_S = (2.0, 0.2)
# The exchange's view comes this long after the serve, the server having hit the ball.
AFTER_SERVE_S = 0.3
# The view stays this long after a rally's end, then the whole picture shows until SERVE_LEAD_S before the next serve
# (the owner's call, 15 Nov: between rallies the video stays centred), when the server's view comes.
HOLD_S, SERVE_LEAD_S = 1.0, 3.0
# A shorter exchange keeps the serve's view.
MIN_EXCHANGE_S = 1.0
# During the exchange a view every FOLLOW_S, of the players seen from BEHIND_S before it to AHEAD_S after: the camera
# averages the views a second either side and eases between them (`camera`) (the owner's call, 15 Nov: closer, every player and
# the ball kept in, parts of the court out).
FOLLOW_S, BEHIND_S, AHEAD_S = 1.0, 1.0, 1.5
# The ball this close to the serve is at the server, who often waits too far back to be tracked.
BALL_AT_SERVE_S = 0.2
# Around that ball, in fractions of the picture: the server's body besides MARGIN.
SERVER_MARGIN = 0.05
# A track seen less than this in a moment is no player: a false detection.
MIN_TRACK_S = 0.5
# Around the players, in fractions of the picture; under them only, the rest above for the high balls.
MARGIN = 0.03
# The tightest view, in fractions of the picture, should the tracking lose players.
MIN_VIEW = 0.4
# A view still showing the players, MARGIN or not, is kept unless this much wider than needed.
KEPT_WIDER = 1.15
STEP_S = 0.1


def read_boxes(path: Path, size: tuple[int, int], fps: float) -> np.ndarray:
    """players.csv's [time, track, x1, y1, x2, y2] every STEP_S by time, boxes in fractions of the picture."""
    step = max(1, round(STEP_S * fps))
    t = player_table.read(path)
    kept = t["frame"] % step == 0
    boxes = np.column_stack([t["frame"][kept] / fps, t["track"][kept], *(t[k][kept] / size[k[0] == "y"] for k in ("x1", "y1", "x2", "y2"))]).astype(float).reshape(-1, 6)
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


def with_server(box: tuple[float, float, float, float] | None, ball: np.ndarray, served: float) -> tuple[float, float, float, float] | None:
    """`box` also covering the ball of `ball` (rows [time, x, y] by time) nearest to the serve at `served`, if seen."""
    near = np.abs(ball[:, 0] - served)
    if box is None or not len(ball) or near.min() > BALL_AT_SERVE_S:
        return box
    _, x, y = ball[near.argmin()]
    return (max(0, min(box[0], x - SERVER_MARGIN)), max(0, min(box[1], y - SERVER_MARGIN)), min(1, max(box[2], x + SERVER_MARGIN)), min(1, max(box[3], y + SERVER_MARGIN)))


def views(boxes: np.ndarray, rallies: list[dict], touches: list[dict], ball: np.ndarray = np.empty((0, 3))) -> list[list[float]]:
    """The views as [from this time, x, y, width], in fractions of the picture, from the rallies and their `touches`
    (data.js's, without the ball's floor and net contacts): the whole picture between rallies, each serve's SERVE_LEAD_S
    before it (from the rally before's end on a shorter break), showing the server by `ball` (rows [time, x, y] by
    time), the exchange's once the serve is hit, the whole picture after the last rally."""
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
        free = end + HOLD_S if k else 0.0
        server = with_server(players_box(boxes, served - SERVE_S[0], served + SERVE_S[1]), ball, served)
        if server is not None and served - SERVE_LEAD_S > free:
            shown.append([round(float(free), 2), 0, 0, 1])
        show(max(free, served - SERVE_LEAD_S) if served - SERVE_LEAD_S > free else min(free, served), server)
        answered = next((t["t"] for t in own if t["t"] > served and t["type"] != "serve"), None)
        if answered is not None and rally["end"] - answered >= MIN_EXCHANGE_S:
            first = min(served + AFTER_SERVE_S, answered)
            for at in np.arange(first, rally["end"], FOLLOW_S):
                show(at, players_box(boxes, max(answered, at - BEHIND_S), min(rally["end"], at + AHEAD_S)))
        end = rally["end"]
    if shown:
        shown.append([round(end + HOLD_S, 2), 0, 0, 1])
    return shown


# The camera following those views, which the video's copies are cut by (`video_copies`) and the page reads to draw on
# them (video.js): the views widened to keep the ball EDGE inside them, its place averaged over BALL_SMOOTH_S; averaged
# over CAMERA_AHEAD_S either side, then followed by a critically damped spring of SPRING radians a second (it settles
# within about 5 / SPRING seconds). The page did the same on the whole picture until 16 Nov (helpers/zoom.ts).
BALL_SMOOTH_S = 0.5
EDGE = 0.15
CAMERA_AHEAD_S = 1.0
SPRING = 5.0
# The camera's place every CAMERA_STEP_S (the page and the copies take it in between linearly), the spring stepped every SPRING_STEP_S.
CAMERA_STEP_S = 0.1
SPRING_STEP_S = 0.02
# A close call's bounce (`bounces`): zoomed this much, from this long before it to this long after, where the ball is seen
# this near it (the page's until 16 Nov).
CALL_ZOOM, CALL_BEFORE_S, CALL_AFTER_S, CALL_SEEN_S = 2.5, 0.6, 2.2, 0.12
# The hosted video's held bounce (`timeline`): zoomed this much on the ball, back out this long before it plays on.
HELD_ZOOM, HELD_BACK_S = 5.0, 0.6
# Under this zoom the camera shows the whole picture: no sample kept there. Its samples kept in whole numbers of CAMERA_UNIT.
WHOLE_ZOOM = 1.0005
CAMERA_UNIT = 1e-4


def ball_at(ball: np.ndarray, times: np.ndarray) -> np.ndarray:
    """The ball of `ball` (rows [time, x, y] by time) at each of `times`, its samples within BALL_SMOOTH_S averaged: rows
    [x, y], NaN where none."""
    lo = np.searchsorted(ball[:, 0], times - BALL_SMOOTH_S)
    hi = np.searchsorted(ball[:, 0], times + BALL_SMOOTH_S, side="right")
    sums = np.vstack([np.zeros((1, 2)), np.cumsum(ball[:, 1:3], axis=0)])
    n = (hi - lo)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (sums[hi] - sums[lo]) / np.maximum(n, 1), np.nan)


def frames_at(shown: list[list[float]], times: np.ndarray, ball: np.ndarray) -> np.ndarray:
    """The view of `shown` (`views`) at each of `times`, widened only as much as keeps the ball (`ball_at`'s rows) EDGE
    inside it, the players' view still in it (the owner's call, 15 Nov: every player and the ball, parts of the court
    out): rows [centre x, centre y, zoom]."""
    table = np.array(shown, dtype=float).reshape(-1, 4) if shown else np.array([[0.0, 0.0, 0.0, 1.0]])
    x, y, w = table[np.maximum(np.searchsorted(table[:, 0], times, side="right") - 1, 0), 1:].T
    room = EDGE * w
    bx, by = ball.T
    with np.errstate(invalid="ignore"):
        inside = np.isnan(bx) | ((bx >= x + room) & (bx <= x + w - room) & (by >= y + room) & (by <= y + w - room))
    bx, by = np.where(inside, x + w / 2, bx), np.where(inside, y + w / 2, by)
    x1, y1 = np.minimum(x, bx - room), np.minimum(y, by - room)
    x2, y2 = np.maximum(x + w, bx + room), np.maximum(y + w, by + room)
    size = np.where(inside, w, np.minimum(1, np.maximum(x2 - x1, y2 - y1)))
    x1, x2 = np.where(inside, x, x1), np.where(inside, x + w, x2)
    y1, y2 = np.where(inside, y, y1), np.where(inside, y + w, y2)

    def place(start: np.ndarray, end: np.ndarray) -> np.ndarray:
        return np.minimum(1 - size, np.maximum(0, (start + end - size) / 2)) + size / 2

    return np.column_stack([np.where(inside, np.minimum(1 - w, np.maximum(0, x)) + w / 2, place(x1, x2)), np.where(inside, np.minimum(1 - w, np.maximum(0, y)) + w / 2, place(y1, y2)), 1 / size])


def bounces(calls: list[dict], ball: np.ndarray, rallies: list[dict], held: list[tuple[float, float]] = ()) -> list[tuple[float, ...]]:
    """The close calls' zooms (`web.line_calls`) where the ball (rows [time, x, y] by time) is seen within CALL_SEEN_S of
    the bounce: (from, until, x, y, zoom), CALL_ZOOM from CALL_BEFORE_S before it to CALL_AFTER_S after, until the next
    rally starts; on the hosted video, HELD_ZOOM on the ball while its bounce is `held` (`timeline.held`), back out
    HELD_BACK_S before it plays on."""
    out = []
    for start, end in held:
        near = np.abs(ball[:, 0] - start) if len(ball) else np.empty(0)
        if len(near) and near.min() <= CALL_SEEN_S:
            _, x, y = ball[near.argmin()]
            out.append((start, end - HELD_BACK_S, float(x), float(y), HELD_ZOOM))
    for call in calls:
        near = np.abs(ball[:, 0] - call["t"]) if len(ball) else np.empty(0)
        if not len(near) or near.min() > CALL_SEEN_S:
            continue
        _, x, y = ball[near.argmin()]
        following = rallies[call["rally"] + 1]["start"] if call["rally"] + 1 < len(rallies) else np.inf
        out.append((call["t"] - CALL_BEFORE_S, min(call["t"] + CALL_AFTER_S, following), float(x), float(y), CALL_ZOOM))
    return sorted(out)


def camera(shown: list[list[float]], ball: np.ndarray, duration: float, calls: list[tuple[float, ...]] = ()) -> np.ndarray:
    """The camera over the video's `duration` (seconds), every CAMERA_STEP_S from 0: rows [centre x, centre y, zoom], in
    fractions of the picture, from the views (`views`) and the ball (rows [time, x, y] by time); on each close call's
    bounce (`bounces`, its zoom) while it lasts, by springs of its own: its share of the view, and its zoom."""
    if not shown and not calls:
        return np.tile([0.5, 0.5, 1.0], (int(duration / CAMERA_STEP_S) + 1, 1))
    reach = round(CAMERA_AHEAD_S / CAMERA_STEP_S)
    grid = np.arange(-reach, int(duration / CAMERA_STEP_S) + reach + 2) * CAMERA_STEP_S
    found = frames_at(shown, grid, ball_at(ball.reshape(-1, 3), grid))
    sums = np.vstack([np.zeros((1, 3)), np.cumsum(found, axis=0)])
    target = (sums[2 * reach + 1 :] - sums[: -2 * reach - 1]) / (2 * reach + 1)
    steps = round(CAMERA_STEP_S / SPRING_STEP_S)
    out = np.empty((len(target) - 1, 3))
    now, speed = [0.5, 0.5, 1.0], [0.0, 0.0, 0.0]
    # The close call's share of the view and its zoom, their speeds, and its bounce: the last one begun.
    calls = sorted(calls)
    share_now, share_speed, at, next_call = 0.0, 0.0, (0.5, 0.5), 0
    zoom_now, zoom_speed, zoom_goal = CALL_ZOOM, 0.0, CALL_ZOOM
    for k in range(len(out)):
        width = 1 / now[2] + (1 / zoom_now - 1 / now[2]) * share_now
        out[k] = [now[0] + (at[0] - now[0]) * share_now, now[1] + (at[1] - now[1]) * share_now, 1 / width]
        a, b = target[k], target[k + 1]
        for s in range(steps):
            share = (s + 1) / steps
            for i in range(3):
                goal = a[i] + (b[i] - a[i]) * share
                speed[i] += (SPRING * SPRING * (goal - now[i]) - 2 * SPRING * speed[i]) * SPRING_STEP_S
                now[i] += speed[i] * SPRING_STEP_S
            time = (k + share) * CAMERA_STEP_S
            while next_call < len(calls) and calls[next_call][0] <= time:
                at, zoom_goal = calls[next_call][2:4], calls[next_call][4]
                if share_now < 0.01:
                    zoom_now, zoom_speed = zoom_goal, 0.0
                next_call += 1
            zoom_speed += (SPRING * SPRING * (zoom_goal - zoom_now) - 2 * SPRING * zoom_speed) * SPRING_STEP_S
            zoom_now += zoom_speed * SPRING_STEP_S
            on = next_call and calls[next_call - 1][0] <= time <= calls[next_call - 1][1]
            share_speed += (SPRING * SPRING * ((1.0 if on else 0.0) - share_now) - 2 * SPRING * share_speed) * SPRING_STEP_S
            share_now += share_speed * SPRING_STEP_S
    zoom = np.maximum(1, out[:, 2])
    half = 0.5 / zoom
    return np.column_stack([np.clip(out[:, 0], half, 1 - half), np.clip(out[:, 1], half, 1 - half), zoom])


def camera_spans(track: np.ndarray) -> list[list[float]]:
    """`camera`'s track without its whole-picture moments, as runs [from this time, x, y, zoom, then each sample's change
    from the one before...] every CAMERA_STEP_S, in CAMERA_UNIT whole numbers, a sample either side: the whole picture
    outside them. About a third of the size of the samples written out."""
    zoomed = track[:, 2] >= WHOLE_ZOOM
    zoomed = zoomed | np.r_[zoomed[1:], False] | np.r_[False, zoomed[:-1]]
    edges = np.flatnonzero(np.diff(np.r_[0, zoomed.astype(int), 0]))
    units = np.rint(track / CAMERA_UNIT).astype(int)
    return [[round(start * CAMERA_STEP_S, 2), *units[start].tolist(), *np.diff(units[start:end], axis=0).ravel().tolist()] for start, end in zip(edges[::2], edges[1::2])]


def camera_at(spans: list[list[float]], times: np.ndarray) -> np.ndarray:
    """The camera of `camera_spans` at each of `times`, linear between its samples: rows [centre x, centre y, zoom]."""
    out = np.tile([0.5, 0.5, 1.0], (len(times), 1))
    for span in spans:
        run = np.cumsum(np.array(span[1:], dtype=float).reshape(-1, 3), axis=0) * CAMERA_UNIT
        at = (times - span[0]) / CAMERA_STEP_S
        # A sample's own time lands a hair either side of it.
        on = (at >= -1e-6) & (at <= len(run) - 1 + 1e-6)
        k = np.clip(at[on], 0, None).astype(int).clip(max=max(0, len(run) - 2))
        out[on] = run[k] + (run[np.minimum(k + 1, len(run) - 1)] - run[k]) * np.clip(at[on] - k, 0, 1)[:, None]
    return out
