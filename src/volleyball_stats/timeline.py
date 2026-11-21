"""The hosted video's own time: the rallies at their speed, the breaks within a set twice as fast, the long pauses cut
(timeouts, between sets, before the first rally and after the last), and each close call slowed down to its bounce,
held there while the camera closes in on the ball (the owner's calls, 16 Nov).

A map of pieces [from, to, at, until]: the source's seconds `from` to `to` play from the copy's `at` to `until`, at
their ratio's speed (a held frame: `from` == `to`). Between two pieces the source jumps ahead: a cut, faded through
black (CUT_FADE_S either side). The copies are made along it (`video_copies`), and the hosted page's data is retimed by
it (`retimed`), so the page plays the copy's time as it played the source's. The review keeps the source's time.
"""

import numpy as np

# Kept either side of a cut: the end of a rally, the start of the next.
KEEP_S = 2.0
# A break within a set longer than this is cut, as a timeout is; one shorter than the two ends kept plays whole.
LONG_BREAK_S = 45.0
# A break within a set plays this many times as fast, but for this long after the rally and before the next.
FAST = 2.0
CALM_S = 1.0
# The fade through black at a cut, each side.
CUT_FADE_S = 0.3
# A close call: this long before its bounce at half speed, then its bounce held this long (the copy's seconds).
SLOW_S, SLOW = 0.6, 0.5
HOLD_S = 2.0
# The bounce: the ball's lowest place in the picture this near the landing touch.
BOUNCE_S = 0.3
# A copy's cut this near the review's still serves: the copies are worth making again past it (the owner's call, 21 Nov).
MOVED_S = 2.0


def bounce_at(t: float, ball: np.ndarray) -> float | None:
    """The time of the ball's bounce near the landing at `t`: its lowest place in the picture (rows [time, x, y] by time)
    within BOUNCE_S; None where it is not seen then."""
    near = ball[np.abs(ball[:, 0] - t) <= BOUNCE_S] if len(ball) else ball
    return float(near[near[:, 2].argmax(), 0]) if len(near) else None


def plan(data: dict, ball: np.ndarray) -> list[list[float]]:
    """The map of the hosted video of `data` (its rallies, sets, timeouts, `lineCalls`, `duration`, on the source's
    time), the ball (rows [time, x, y] by time) placing the close calls' bounces."""
    rallies = data["rallies"]
    if not rallies:
        return [[0.0, data["duration"], 0.0, data["duration"]]]
    timeouts = data.get("timeouts") or []
    held = sorted(b for c in data.get("lineCalls") or [] if (b := bounce_at(c["t"], ball)) is not None)
    # The source's spans and their speed (0: a held frame, its length the copy's), cuts between those not touching.
    spans: list[tuple[float, float, float]] = []

    def play(start: float, end: float, speed: float = 1.0) -> None:
        if end > start:
            spans.append((start, end, speed))

    def rally(start: float, end: float) -> None:
        at = start
        for b in (b for b in held if start <= b <= end):
            play(at, max(at, b - SLOW_S))
            play(max(at, b - SLOW_S), b, SLOW)
            spans.append((b, b, 0.0))
            at = b
        play(at, end)

    play(max(0.0, rallies[0]["start"] - KEEP_S), rallies[0]["start"])
    for k, r in enumerate(rallies):
        rally(r["start"], r["end"])
        if k + 1 == len(rallies):
            play(r["end"], min(data["duration"], r["end"] + KEEP_S))
            break
        following = rallies[k + 1]
        gap = following["start"] - r["end"]
        paused = following["set"] != r["set"] or gap > LONG_BREAK_S or any(o["start"] < following["start"] and o["end"] > r["end"] for o in timeouts)
        if paused and gap > 2 * KEEP_S:
            play(r["end"], r["end"] + KEEP_S)
            play(following["start"] - KEEP_S, following["start"])
        elif gap > 2 * CALM_S:
            play(r["end"], r["end"] + CALM_S)
            play(r["end"] + CALM_S, following["start"] - CALM_S, FAST)
            play(following["start"] - CALM_S, following["start"])
        else:
            play(r["end"], following["start"])
    pieces: list[list[float]] = []
    out = 0.0
    for start, end, speed in spans:
        length = HOLD_S if speed == 0 else (end - start) / speed
        # Pieces of the same speed in a row make one.
        last = pieces[-1] if pieces else None
        if last and speed and last[1] == start and last[1] > last[0] and abs((last[3] - last[2]) / (last[1] - last[0]) - 1 / speed) < 1e-9:
            last[1], last[3] = round(end, 3), round(out + length, 3)
        else:
            pieces.append([round(start, 3), round(end, 3), round(out, 3), round(out + length, 3)])
        out += length
    return pieces


def moved(made: list[list[float]], now: list[list[float]]) -> bool:
    """Whether the map `now` differs from `made` enough to make the copies again: a piece's end on the source over
    MOVED_S from every one of the other map (a rally moved, added or gone), or a close call's held frame added, gone or
    moved past BOUNCE_S. The camera follows them."""

    def ends(pieces: list[list[float]]) -> np.ndarray:
        return np.unique(np.array(pieces, dtype=float).reshape(-1, 4)[:, :2])

    def far(a: np.ndarray, b: np.ndarray) -> bool:
        return bool((np.abs(a[:, None] - b[None, :]).min(axis=1) > MOVED_S).any())

    a, b = ends(made), ends(now)
    if not len(a) or not len(b):
        return len(a) != len(b)
    holds = [np.array(sorted(p[0] for p in pieces if p[0] == p[1])) for pieces in (made, now)]
    if len(holds[0]) != len(holds[1]) or (len(holds[0]) and np.abs(holds[0] - holds[1]).max() > BOUNCE_S):
        return True
    return far(a, b) or far(b, a)


def cuts(pieces: list[list[float]]) -> list[float]:
    """The copy's times where the source jumps ahead."""
    return [b[2] for a, b in zip(pieces, pieces[1:]) if b[0] > a[1] + 1e-6]


def to_copy(pieces: list[list[float]], times: np.ndarray) -> np.ndarray:
    """The copy's times of the source's `times`: one cut out at its cut, one at a held frame at the hold's start."""
    table = np.array(pieces, dtype=float).reshape(-1, 4)
    times = np.asarray(times, dtype=float)
    # The first piece ending at or after each time: it holds it, or the time was cut out before it.
    k = np.searchsorted(table[:, 1], times, side="left")
    past = k >= len(table)
    k = np.minimum(k, len(table) - 1)
    start, end, at, until = table[k].T
    share = np.clip((times - start) / np.maximum(end - start, 1e-9), 0, 1)
    return np.where(past, table[-1, 3], np.where(times < start, at, at + (until - at) * share))


def to_source(pieces: list[list[float]], times: np.ndarray) -> np.ndarray:
    """The source's times the copy shows at `times`."""
    table = np.array(pieces, dtype=float).reshape(-1, 4)
    k = np.clip(np.searchsorted(table[:, 2], times, side="right") - 1, 0, len(table) - 1)
    start, end, at, until = table[k].T
    share = np.clip((np.asarray(times, dtype=float) - at) / np.maximum(until - at, 1e-9), 0, 1)
    return start + (end - start) * share


def fade(pieces: list[list[float]], times: np.ndarray) -> np.ndarray:
    """How much of the picture and the sound shows at the copy's `times`: down to nothing at each cut, over CUT_FADE_S
    either side."""
    found = np.ones(len(times))
    for at in cuts(pieces):
        found = np.minimum(found, np.clip(np.abs(np.asarray(times) - at) / CUT_FADE_S, 0, 1))
    return found


def retimed(data: dict, pieces: list[list[float]]) -> dict:
    """`data` (the page's) on the copy's time: its rallies, touches, timeouts, close calls, views and duration; the
    rallies' times (`real`) and the match's length (`length`) kept for the stats."""

    def at(t: float | None) -> float | None:
        return None if t is None else round(float(to_copy(pieces, np.array([t]))[0]), 3)

    # The match's own length and each rally's times stay for the stats: how long it lasted, not how long it plays.
    out = {**data, "duration": round(pieces[-1][3], 2), "length": data.get("length", data["duration"])}
    out["rallies"] = [{**r, **{k: at(r[k]) for k in ("start", "window", "end") if k in r}, "real": r.get("real", [r["start"], r["end"]])} for r in data["rallies"]]
    out["contacts"] = [{**c, "t": at(c["t"])} for c in data["contacts"]]
    out["timeouts"] = [{**o, "start": at(o["start"]), "end": at(o["end"])} for o in data.get("timeouts") or []]
    if data.get("lineCalls"):
        # A call whose bounce is held shows from the hold: its card lands as the picture stops.
        holds = [(p[0], p[2]) for p in pieces if p[0] == p[1]]

        def call_at(t: float) -> float | None:
            near = [h for h in holds if abs(h[0] - t) <= BOUNCE_S]
            return min(near, key=lambda h: abs(h[0] - t))[1] if near else at(t)

        out["lineCalls"] = [{**c, "t": call_at(c["t"])} for c in data["lineCalls"]]
    if data.get("views"):
        out["views"] = [[at(v[0]), *v[1:]] for v in data["views"]]
    if data.get("end") is not None:
        out["end"] = at(data["end"])
    return out


def retimed_ball(samples: np.ndarray, pieces: list[list[float]]) -> np.ndarray:
    """The ball's samples (rows [time, x, y] by time) on the copy's time, those cut out left out."""
    if not len(samples):
        return samples
    table = np.array(pieces, dtype=float)
    kept = np.zeros(len(samples), bool)
    for start, end, _, _ in table:
        kept |= (samples[:, 0] >= start) & (samples[:, 0] <= end)
    kept_samples = samples[kept]
    return np.column_stack([to_copy(pieces, kept_samples[:, 0]), kept_samples[:, 1:]])


def held(pieces: list[list[float]]) -> list[tuple[float, float]]:
    """The copy's spans where a frame is held: (from, until)."""
    return [(p[2], p[3]) for p in pieces if p[0] == p[1]]


def retimed_positions(players: dict, fps: float, pieces: list[list[float]]) -> dict:
    """The players' positions (`web.player_samples`: one every `step` frames of the match at `fps`) on the copy's time:
    the same step, each sample the match's at that moment of the copy."""
    every = players["step"] / fps
    samples = players["samples"]
    count = int(pieces[-1][3] / every) + 1
    at = np.clip(np.rint(to_source(pieces, np.arange(count) * every) / every).astype(int), 0, len(samples) - 1)
    return {**players, "samples": [samples[k] for k in at]}


def cut(data: dict, ball: np.ndarray) -> dict:
    """How the hosted video's copies are made from the match of `data` (the page's, its `lineCalls` in) and the ball
    (rows [time, x, y] by time): its `map` and its `camera` (`framing.camera_spans`) on the copy's time."""
    from volleyball_stats import framing

    pieces = plan(data, ball)
    on, seen = retimed(data, pieces), retimed_ball(ball, pieces)
    calls = framing.bounces(on.get("lineCalls") or [], seen, on["rallies"], held(pieces))
    return {"map": pieces, "camera": framing.camera_spans(framing.camera(on.get("views") or [], seen, on["duration"], calls))}
