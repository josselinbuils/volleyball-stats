"""Each player's film: a vertical film of under 45 s cut from the real video like a broadcast, made ahead of time on demand.

    uv run python -m volleyball_stats.film outputs/MATCH --video VIDEO --court COURT_JSON [--names NAME,NAME]

The moments are a player's fastest serve and best points, each played then replayed slowly; the match has its own 16/9 film of about a
minute (HIGHLIGHTS). `build` makes only the films whose `plan` changed (FILMS/manifest.json); the ball's search is kept whatever
changes. Real footage: a film stays behind the hosted page's password (web.write_site puts them only beside a page with the video).
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import ball as tracker
from volleyball_stats import files
from volleyball_stats.court import Calibration, distort, undistort

FILMS = "films"
MANIFEST = "manifest.json"
BALL_CACHE, TIMES_CACHE = "film_ball.json", "frame_times.npy"
# Bumped when films must be made again whatever their data.
VERSION = 4
SEG_S, SEG_M = Path("models/yolo11s-seg.pt"), Path("models/yolo11m-seg.pt")
LOCALE = Path(__file__).resolve().parents[2] / "web/src/locales/fr.json"
# Films made at once.
WORKERS = 3

# The film being made's size: upright, or 16/9 (`use_format`).
FORMATS = {"tall": (720, 1280), "wide": (1920, 1080)}
WIDTH, HEIGHT = FORMATS["tall"]
ASPECT = WIDTH / HEIGHT
SOURCE_W, SOURCE_H = 3840, 2160
FPS = 50.0
RED, GOLD, WHITE, INK, GREY = (19, 6, 227), (40, 200, 255), (255, 255, 255), (22, 16, 14), (200, 200, 200)
FONTS = Path("/System/Library/Fonts/Supplemental")

# The film's shape.
MOMENTS, LEAST_MOMENTS = 6, 2
# At most this many of a kind of touch while there is anything else to show: the same action again looks like a repeat.
SAME_KIND = 2
INTRO_S, OUTRO_S = 2.6, 4.5
LEAD_S, AFTER_S, AFTER_POINT_S, AFTER_FLIGHT_S = 3.5, 1.0, 1.6, 0.5
REPLAY_BEFORE_S, REPLAY_AFTER_S, REPLAY_SPEED = 1.0, 0.8, 0.5
# The replay slows into a freeze on the touch.
REPLAY_PRE, FREEZE = 1.75, 0.6
# The match's film, under this name among the players'.
HIGHLIGHTS = "*"
# The touches the owner puts in the films from the review's Match tab, by video frame: the touch nearest each, within
# PICK_SLACK_S, a rerun moving touches a little.
PICKS, PICK_SLACK_S = "highlight_picks.json", 0.3
HIGHLIGHTS_S, HIGHLIGHTS_LEAST, HIGHLIGHTS_REPLAYS = 50.0, 8, 2
# A clip runs from the set before its touch, or the serve's toss; in the match's film to the point's banner gone, a point another
# touch wins up to PUNCH_END_S after the touch.
PUNCH_LEAD_S, TOSS_S, PUNCH_END_S = 2.0, 1.2, 2.5
# The longest rally's best exchanges, BEATS at most, cut in before its end: from just before an attack to just after the touch
# that kept the ball in play.
BEATS, BEAT_BEFORE_S, BEAT_AFTER_S = 3, 0.7, 0.5
# A film opens on its most striking point, this long before and after it, then its title.
HOOK_BEFORE_S, HOOK_AFTER_S = 1.0, 0.8
# The camera on a live shot follows the ball, on the player only this long around their touch; it widens for a ball this many seconds
# of flight across, and keeps the ball within this share of the picture's half.
ON_PLAYER_BEFORE_S, ON_PLAYER_AFTER_S, FLIGHT_IN_VIEW_S, BALL_IN_VIEW = 1.0, 0.5, 0.8, 0.8
# How a point is a moment (the page's `highlights`).
LONG_RALLY, LATE = 7, 20
KINDS = ("setWon", "longRally", "lateTie", "ace", "block")
TOUCHES = {"serve", "pass", "set", "attack", "relance", "block", "dig"}

# The ball. A ball never stays put this long, moves no faster, and a sudden change of its velocity is a touch, a block or the floor.
STILL_FRAMES, STILL_PX, TELEPORT_PX = 20, 14.0, 110.0
CHAIN_FRAMES, KINK_PX, INLIER_PX = 60, 8.0, 16.0
# A flight this much smaller than a ball on our court can look, at its worst, is a ball on another court: its size, read against
# frames SIZE_GAP away so that all of it shows. Single frames read too small at times, so a flight is judged by its upper sizes.
SMALL_FLIGHT, SIZE_GAP, SIZE_LEAST_POINTS = 0.7, 10, 5
# A ball's diameter, and the volume it plays in around the court, in metres.
BALL_M, VOLUME_X, VOLUME_Y, VOLUME_H = 0.21, 13.0, 7.0, 10.0
# Flights this close join up: a line drawn over a longer hole is a guess, and no effect is better than one on nothing. After the
# last touch this long unseen, the ball is lost.
JOIN_FRAMES, LOST_FRAMES = 10, 8
# Where the search looks around the first pass: sharper first, in up to 4 times the first pass's detail.
CROPS = ((1536, 864), (960, 540))
TAIL_CROPS = ((1536, 864), (2560, 1440))
WINDOW_PAD_S = 0.4
TAIL_FRAMES = 90
BATCH = 16
# A server stands behind the end line, 9 m from the net: a track this close to it at the serve follows someone else.
SERVER_FROM_NET_M = 8.0


def serving_body(named: tuple[float, float] | None, team: dict[int, tuple[float, float]]) -> int | None:
    """The teammate (`team`: places by person, at the serve) who is the server when the named player's track is inside the court,
    None to keep them. Only the serve: elsewhere the ball's 3D place, not the track, is often what is off."""
    if named is not None and abs(named[0]) >= SERVER_FROM_NET_M:
        return None
    behind = sorted((-abs(p[0]), person) for person, p in team.items() if abs(p[0]) >= SERVER_FROM_NET_M)
    return behind[0][1] if behind else None


def use_format(name: str) -> None:
    """Makes the film being made upright or 16/9: a process makes one film at a time."""
    global WIDTH, HEIGHT, ASPECT
    WIDTH, HEIGHT = FORMATS[name]
    ASPECT = WIDTH / HEIGHT


def locale() -> dict:
    return json.loads(LOCALE.read_text())


def read_page(site: Path) -> dict | None:
    """The data.js of the page at `site`, with each contact's index and team group, None without one."""
    path = site / "data.js"
    if not path.exists():
        return None
    text = path.read_text()
    page = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
    for k, c in enumerate(page["contacts"]):
        c["i"] = k
        c["g"] = (page.get("teams") and c.get("team")) or (1 if c.get("side") == "left" else 2)
    for k, r in enumerate(page["rallies"]):
        r["i"] = k
        r["contacts"] = []
    for c in page["contacts"]:
        page["rallies"][c["rally"]]["contacts"].append(c)
    return page


def read_picks(match: Path) -> set[int]:
    path = match / PICKS
    return set(json.loads(path.read_text())) if path.exists() else set()


def write_picks(match: Path, picks: set[int]) -> None:
    files.write_text(match / PICKS, json.dumps(sorted(picks)) + "\n")


def picked(contacts: list[dict], picks: set[int], fps: float) -> list[dict]:
    touches = [c for c in contacts if is_touch(c)]
    out = []
    for frame in sorted(picks):
        c = min(touches, key=lambda c: abs(c["f"] - frame), default=None)
        if c is not None and abs(c["f"] - frame) <= PICK_SLACK_S * fps and c not in out:
            out.append(c)
    return out


def is_touch(c: dict) -> bool:
    return c["type"] in TOUCHES


def scoring_touch(rally: dict) -> dict | None:
    touches = [c for c in rally["contacts"] if is_touch(c)]
    if touches and touches[-1].get("result") == "point":
        return touches[-1]
    if len(touches) >= 2 and touches[-1].get("result") == "error" and touches[-2].get("result") == "point" and touches[-2]["g"] != touches[-1]["g"]:
        return touches[-2]
    return None


def clip_start(rally: dict, t: float) -> float:
    served = min(rally["start"], next(q["t"] for q in rally["contacts"] if is_touch(q))) - TOSS_S
    return max(served, t - PUNCH_LEAD_S)


def striking(c: dict) -> float:
    """How striking a point looks: a block, an attack's height, a serve's speed."""
    return 3.0 if c["type"] == "block" else (c.get("reach") or 0) if c["type"] == "attack" else (c.get("speed") or 0) / 30


def scores_before(rallies: list[dict]) -> dict[int, list[int]]:
    out, number, before = {}, None, [0, 0]
    for r in rallies:
        if r["set"] != number:
            number, before = r["set"], [0, 0]
        out[r["i"]] = before
        before = r.get("score") or before
    return out


def highlights(rallies: list[dict], key: set[int]) -> list[dict]:
    """A player's best points, at most MOMENTS: winning a set, ending a long rally, a late tie, then aces and blocks."""
    before = scores_before(rallies)
    found = []
    for k, r in enumerate(rallies):
        c = scoring_touch(r)
        if not c or r.get("winner") != c["g"] or not r.get("score") or c.get("person") not in key:
            continue
        was = before[r["i"]]
        touches = sum(is_touch(q) for q in r["contacts"])
        score = r["score"] if c["g"] == 1 else r["score"][::-1]
        late = max(r["score"]) >= LATE and abs(r["score"][0] - r["score"][1]) <= 1 and abs(was[0] - was[1]) <= 1
        following = rallies[k + 1]["set"] if k + 1 < len(rallies) else None
        kind = "setWon" if following != r["set"] and score[0] > score[1] else "longRally" if touches >= LONG_RALLY else "lateTie" if late else "ace" if c["type"] == "serve" else "block" if c["type"] == "block" else None
        if kind:
            found.append((kind, c))
    return [c for _, c in sorted(found, key=lambda x: (KINDS.index(x[0]), x[1]["t"]))[:MOMENTS]]


def moments_of(rallies: list[dict], key: set[int], mine: list[dict], picks: list[dict] = ()) -> list[dict]:
    """A player's moments in the order the film shows them: their fastest serve, then their points building up to the best, the
    touches picked in the review always, as the best."""
    played = [c for c in mine if is_touch(c) and c.get("result") != "error"]
    forced = [c for c in picks if c in played]
    timed = [c for c in played if c.get("speed") is not None]
    fastest = None
    for c in timed:
        if fastest is None or c["speed"] > fastest["speed"]:
            fastest = c
    touches_in = lambda c: sum(is_touch(q) for q in rallies[c["rally"]]["contacts"])  # noqa: E731
    candidates = [
        *forced,
        *highlights(rallies, key),
        *sorted((c for c in played if c.get("result") == "point"), key=lambda c: -c["t"]),
        *sorted((c for c in played if c.get("result") != "point"), key=lambda c: -touches_in(c)),
    ]
    seen = {fastest["rally"]} if fastest else set()
    kinds = [fastest["type"]] if fastest else []
    best = []
    for c in forced:
        if c["rally"] not in seen:
            seen.add(c["rally"])
            kinds.append(c["type"])
            best.append(c)
    for limit in (SAME_KIND, MOMENTS):
        for c in candidates:
            if len(seen) < MOMENTS and c["rally"] not in seen and kinds.count(c["type"]) < limit:
                seen.add(c["rally"])
                kinds.append(c["type"])
                best.append(c)
    # The candidates come best first, whichever round took them.
    best.sort(key=lambda c: next(k for k, q in enumerate(candidates) if q is c))
    return varied([*([fastest] if fastest else []), *reversed(best)])


def varied(moments: list[dict]) -> list[dict]:
    """`moments` with no kind of touch twice in a row where another order avoids it, the first and the last, the best, in place."""
    out = list(moments)
    for k in range(1, len(out) - 1):
        if out[k]["type"] == out[k - 1]["type"]:
            other = next((j for j in range(k + 1, len(out) - 1) if out[j]["type"] != out[k - 1]["type"]), None)
            if other is not None:
                out[k], out[other] = out[other], out[k]
    # The one before the last, too, from what comes earlier.
    if len(out) >= 4 and out[-2]["type"] == out[-1]["type"]:
        for j in range(1, len(out) - 2):
            neighbours = [out[j - 1]["type"]] + ([out[j + 1]["type"]] if j + 1 < len(out) - 2 else [])
            if out[j]["type"] != out[-1]["type"] and out[-2]["type"] not in neighbours and out[j]["type"] != out[-3]["type"]:
                out[j], out[-2] = out[-2], out[j]
                break
    return out


def shots_of(moments: list[dict], rallies: list[dict]) -> tuple[list[dict], float]:
    """The film's shots: its most striking point but the last as a hook, a title, each moment played then replayed, an end."""
    shots, at = [], 0.0

    def add(kind: str, length: float, start: float, speed: float, c: dict) -> None:
        nonlocal at
        shots.append({"kind": kind, "start": at, "length": length, "from": start, "speed": speed, "contact": c["i"], "rally": c["rally"]})
        at += length

    scored = [c for c in moments[:-1] if c.get("result") == "point"]
    if scored:
        hook = max(scored, key=striking)
        add("live", HOOK_BEFORE_S + HOOK_AFTER_S, hook["t"] - HOOK_BEFORE_S, 1, hook)
        shots[-1]["hook"] = True
    add("intro", INTRO_S, moments[0]["t"] - LEAD_S, 1, moments[0])
    for c in moments:
        rally = rallies[c["rally"]]
        touches = [q for q in rally["contacts"] if is_touch(q)]
        following = next((q for q, was in zip(touches[1:], touches) if was is c), None)
        start = clip_start(rally, c["t"])
        end = following["t"] + AFTER_FLIGHT_S if c["type"] == "serve" and following else c["t"] + (AFTER_POINT_S if c.get("result") == "point" else AFTER_S)
        add("live", end - start, start, 1, c)
        # Replayed only where it adds something: the first when its speed was measured, and the last, the best.
        if c is moments[-1] or (c is moments[0] and c.get("speed") is not None):
            add("replay", (REPLAY_BEFORE_S + REPLAY_AFTER_S) / REPLAY_SPEED, c["t"] - REPLAY_BEFORE_S, REPLAY_SPEED, c)
    add("outro", OUTRO_S, moments[-1]["t"], 1, moments[-1])
    return shots, at


def voice_index(site: Path) -> dict | None:
    path = site / "voice" / "index.js"
    if not path.exists():
        return None
    text = path.read_text()
    return json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))


def lines_of(shots: list[dict], voice: dict | None, name: str) -> list[dict]:
    """The commentary's lines the shots play, each after the last has ended; the replay's own about the player."""
    if not voice:
        return []
    out, free = [], 0.0
    for shot in shots:
        if shot["kind"] == "live" and not shot.get("hook"):
            for t, clip, length in voice["lines"]:
                at = shot["start"] + t - shot["from"]
                if max(shot["start"], free) <= at < shot["start"] + shot["length"]:
                    out.append({"at": at, "file": clip})
                    free = at + length
        elif shot["kind"] == "replay" and voice["replay"].get(name) and shot["start"] >= free:
            out.append({"at": shot["start"], "file": voice["replay"][name]})
        elif shot["kind"] == "replay" and voice["replay"].get(shot.get("who", {}).get("name")) and shot["start"] >= free:
            out.append({"at": shot["start"], "file": voice["replay"][shot["who"]["name"]]})
            free = shot["start"] + shot["length"]
            free = shot["start"] + shot["length"]
    return out


def who_of(person: int, people: dict) -> dict:
    """Who a touch shows, across their tracking numbers."""
    q = people[str(person)]
    persons = sorted(int(p) for p, o in people.items() if o.get("name") == q["name"] and o.get("team") == q["team"] and o.get("number") is not None)
    return {"name": q["name"], "team": q["team"], "persons": persons or [person], "jersey": next((people[str(p)]["jersey"] for p in persons if people[str(p)].get("jersey") is not None), None)}


def rally_touch(rally: dict, people: dict) -> dict | None:
    """The named touch a rally is shown for: the one that scored, else its winner's last, else its last; never a fault, a film names no one for one."""
    named = lambda c: people.get(str(c.get("person")), {}).get("name")  # noqa: E731
    scored = scoring_touch(rally)
    if scored and named(scored):
        return scored
    touches = [c for c in rally["contacts"] if is_touch(c) and named(c) and c.get("result") != "error"]
    return next((c for c in reversed(touches) if c["g"] == rally.get("winner")), touches[-1] if touches else None)


def highlight_moments(page: dict, picks: set[int] = frozenset()) -> list[tuple[dict, dict]]:
    """The match's best rallies, in match order, as (touch, its clip's start and end, replayed or not), the longest's best exchanges
    before its end, its most striking point first as a hook: the longest, the match point and the touches `picks` (by frame)
    always, then set points, late ties, aces, blocks and kills, both teams, every set and many players shown."""
    rallies, people = page["rallies"], page.get("people") or {}
    before = scores_before(rallies)
    played = [r for r in rallies if r.get("winner") and rally_touch(r, people)]
    if len(played) < HIGHLIGHTS_LEAST:
        return []
    count = lambda r: sum(is_touch(c) for c in r["contacts"])  # noqa: E731
    longest = max(played, key=lambda r: (count(r), r["end"] - r["start"]))
    last = played[-1]

    def worth(r: dict) -> float:
        c, score, was, n = rally_touch(r, people), r.get("score") or [0, 0], before[r["i"]], count(r)
        following = rallies[r["i"] + 1]["set"] if r["i"] + 1 < len(rallies) else None
        scored = c is scoring_touch(r)
        late = max(score) >= LATE and abs(score[0] - score[1]) <= 1 and abs(was[0] - was[1]) <= 1
        return (3.0 if following != r["set"] else 0) + (3.0 if late else 0) + (0.2 * min(n, 15) if n >= LONG_RALLY else 0) + (2 + (c.get("speed") or 0) / 40 if scored and c["type"] == "serve" else 0) + (3.0 if scored and c["type"] == "block" else 0) + (1.5 if scored and c["type"] == "attack" else 0) + (1.5 if (c.get("reach") or 0) >= 3.2 else 0)

    def clip(r: dict) -> tuple[float, float]:
        c = rally_touch(r, people)
        point = c["t"] if c is scoring_touch(r) else min(r["end"], c["t"] + PUNCH_END_S)
        return clip_start(r, c["t"]), point + AFTER_POINT_S

    def beats(r: dict) -> list[tuple[dict, float, float]]:
        """Its best exchanges before its clip, one per stretch of the rally: an attack and the named touch that kept the ball in
        play, as (that touch, start, end)."""
        wanted = BEATS if r is longest else 0
        touches = [c for c in r["contacts"] if is_touch(c)]
        found = [
            (b, a["t"] - BEAT_BEFORE_S, b["t"] + BEAT_AFTER_S, (a.get("reach") or 0) + (b["type"] == "dig"))
            for a, b in zip(touches, touches[1:])
            if a["type"] == "attack" and a.get("result") == "play" and b["g"] != a["g"] and b.get("result") == "play" and people.get(str(b.get("person")), {}).get("name")
        ]
        finish, kept = clip(r)[0], []
        for k in range(wanted):
            lo, hi = r["start"] + (finish - r["start"]) * k / wanted, r["start"] + (finish - r["start"]) * (k + 1) / wanted
            inside = [x for x in found if lo <= x[1] < hi and x[2] <= finish and (not kept or x[1] >= kept[-1][2])]
            if inside:
                # Another defender each time, where there is one.
                seen = {people[str(b["person"])]["name"] for b, _, _ in kept}
                kept.append(max(inside, key=lambda x: (people[str(x[0]["person"])]["name"] not in seen, x[3]))[:3])
        return kept

    def length(r: dict) -> float:
        return clip(r)[1] - clip(r)[0] + sum(end - start for _, start, end in beats(r))

    replay_s = (REPLAY_BEFORE_S + REPLAY_AFTER_S) / REPLAY_SPEED
    room = HIGHLIGHTS_S - HOOK_BEFORE_S - HOOK_AFTER_S - INTRO_S - OUTRO_S - HIGHLIGHTS_REPLAYS * replay_s
    chosen = [longest] if longest is last else [longest, last]
    # A touch picked is its rally's clip when the rally is shown for it, else a clip of its own.
    wanted = [c for c in picked(page["contacts"], picks, page.get("fps", FPS)) if people.get(str(c.get("person")), {}).get("name") and c.get("result") != "error"]
    chosen += [r for r in played if rally_touch(r, people) in wanted and r not in chosen]
    extras = [(c, clip_start(rallies[c["rally"]], c["t"]), c["t"] + AFTER_S) for c in wanted if not any(c is rally_touch(r, people) for r in chosen)]
    room -= sum(length(r) for r in chosen) + sum(end - start for _, start, end in extras)
    while True:
        def adjusted(r: dict) -> float:
            c = rally_touch(r, people)
            shown = [rally_touch(q, people) for q in chosen]
            name = people[str(c["person"])]["name"]
            teams = [sum(q["g"] == g for q in shown) for g in (1, 2)]
            return worth(r) - 1.5 * sum(people[str(q["person"])]["name"] == name for q in shown) - 1.0 * sum(q["type"] == c["type"] for q in shown) + (1.5 if teams[c["g"] - 1] < teams[2 - c["g"]] else 0) + (1.5 if r["set"] not in {q["set"] for q in chosen} else 0)

        # A point won by a fault shows no action.
        left = [r for r in played if r not in chosen and length(r) <= room and rally_touch(r, people) is scoring_touch(r)]
        if not left:
            break
        best = max(left, key=adjusted)
        chosen.append(best)
        room -= length(best)
    replayed = {last["i"], *sorted((r["i"] for r in chosen if r is not last), key=lambda k: -worth(rallies[k]))[: HIGHLIGHTS_REPLAYS - 1]}
    out = []
    for r in sorted(chosen, key=lambda r: r["start"]):
        out += [(b, {"start": start, "end": end, "replayed": False}) for b, start, end in beats(r)]
        out.append((rally_touch(r, people), {"start": clip(r)[0], "end": clip(r)[1], "replayed": r["i"] in replayed}))
    # A picked touch already in another clip is not shown twice.
    taken = [(span["start"], span["end"]) for _, span in out]
    out += [(c, {"start": start, "end": end, "replayed": False}) for c, start, end in extras if all(end <= a or start >= b for a, b in taken)]
    out.sort(key=lambda m: m[1]["start"])
    # The hook: a point the film comes back to later.
    scored = [r for r in chosen if r is not last and r is not longest and rally_touch(r, people) is scoring_touch(r)]
    if scored:
        c = rally_touch(max(scored, key=lambda r: striking(rally_touch(r, people))), people)
        out.insert(0, (c, {"start": c["t"] - HOOK_BEFORE_S, "end": c["t"] + HOOK_AFTER_S, "replayed": False, "hook": True}))
    return out


def highlight_film(page: dict, site: Path, stamp: str) -> dict | None:
    """What the match's film shows."""
    rallies, contacts, people = page["rallies"], page["contacts"], page.get("people") or {}
    moments = highlight_moments(page, read_picks(site.parent))
    if not moments:
        return None
    shots, at = [], 0.0

    def add(kind: str, length: float, start: float, speed: float, c: dict) -> None:
        nonlocal at
        shots.append({"kind": kind, "start": at, "length": length, "from": start, "speed": speed, "contact": c["i"], "rally": c["rally"], "who": who_of(c["person"], people)})
        at += length

    for c, span in moments[:1] if moments[0][1].get("hook") else []:
        add("live", span["end"] - span["start"], span["start"], 1, c)
        shots[-1]["hook"] = True
    moments = [m for m in moments if not m[1].get("hook")]
    add("intro", INTRO_S, moments[0][0]["t"] - LEAD_S, 1, moments[0][0])
    for c, span in moments:
        add("live", span["end"] - span["start"], span["start"], 1, c)
        if span["replayed"]:
            add("replay", (REPLAY_BEFORE_S + REPLAY_AFTER_S) / REPLAY_SPEED, c["t"] - REPLAY_BEFORE_S, REPLAY_SPEED, c)
    add("outro", OUTRO_S, moments[-1][0]["t"], 1, moments[-1][0])
    before = scores_before(rallies)
    used = sorted({s["rally"] for s in shots})
    fast = max((c for c in contacts if c.get("speed") is not None and people.get(str(c.get("person")), {}).get("name")), key=lambda c: c["speed"], default=None)
    sets = page.get("scores") or [f"{r['score'][0]}-{r['score'][1]}" for k, r in enumerate(rallies) if r.get("score") and (k + 1 == len(rallies) or rallies[k + 1]["set"] != r["set"])]
    won = [int(a) > int(b) for a, b in (x.split("-") for x in sets)]
    film = {
        "version": VERSION,
        "stamp": stamp,
        "kind": "highlights",
        "name": HIGHLIGHTS,
        "format": "wide",
        "team": None,
        "persons": [],
        "jersey": None,
        "teams": [t.get("name") for t in page.get("teams") or []],
        "colours": [t.get("colour") for t in page.get("teams") or []],
        "date": page.get("date"),
        "length": at,
        "shots": shots,
        "lines": lines_of(shots, voice_index(site), HIGHLIGHTS),
        "touches": 0,
        "points": 0,
        "fastest": fast["speed"] if fast else 0,
        "fastestName": people[str(fast["person"])]["name"] if fast else None,
        "sets": sets,
        "won": [sum(won), len(won) - sum(won)],
        "longest": max((sum(is_touch(c) for c in r["contacts"]) for r in rallies), default=0),
        "rallies": {
            str(k): {
                "start": rallies[k]["start"],
                "end": rallies[k]["end"],
                "set": rallies[k]["set"],
                "before": before[k],
                "score": rallies[k].get("score"),
                "touches": [[c["i"], c["t"], c["type"], c.get("person"), c.get("result"), c.get("speed"), c.get("reach"), c.get("x"), c.get("y")] for c in rallies[k]["contacts"]],
            }
            for k in used
        },
    }
    film["hash"] = hashlib.sha256(json.dumps(film, sort_keys=True).encode()).hexdigest()[:12]
    film["file"] = "resume.mp4"
    return film


def file_name(name: str, team: int) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return f"{team}-{'-'.join(re.findall(r'[a-z0-9]+', plain)) or 'film'}.mp4"


def plan(page: dict, site: Path, stamp: str = "") -> dict[str, dict]:
    """What each player's film shows, by name: all a film is made from, so that it is made again only when this changes.
    `stamp` says which tracking it stands on."""
    rallies, contacts = page["rallies"], page["contacts"]
    people = page.get("people") or {}
    voice = voice_index(site)
    picks = picked(contacts, read_picks(site.parent), page.get("fps", FPS))
    out = {}
    names = dict.fromkeys(q["name"] for q in people.values() if q.get("name"))
    for name in names:
        first = next(q for q in people.values() if q.get("name") == name)
        key = {int(p) for p, q in people.items() if q.get("name") == name and q.get("team") == first["team"] and q.get("number") is not None}
        mine = [c for c in contacts if c.get("person") in key]
        moments = moments_of(rallies, key, mine, [c for c in picks if c in mine])
        if len(moments) < LEAST_MOMENTS:
            continue
        shots, length = shots_of(moments, rallies)
        used = sorted({s["rally"] for s in shots})
        film = {
            "version": VERSION,
            "stamp": stamp,
            "name": name,
            "team": first["team"],
            "persons": sorted(key),
            "jersey": next((q["jersey"] for p, q in people.items() if int(p) in key and q.get("jersey") is not None), None),
            "teams": [t.get("name") for t in page.get("teams") or []],
            "colours": [t.get("colour") for t in page.get("teams") or []],
            "date": page.get("date"),
            "length": length,
            "shots": shots,
            "lines": lines_of(shots, voice, name),
            "touches": sum(is_touch(c) for c in mine),
            "points": sum(c.get("result") == "point" for c in mine),
            "fastest": max((c["speed"] for c in mine if c.get("speed") is not None), default=0),
            "rallies": {
                str(k): {
                    "start": rallies[k]["start"],
                    "end": rallies[k]["end"],
                    "set": rallies[k]["set"],
                    "before": scores_before(rallies)[k],
                    "score": rallies[k].get("score"),
                    "touches": [[c["i"], c["t"], c["type"], c.get("person"), c.get("result"), c.get("speed"), c.get("reach"), c.get("x"), c.get("y")] for c in rallies[k]["contacts"]],
                }
                for k in used
            },
        }
        film["hash"] = hashlib.sha256(json.dumps(film, sort_keys=True).encode()).hexdigest()[:12]
        film["file"] = file_name(name, first["team"])
        out[name] = film
    match_film = highlight_film(page, site, stamp)
    if match_film:
        out[HIGHLIGHTS] = match_film
    return out


def tracking_stamp(match: Path) -> str:
    """Which tracking the films stand on: another run of the pipeline moves them."""
    return "-".join(f"{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in (match / "players.csv", match / "ball.csv") if p.exists())


def manifest(match: Path) -> dict:
    path = match / FILMS / MANIFEST
    return json.loads(path.read_text()) if path.exists() else {}


def kind_of(name: str) -> str:
    """A film's kind: the match's highlights or a player's."""
    return "highlights" if name == HIGHLIGHTS else "players"


def status(match: Path) -> dict:
    """By kind, how many films the match should have and how many of them are missing or out of date."""
    out = {"players": {"total": 0, "stale": 0}, "highlights": {"total": 0, "stale": 0}}
    page = read_page(match / "review")
    if not page or not page.get("positions"):
        return out
    made = manifest(match)
    for name, film in plan(page, match / "review", tracking_stamp(match)).items():
        out[kind_of(name)]["total"] += 1
        out[kind_of(name)]["stale"] += made.get(name, {}).get("hash") != film["hash"] or not (match / FILMS / film["file"]).exists()
    return out


# The ball's path.


def moving(points: list[tuple]) -> list[tuple]:
    """Without what stays put for STILL_FRAMES: a ball on the floor, a light, a spot on the wall."""
    need = STILL_FRAMES * 0.6
    kept = []
    for p in points:
        near = [q[0] for q in points if abs(q[0] - p[0]) <= STILL_FRAMES and q is not p and np.hypot(q[1] - p[1], q[2] - p[2]) < STILL_PX]
        long_before = any(p[0] - q >= need for q in near)
        long_after = any(q - p[0] >= need for q in near)
        if len(near) < need or not (long_before or long_after):
            kept.append(p)
    return kept


def chain(points: list[tuple]) -> list[tuple]:
    """The longest sequence of `points` (frame, x, y) a ball could have followed, smooth where it can be."""
    n = len(points)
    if not n:
        return []
    frames = np.array([p[0] for p in points])
    xy = np.array([p[1:3] for p in points], float)
    score, before, speed = np.ones(n), -np.ones(n, int), np.zeros((n, 2))
    for i in range(n):
        for j in range(np.searchsorted(frames, frames[i] - CHAIN_FRAMES), i):
            gap = frames[i] - frames[j]
            if gap <= 0:
                continue
            v = (xy[i] - xy[j]) / gap
            if np.hypot(*v) > (TELEPORT_PX if gap <= 25 else 60):
                continue
            kink = min(1.0, np.hypot(*(v - speed[j])) / 40) * (0.7 if before[j] >= 0 else 0)
            value = score[j] + 1 - kink - 0.02 * (gap - 1)
            if value > score[i]:
                score[i], before[i], speed[i] = value, j, v
    i, out = int(np.argmax(score)), []
    while i >= 0:
        out.append(i)
        i = before[i]
    return [points[k] for k in reversed(out)]


def chains(points: list[tuple], least: int = 6) -> list[list[tuple]]:
    """Every chain in time order: the longest, then those before and after it, for a rally with long holes."""
    run = chain(points)
    if len(run) < least:
        return []
    return [*chains([p for p in points if p[0] < run[0][0]], least), run, *chains([p for p in points if p[0] > run[-1][0]], least)]


def split(run: list[tuple]) -> list[list[tuple]]:
    """`run` cut where the ball's velocity changes at once. Gravity bends it slowly."""
    f = np.array([p[0] for p in run], float)
    xy = np.array([p[1:3] for p in run], float)
    change = np.zeros(len(run))
    for k in range(3, len(run) - 3):
        if f[k + 3] - f[k - 3] <= 12:
            change[k] = np.hypot(*((xy[k + 3] - xy[k]) / max(1, f[k + 3] - f[k]) - (xy[k] - xy[k - 3]) / max(1, f[k] - f[k - 3])))
    cuts: list[int] = []
    for k in np.argsort(-change):
        if change[k] > max(KINK_PX, 0.3 * np.hypot(*((xy[min(k + 3, len(run) - 1)] - xy[k]) / 3))) and all(abs(k - c) >= 4 for c in cuts):
            cuts.append(int(k))
    edges = [0, *sorted(cuts), len(run) - 1]
    parts = []
    for a, b in zip(edges, edges[1:]):
        begin = a
        for k in range(a, b):
            hole = f[k + 1] - f[k]
            # Across a long hole the same flight goes on; another one is a touch nothing saw.
            if hole > LOST_FRAMES and np.hypot(*((xy[k + 1] - xy[k]) / hole - (xy[k] - xy[max(k - 3, 0)]) / max(1, f[k] - f[max(k - 3, 0)]))) > KINK_PX:
                parts.append(run[begin : k + 1])
                begin = k + 1
        parts.append(run[begin : b + 1])
    return parts


def curve(part: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """Frames and places of a flight across its holes: its curve, staying on the detections where they fit, else straight between them."""
    f = np.array([p[0] for p in part], float)
    xy = np.array([p[1:3] for p in part], float)
    frames = np.arange(int(f[0]), int(f[-1]) + 1)
    straight = np.c_[np.interp(frames, f, xy[:, 0]), np.interp(frames, f, xy[:, 1])]
    if len(part) < 4:
        return frames, straight
    degree = 3 if np.ptp(f) > 30 and len(part) >= 12 else 2
    centre = f.mean()
    design = lambda q: np.vander((np.asarray(q, float) - centre) / 25.0, degree + 1)  # noqa: E731
    good = np.ones(len(f), bool)
    for _ in range(3):
        cx = np.linalg.lstsq(design(f[good]), xy[good, 0], rcond=None)[0]
        cy = np.linalg.lstsq(design(f[good]), xy[good, 1], rcond=None)[0]
        off = np.c_[xy[:, 0] - design(f) @ cx, xy[:, 1] - design(f) @ cy]
        now = np.hypot(*off.T) < INLIER_PX
        if now.sum() < 4:
            break
        good = now
    if good.mean() < 0.8:
        return frames, straight
    w = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    w /= w.sum()
    smooth = lambda v: np.convolve(np.pad(np.interp(frames, f[good], v[good]), 4, mode="edge"), w, "valid")  # noqa: E731
    return frames, np.c_[design(frames) @ cx + smooth(off[:, 0]), design(frames) @ cy + smooth(off[:, 1])]


def size_key(frame: int, x: float, y: float) -> str:
    return f"{frame}:{round(x)}:{round(y)}"


def too_small(part: list[tuple], sizes: dict[str, float], least: Callable[[float, float], float]) -> bool:
    """Whether this flight's ball is too small to be on our court."""
    read = [sizes[size_key(*p)] for p in part if size_key(*p) in sizes]
    if len(read) < SIZE_LEAST_POINTS:
        return False
    middle = part[len(part) // 2]
    return float(np.percentile(read, 80)) < SMALL_FLIGHT * least(middle[1], middle[2])


def small_flights(found: dict, also: dict | None, start: int, end: int, sizes: dict[str, float], least: Callable[[float, float], float]) -> list[list[tuple]]:
    """The flights among the detections too small to be on our court."""
    return [part for run in chains(moving(candidates(found, also, start, end))) for part in split(run) if too_small(part, sizes, least)]


def candidates(found: dict, also: dict | None, start: int, end: int, rejected: dict | None = None) -> list[tuple]:
    """The detections through [start, end] as (frame, x, y), both when they differ, without those `rejected`."""
    points = [(q, float(found[q][0]), float(found[q][1])) for q in range(start, end + 1) if q in found]
    for q in range(start, end + 1):
        if also and q in also and (q not in found or np.hypot(found[q][0] - also[q][0], found[q][1] - also[q][1]) > 3):
            points.append((q, float(also[q][0]), float(also[q][1])))
    if rejected:
        points = [p for p in points if not (p[0] in rejected and np.hypot(p[1] - rejected[p[0]][0], p[2] - rejected[p[0]][1]) < 15)]
    return sorted(points)


def rally_path(found: dict, marks: list[int], start: int, end: int, also: dict | None = None, rejected: dict | None = None) -> dict[int, tuple[float, float]]:
    """Frame -> the ball's place through [start, end] from the detections `found` and `also` but those `rejected`; after the last touch
    (`marks`) it ends at the landing, or where the ball is lost. A touch's own frame can be some frames off: the ball's motion makes the flights."""
    points = candidates(found, also, start, end, rejected)
    last_touch = max([m for m in marks if start < m < end], default=end)
    out: dict[int, tuple[float, float]] = {}
    was = None
    for part in (p for run in chains(moving(points)) for p in split(run)):
        frames, path = curve(part)
        if was is not None:
            gap = frames[0] - was[0]
            if frames[0] > last_touch:
                v0 = (was[1] - was[2]) / max(1, was[3])
                back = min(3, len(path) - 1)
                v1 = (path[back] - path[0]) / max(1, back)
                # The floor: going down, then up, still the same way across. A block turns it back instead.
                if gap > LOST_FRAMES or (was[0] > last_touch and v0[1] > 2 and v1[1] < -2 and v0[0] * v1[0] >= 0):
                    break
            if 1 < gap <= JOIN_FRAMES and np.hypot(*(path[0] - was[1])) / gap <= TELEPORT_PX:
                for q in range(was[0] + 1, int(frames[0])):
                    place = was[1] + (path[0] - was[1]) * ((q - was[0]) / gap)
                    out[q] = (float(place[0]), float(place[1]))
        for q, p in zip(frames, path):
            # A curve's end past the picture is no ball.
            if -200 < p[0] < SOURCE_W + 200 and -400 < p[1] < SOURCE_H + 200:
                out[int(q)] = (float(p[0]), float(p[1]))
        back = min(3, len(path) - 1)
        was = (int(frames[-1]), path[-1], path[-1 - back], back)
    return out


def projector(cal: Calibration) -> Callable[[float, float, float], np.ndarray]:
    """(x, y, h) on the court, in metres, to the picture: the court's homography and the lens give the camera."""
    k = np.array(cal.lens["K"], float)
    inverse = np.linalg.inv(k)
    h = cal.homography
    r1, r2 = inverse @ h[:, 0], inverse @ h[:, 1]
    up = k @ np.cross(r1 / np.linalg.norm(r1), r2 / np.linalg.norm(r2)) * (np.linalg.norm(r1) + np.linalg.norm(r2)) / 2

    def project(x: float, y: float, height: float, sign: float = 1.0) -> np.ndarray:
        p = h @ np.array([x, y, 1.0]) + sign * height * up
        return distort((p[:2] / p[2])[None], cal.lens)[0]

    sign = 1.0 if project(0, 0, 2)[1] < project(0, 0, 0)[1] else -1.0
    return lambda x, y, height: project(x, y, height, sign)


def least_sizes(cal: Calibration) -> Callable[[float, float], float]:
    """Point of the picture -> the smallest a ball can look there while on our court, in pixels: along the ray through it, inside the
    volume it plays in, as far from the camera as it gets. From a grid of the picture."""
    k = np.array(cal.lens["K"], float)
    inverse = np.linalg.inv(k)
    h1, h2, h3 = (inverse @ cal.homography[:, c] for c in range(3))
    scale = (np.linalg.norm(h1) + np.linalg.norm(h2)) / 2
    r1, r2, t = h1 / scale, h2 / scale, h3 / scale
    r3 = np.cross(r1, r2)
    camera = -np.c_[r1, r2, r3].T @ t
    if camera[2] < 0:
        r3 = -r3
        camera = -np.c_[r1, r2, r3].T @ t
    rotation = np.c_[r1, r2, r3]

    def project(points: np.ndarray) -> np.ndarray:
        p = (k @ (rotation @ points.T + t[:, None])).T
        return distort(p[:, :2] / p[:, 2:], cal.lens)

    xs, ys = np.arange(0, SOURCE_W + 1, 120), np.arange(0, SOURCE_H + 1, 120)
    grid = np.zeros((len(ys), len(xs)))
    distances = np.linspace(1, 60, 120)[:, None]
    for j, y in enumerate(ys):
        pinhole = undistort(np.c_[xs, np.full(len(xs), y)].astype(float), cal.lens)
        for i, u in enumerate(pinhole):
            ray = rotation.T @ (inverse @ np.array([u[0], u[1], 1.0]))
            ray /= np.linalg.norm(ray)
            side = np.cross(ray, [0, 0, 1.0])
            side /= np.linalg.norm(side)
            points = camera + distances * ray
            inside = points[(np.abs(points[:, 0]) <= VOLUME_X) & (np.abs(points[:, 1]) <= VOLUME_Y) & (points[:, 2] >= 0) & (points[:, 2] <= VOLUME_H)]
            if len(inside):
                grid[j, i] = np.hypot(*(project(inside + side * BALL_M / 2) - project(inside - side * BALL_M / 2)).T).min()

    def least(x: float, y: float) -> float:
        return float(grid[int(np.clip(round(y / 120), 0, len(ys) - 1)), int(np.clip(round(x / 120), 0, len(xs) - 1))])

    return least


def ball_size(before: np.ndarray, picture: np.ndarray, after: np.ndarray, x: float, y: float) -> float | None:
    """The narrow side of what is at (x, y) in `picture` alone, in pixels: its length is the ball's blur."""
    reach = 70
    x0, y0 = int(max(0, x - reach)), int(max(0, y - reach))
    x1, y1 = int(x + reach), int(y + reach)
    if x1 <= x0 or y1 <= y0:
        return None
    crops = [cv2.cvtColor(p[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.int16) for p in (before, picture, after)]
    if not crops[1].size:
        return None
    changed = np.minimum(np.abs(crops[1] - crops[0]), np.abs(crops[1] - crops[2])).astype(np.uint8)
    mask = cv2.morphologyEx((changed > 16).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, centres = cv2.connectedComponentsWithStats(mask)
    best, nearest = None, 40.0
    for k in range(1, count):
        d = np.hypot(centres[k][0] + x0 - x, centres[k][1] + y0 - y)
        if d < nearest and stats[k, cv2.CC_STAT_AREA] >= 12:
            best, nearest = k, d
    if best is None:
        return None
    return float(min(cv2.minAreaRect(np.argwhere(labels == best)[:, ::-1].astype(np.float32))[1]))


def read_ball(path: Path) -> dict[int, tuple[float, float]]:
    found = {}
    with open(path) as f:
        next(f)
        for line in f:
            frame, seen, x, y = line.strip().split(",")
            if seen == "1":
                found[int(frame)] = (float(x), float(y))
    return found


def frame_times(match: Path, video: Path) -> np.ndarray:
    """Each frame's real time: a video's rate need not be even, and a time made from a frame's number then drifts."""
    path = match / TIMES_CACHE
    if path.exists():
        return np.load(path)
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    times = np.sort(np.array([float(line.split(",")[0]) for line in done.stdout.splitlines() if line.strip()]))
    np.save(path, times)
    return times


def decoder(video: Path, times: np.ndarray, frame: int, count: int) -> subprocess.Popen:
    """The video's frames from `frame`, exactly, as raw pictures."""
    return subprocess.Popen(
        ["ffmpeg", "-v", "quiet", *hardware(), "-ss", f"{times[frame] - 0.004:.4f}", "-i", str(video), "-frames:v", str(count), "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE,
    )


def hardware() -> list[str]:
    return ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []


def read_picture(process: subprocess.Popen) -> np.ndarray | None:
    size = SOURCE_W * SOURCE_H * 3
    raw = process.stdout.read(size)
    return np.frombuffer(raw, np.uint8).reshape(SOURCE_H, SOURCE_W, 3) if len(raw) == size else None


def closed(process: subprocess.Popen) -> None:
    process.stdout.close()
    process.terminate()
    process.wait()


def shown_span(shot: dict, t: float) -> tuple[float, float]:
    """The match time a shot shows."""
    return (t - REPLAY_BEFORE_S, t + REPLAY_AFTER_S) if shot["kind"] == "replay" else (shot["from"], shot["from"] + shot["length"] * shot["speed"])


def search_ball(match: Path, video: Path, court: Path, films: dict[str, dict], page: dict) -> dict:
    """The ball searched again around where the first pass puts it, in the frames these films show and no search has seen. Kept."""
    import torch

    path = match / BALL_CACHE
    cache = json.loads(path.read_text()) if path.exists() else {"seen": [], "found": {}}
    seen = {int(q) for q in cache["seen"]}
    found = {int(q): tuple(v) for q, v in cache["found"].items()}
    sizes: dict[str, float] = cache.get("sizes", {})
    sized = {int(q) for q in cache.get("sized", [])}
    rejected = {int(q): tuple(v) for q, v in cache.get("rejected", {}).items()}
    least = least_sizes(Calibration.load(court))
    detected = read_ball(match / "ball.csv")
    times = frame_times(match, video)
    marks_of = marks(page)
    wanted: dict[int, set[int]] = {}
    for film in films.values():
        for shot in film["shots"]:
            if shot["kind"] in ("live", "replay"):
                a, b = shown_span(shot, page["contacts"][shot["contact"]]["t"])
                wanted.setdefault(shot["rally"], set()).update(range(round((a - WINDOW_PAD_S) * FPS), round((b + WINDOW_PAD_S) * FPS) + 1))
    device = tracker.default_device()
    model = tracker.load_model(device)

    @torch.no_grad()
    def look(jobs: list[tuple], crop: tuple[int, int], avoid: Callable[[int], tuple | None] = lambda _: None) -> list[tuple | None]:
        """The best place of each job (three frames, a centre, a frame) in a crop around its centre, away from `avoid`'s for its frame."""
        out = []
        w, h = crop
        for at in range(0, len(jobs), BATCH):
            part = jobs[at : at + BATCH]
            corners = [(int(np.clip(job[1][0] - w / 2, 0, SOURCE_W - w)), int(np.clip(job[1][1] - h / 2, 0, SOURCE_H - h))) for job in part]
            inputs = np.stack([np.concatenate([tracker.preprocess(p[y : y + h, x : x + w]) for p in job[0]]) for job, (x, y) in zip(part, corners)])
            maps = model(torch.from_numpy(inputs).to(device))[0].sigmoid().cpu().numpy()
            for heat, (x, y), job in zip(maps, corners, part):
                middle = heat[1].copy()
                spot = avoid(job[2]) if len(job) > 2 else None
                if spot:
                    cv2.circle(middle, (round((spot[0] - x) * tracker.WIDTH / w), round((spot[1] - y) * tracker.HEIGHT / h)), max(3, round(50 * tracker.WIDTH / w)), 0, -1)
                blob = tracker.best_blob(middle)
                out.append((round(x + blob[0] * w / tracker.WIDTH, 1), round(y + blob[1] * h / tracker.HEIGHT, 1), round(blob[2], 3)) if blob and blob[2] >= tracker.THRESHOLD[1] else None)
        return out

    def sweep(frames: list[int], centre: Callable[[int], tuple[float, float]], avoid: Callable[[int], tuple | None] = lambda _: None) -> None:
        """Searches `frames`, around `centre`, in the sharper crop where the wider one misses or doubts."""
        asked = set(frames)
        for a, b in ranges(frames):
            process = decoder(video, times, a - 1, b - a + 3)
            rolling, pending = [], []
            current = a - 2

            def flush() -> None:
                results = look([(pictures, centre(q), q) for q, pictures in pending], CROPS[0], avoid)
                sharper = [(k, q, pictures) for k, ((q, pictures), hit) in enumerate(zip(pending, results)) if hit is None]
                for (k, _, _), hit in zip(sharper, look([(pictures, centre(q), q) for _, q, pictures in sharper], CROPS[1], avoid)):
                    results[k] = hit
                for (q, _), hit in zip(pending, results):
                    if hit:
                        found[q] = hit
                    elif avoid(q):
                        found.pop(q, None)
                pending.clear()

            while current < b + 1:
                picture = read_picture(process)
                if picture is None:
                    break
                current += 1
                rolling = [*rolling[-2:], picture]
                if len(rolling) == 3 and current - 1 in asked:
                    pending.append((current - 1, list(rolling)))
                    if len(pending) == BATCH:
                        flush()
            if pending:
                flush()
            closed(process)

    @torch.no_grad()
    def follow(k: int, frames: list[int], last: int) -> None:
        """The ball after a rally's last touch, followed forward from it."""
        known = sorted(q for q in {**detected, **found} if last - 8 <= q <= last)
        if not known or not frames:
            return
        merged = {**detected, **found}
        place, at, velocity = np.array(merged[known[-1]][:2], float), known[-1], np.zeros(2)
        process = decoder(video, times, last - 1, frames[-1] - last + 3)
        rolling, current = [], last - 2
        while current < frames[-1] + 1:
            picture = read_picture(process)
            if picture is None:
                break
            current += 1
            rolling = [*rolling[-2:], picture]
            if len(rolling) < 3 or current - 1 <= last:
                continue
            q = current - 1
            expected = np.clip(place + velocity * (q - at), 0, [SOURCE_W, SOURCE_H])
            best = None
            for crop in TAIL_CROPS:
                hit = look([(rolling, expected)], crop)[0]
                if hit:
                    score = hit[2] / (1 + np.hypot(hit[0] - expected[0], hit[1] - expected[1]) / 300)
                    if best is None or score > best[0]:
                        best = (score, hit)
            if best:
                spot = np.array(best[1][:2])
                # Right after the touch it can be anywhere: the touch changed its way.
                if q - last < 6 or np.hypot(*(spot - expected)) < 260:
                    if q - at <= 6:
                        velocity = 0.5 * velocity + 0.5 * (spot - place) / (q - at)
                    place, at = spot, q
                    if q not in detected:
                        found[q] = best[1]
        closed(process)

    def measure(frames: list[int]) -> None:
        """The size of every detection at `frames`."""
        for a, b in ranges(frames):
            process = decoder(video, times, a - SIZE_GAP - 1, b - a + 2 * SIZE_GAP + 3)
            pictures: dict[int, np.ndarray] = {}
            current = a - SIZE_GAP - 2
            while current < b + SIZE_GAP:
                picture = read_picture(process)
                if picture is None:
                    break
                current += 1
                pictures[current] = picture
                q = current - SIZE_GAP
                if q >= a and q - SIZE_GAP in pictures:
                    for place in (found.get(q), detected.get(q)):
                        if place:
                            size = ball_size(pictures[q - SIZE_GAP], pictures[q], picture, place[0], place[1])
                            if size is not None:
                                sizes[size_key(q, place[0], place[1])] = round(size, 1)
                    sized.add(q)
                pictures.pop(current - 2 * SIZE_GAP - 1, None)
            closed(process)

    def save() -> None:
        files.write_text(path, json.dumps({"seen": sorted(seen), "found": {str(q): v for q, v in found.items()}, "sizes": sizes, "sized": sorted(sized), "rejected": {str(q): v for q, v in rejected.items()}}, separators=(",", ":")))

    for k, frames in sorted(wanted.items()):
        new = sorted(frames - seen)
        rally_marks = marks_of[k]
        if not new:
            if frames <= sized:
                continue
        last = max(rally_marks)
        inside = [q for q in new if q <= last]
        if inside:
            wide = rally_path({}, rally_marks, min(rally_marks) - 30, last + 10, detected)
            sweep(inside, centre_of(wide, detected))
            missing = [q for q in inside if q not in found]
            if missing:
                sweep(missing, centre_of(rally_path(found, rally_marks, min(rally_marks) - 30, last + 10, detected), detected))
        follow(k, [q for q in new if q > last], last)
        seen.update(new)
        # What is too small is another court's ball: dropped, its frames searched again away from it for the real one.
        start, end = min(rally_marks) - 30, last + TAIL_FRAMES
        measure(sorted(frames - sized))
        for part in small_flights(found, detected, start, end, sizes, least):
            rejected.update({p[0]: (p[1], p[2]) for p in part})
        wrong = sorted(q for q in rejected if q in frames and q <= last)
        if wrong:
            sweep(wrong, centre_of(rally_path(found, rally_marks, start, end, detected, rejected), detected), rejected.get)
            for q in wrong:
                sized.discard(q)
            measure(wrong)
        save()
    return found


def ranges(frames: list[int]) -> list[tuple[int, int]]:
    """`frames`, sorted, as ranges, those under 6 frames apart joined: the video is read through them anyway."""
    out: list[list[int]] = []
    for q in frames:
        if out and q - out[-1][1] <= 6:
            out[-1][1] = q
        else:
            out.append([q, q])
    return [(a, b) for a, b in out]


def centre_of(path: dict, detected: dict) -> Callable[[int], tuple[float, float]]:
    """Where to look at a frame: on the path, else between the places around it."""
    known = sorted(path) or sorted(detected)
    xs, ys = np.array([path.get(q, detected.get(q))[0] for q in known]), np.array([path.get(q, detected.get(q))[1] for q in known])
    return lambda q: (float(np.interp(q, known, xs)), float(np.interp(q, known, ys)))


def marks(page: dict) -> dict[int, list[int]]:
    """Each rally's contacts' frames."""
    out: dict[int, list[int]] = {}
    for c in page["contacts"]:
        out.setdefault(c["rally"], []).append(int(c.get("f", round(c["t"] * FPS))))
    return out


def film_path(page: dict, film: dict, detected: dict, found: dict, places: dict[int, list[float]], cal: Calibration, rejected: dict | None = None) -> dict[int, tuple[float, float]]:
    """Frame -> the ball's place through a film's rallies, across the holes; up to a touch's 3D place for a fast ball nothing sees."""
    project = projector(cal)
    out: dict[int, tuple[float, float]] = {}
    marks_of = marks(page)
    for k in {s["rally"] for s in film["shots"]}:
        m = marks_of[k]
        path = rally_path(found, m, min(m) - 30, max(m) + TAIL_FRAMES, detected, rejected)
        for c in page["rallies"][k]["contacts"]:
            frame = int(c.get("f", round(c["t"] * FPS)))
            before = max((q for q in path if q < frame), default=None)
            if c["type"] == "floor" or c["i"] not in places or before is None or not 2 <= frame - before <= 45:
                continue
            a, b = np.array(path[before]), project(*places[c["i"]])
            for q in range(before + 1, frame + 1):
                if q not in path:
                    place = a + (b - a) * ((q - before) / (frame - before))
                    path[q] = (float(place[0]), float(place[1]))
        out.update(path)
    return out


# The film.


def gauss(values: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return values
    reach = int(3 * sigma)
    w = np.exp(-0.5 * (np.arange(-reach, reach + 1) / sigma) ** 2)
    return np.convolve(np.pad(values, reach, mode="edge"), w / w.sum(), "valid")


def ease(a: float, b: float, x):
    u = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def out_back(u: float) -> float:
    """Past its end, then back: what slams in."""
    u = float(np.clip(u, 0, 1))
    return 1 + 2.4 * (u - 1) ** 3 + 1.4 * (u - 1) ** 2


def holds(target: np.ndarray, slack: float) -> np.ndarray:
    """A path that holds still while the target stays within `slack`, then moves only as far as it must: an operator's pan."""
    forth = np.zeros_like(target)
    forth[0] = target[0]
    for i in range(1, len(target)):
        forth[i] = np.clip(forth[i - 1], target[i] - slack, target[i] + slack)
    back = np.zeros_like(target)
    back[-1] = forth[-1]
    for i in range(len(target) - 2, -1, -1):
        back[i] = np.clip(back[i + 1], forth[i] - slack / 2, forth[i] + slack / 2)
    return (forth + back) / 2


def handheld(n: int, amount: float, rng: np.random.Generator) -> np.ndarray:
    """An operator's slow drift."""
    t = np.arange(n) / FPS
    return amount * sum(w * np.sin(2 * np.pi * hz * t + rng.uniform(0, 6.28)) for hz, w in ((0.17, 1), (0.31, 0.7), (0.53, 0.4), (0.97, 0.2)))


def keep_in_view(centre: np.ndarray, ball: np.ndarray, half: np.ndarray, known: np.ndarray) -> np.ndarray:
    """The camera's `centre` moved, smoothly and ahead of time, so that the `ball`, where `known`, stays within `half` of it."""
    out = centre.copy()
    for _ in range(4):
        gap = np.where(known, ball - out, 0.0)
        out = out + gauss(np.sign(gap) * np.maximum(np.abs(gap) - half, 0.0), FPS * 0.1)
    return out


def font(name: str, fallback: str = "sans") -> cv2.FontFace:
    """The Mac's font, else OpenCV's own."""
    return cv2.FontFace(str(FONTS / name) if (FONTS / name).exists() else fallback)


def text_width(text: str, face: cv2.FontFace, size: int) -> int:
    return cv2.putText(np.zeros((1, 1, 3), np.uint8), text, (0, 0), (0, 0, 0), face, size, 400)[0][0]


def write(g: np.ndarray, text: str, x: float, y: float, size: int, face: cv2.FontFace, color=WHITE, widest: int | None = None, center: bool = False) -> None:
    while widest and text_width(text, face, size) > widest and size > 14:
        size -= 2
    if center:
        x -= text_width(text, face, size) // 2
    cv2.putText(g, text, (int(x), int(y)), color, face, size, 400)


def slant(g: np.ndarray, x: int, y: int, w: int, h: int, color, alpha: float = 1.0, lean: int = 14) -> None:
    """A slanted panel, as race graphics draw them."""
    points = np.array([[x + lean, y], [x + w + lean, y], [x + w, y + h], [x, y + h]], np.int32)
    if alpha >= 1:
        cv2.fillPoly(g, [points], color, cv2.LINE_AA)
        return
    x0, x1, y0, y1 = max(0, x), min(WIDTH, x + w + lean + 1), max(0, y), min(HEIGHT, y + h)
    if x1 > x0 and y1 > y0:
        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillPoly(mask, [points - [x0, y0]], 255, cv2.LINE_AA)
        a = mask[..., None] / 255.0 * alpha
        part = g[y0:y1, x0:x1]
        part[:] = (part * (1 - a) + np.array(color) * a).astype(np.uint8)


def add_light(g: np.ndarray, light: np.ndarray, x: int, y: int) -> None:
    """`light`, a small picture, added over `g` at (x, y)."""
    x0, y0, x1, y1 = max(0, x), max(0, y), min(WIDTH, x + light.shape[1]), min(HEIGHT, y + light.shape[0])
    if x1 > x0 and y1 > y0:
        part = g[y0:y1, x0:x1]
        part[:] = np.clip(part.astype(np.int16) + light[y0 - y : y1 - y, x0 - x : x1 - x], 0, 255).astype(np.uint8)


class Maker:
    """Makes the films of a match, its models and what they read loaded once."""

    def __init__(self, match: Path, video: Path, court: Path, page: dict):
        from ultralytics import YOLO

        self.match, self.video, self.page = match, video, page
        self.cal = Calibration.load(court)
        self.times = frame_times(match, video)
        self.seg, self.fine = YOLO(str(SEG_S)), YOLO(str(SEG_M))
        self.italic, self.din, self.cond = font("Arial Bold Italic.ttf"), font("DIN Alternate Bold.ttf"), font("DIN Condensed Bold.ttf")
        self.words = locale()
        self.detected = read_ball(match / "ball.csv")
        cache = json.loads((match / BALL_CACHE).read_text()) if (match / BALL_CACHE).exists() else {"found": {}}
        self.found = {int(q): tuple(v) for q, v in cache["found"].items()}
        self.rejected = {int(q): tuple(v) for q, v in cache.get("rejected", {}).items()}
        site = match / "review"
        text = (site / "ball3d.js").read_text() if (site / "ball3d.js").exists() else "=[]"
        flat = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
        self.places = {int(flat[k]): flat[k + 1 : k + 4] for k in range(0, len(flat), 4)}
        k = np.array(self.cal.lens["K"], float)
        inverse = np.linalg.inv(k)
        r1, r2 = inverse @ self.cal.homography[:, 0], inverse @ self.cal.homography[:, 1]
        self.vanishing = k @ np.cross(r1 / np.linalg.norm(r1), r2 / np.linalg.norm(r2))
        self.step_s = page["positions"]["step"] / FPS
        self.tracks: dict[int, np.ndarray] = {}
        self.load_tracks()

    def load_tracks(self) -> None:
        """Everyone's places by sample: the page's, smoothed."""
        pos = self.page["positions"]
        size = pos["files"] * pos["every"] + 1
        for n in range(pos["files"]):
            text = (self.match / "review" / "positions" / f"{n}.js").read_text()
            _, columns = json.loads(text[text.index(",") + 1 : text.rindex(")")])
            for person, runs, xs, ys in columns:
                places = self.tracks.setdefault(person, np.full((size, 2), np.nan))
                k = move = x = y = 0
                for i, run in enumerate(runs):
                    if i % 2:
                        for _ in range(run):
                            x += xs[move]
                            y += ys[move]
                            move += 1
                            places[n * pos["every"] + k] = (x * pos["cm"] / 100, y * pos["cm"] / 100)
                            k += 1
                    else:
                        k += run

    def track(self, persons: list[int]) -> np.ndarray:
        """A player's places by sample, across their tracking numbers."""
        out = np.full_like(next(iter(self.tracks.values())), np.nan)
        for person in persons:
            if person in self.tracks:
                there = np.isfinite(self.tracks[person][:, 0])
                out[there] = self.tracks[person][there]
        return out

    def who(self, shot: dict) -> dict:
        """Whom a shot shows: the film's player, or in the match's film the touch's."""
        return shot.get("who") or {key: self.film[key] for key in ("name", "team", "persons", "jersey")}

    def follow_body(self, shot: dict) -> None:
        """The body the shot follows: the named player, unless their track is not where a server stands."""
        who = self.who(shot)
        self.named = self.track(who["persons"])
        self.named_known = np.flatnonzero(np.isfinite(self.named[:, 0]))
        self.hero, self.known = self.named, self.named_known
        c = self.contact(shot)
        if c["type"] != "serve":
            return
        k = round(c["t"] / self.step_s)
        here = lambda places: tuple(places[k]) if k < len(places) and np.isfinite(places[k, 0]) else None  # noqa: E731
        people = self.page["people"]
        team = {p: here(t) for p, t in self.tracks.items() if people.get(str(p), {}).get("team") == who["team"] and p not in who["persons"] and here(t)}
        other = serving_body(here(self.named), team)
        if other is not None:
            self.hero = self.tracks[other]
            self.known = np.flatnonzero(np.isfinite(self.hero[:, 0]))

    def lean(self, x: float, y: float) -> float:
        """How far the local up leans in the picture, from the court's vanishing point and the lens."""
        p = undistort(np.array([[x, y]], float), self.cal.lens)[0]
        way = self.vanishing[:2] / self.vanishing[2] - p if abs(self.vanishing[2]) > 1e-9 else self.vanishing[:2]
        a, b = distort(np.array([p, p + 12 * way / np.linalg.norm(way)]), self.cal.lens)
        v = b - a if (b - a)[1] <= 0 else a - b
        return float(np.arctan2(v[0], -v[1]))

    def make(self, film: dict, out: Path) -> None:
        """The film of `film` (`plan`) in the file `out`, H.264 with its sound."""
        use_format(film.get("format", "tall"))
        self.film = film
        self.name = film["name"]
        self.ball = film_path(self.page, film, self.detected, self.found, self.places, self.cal, self.rejected)
        self.rng = np.random.default_rng(7)
        # The bars cross a change of shot kind; one action cuts straight to the next.
        self.cuts = [b["start"] for a, b in zip(film["shots"], film["shots"][1:]) if a["kind"] != b["kind"]]
        self.impacts: list[float] = []
        self.on_rally = None
        self.masks: dict[tuple, np.ndarray | None] = {}
        self.below = " · ".join(x for x in (film["teams"][film["team"] - 1] if film["teams"] and film["team"] else None, self.long_date(film["date"])) if x).upper()
        silent = out.with_suffix(".video.mp4")
        encoder = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(int(FPS)), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "29", "-g", "50", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)],
            stdin=subprocess.PIPE,
        )
        for shot in film["shots"]:
            self.shoot(shot, encoder)
        encoder.stdin.close()
        encoder.wait()
        sound = out.with_suffix(".pcm")
        sound.write_bytes(self.sound().astype(np.float32).tobytes())
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", str(sound), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-shortest", str(out)],
            check=True,
        )
        silent.unlink()
        sound.unlink()

    @staticmethod
    def long_date(date: str | None) -> str | None:
        if not date:
            return None
        months = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
        year, month, day = date.split("-")
        return f"{int(day)} {months[int(month) - 1]} {year}"

    def contact(self, shot: dict) -> dict:
        return self.page["contacts"][shot["contact"]]

    def hero_at(self, moment: float) -> tuple[float, float]:
        k = moment / self.step_s
        return float(np.interp(k, self.known, self.hero[self.known, 0])), float(np.interp(k, self.known, self.hero[self.known, 1]))

    def hero_px(self, moment: float) -> tuple[np.ndarray, float]:
        """The player's feet in the picture, and how many pixels a metre takes there."""
        x, y = self.hero_at(moment)
        a, b = self.cal.to_image(np.array([[x - 0.5, y], [x + 0.5, y]]))
        return self.cal.to_image(np.array([[x, y]]))[0], float(np.hypot(*(b - a)))

    def touch_time(self, shot: dict) -> float:
        """The moment around the touch the ball is nearest the player's raised hands."""
        t = self.contact(shot)["t"]
        best, at = 1e9, t
        for f in range(int((t - 0.14) * FPS), int((t + 0.14) * FPS) + 1):
            b = self.ball.get(f)
            if b:
                feet, ppm = self.hero_px(f / FPS)
                d = np.hypot(b[0] - feet[0], b[1] - (feet[1] - 2.3 * ppm))
                if d < best:
                    best, at = d, f / FPS
        return at

    def moments(self, shot: dict) -> np.ndarray:
        """The match time of each frame: the replay ramps down into a freeze on the touch and back up."""
        n = int(round(shot["length"] * FPS))
        tau = np.arange(n) / FPS
        if shot["kind"] != "replay":
            return shot["from"] + tau * shot["speed"]
        t = self.touch_time(shot)
        after = shot["length"] - REPLAY_PRE - FREEZE
        return np.where(tau < REPLAY_PRE, t - 1.0 + (1 - np.maximum(0, 1 - tau / REPLAY_PRE) ** 1.7), np.where(tau < REPLAY_PRE + FREEZE, t, t + 0.8 * (np.maximum(0, tau - REPLAY_PRE - FREEZE) / after) ** 1.5))

    def camera(self, shot: dict, ms: np.ndarray) -> tuple[np.ndarray, ...]:
        """Where an operator would frame each frame: holding, then panning, with room towards the net, pushing in on the touch."""
        n, tau, t, kind = len(ms), np.arange(len(ms)) / FPS, self.contact(shot)["t"], shot["kind"]
        located = [self.hero_px(m) for m in ms]
        feet = np.array([p for p, _ in located])
        ppm = float(np.median([q for _, q in located]))
        heads = feet[:, 1] - 1.1 * ppm
        seen = [self.ball.get(int(round(m * FPS))) for m in ms]
        have = np.array([s is not None for s in seen])
        if have.sum() >= 2:
            at = np.flatnonzero(have)
            bx = np.interp(np.arange(n), at, [seen[k][0] for k in at])
            by = np.interp(np.arange(n), at, [seen[k][1] for k in at])
        else:
            bx, by = feet[:, 0].copy(), heads.copy()
        net = self.cal.to_image(np.array([[0.0, 0.0]]))[0][0]
        room = np.sign(net - feet[:, 0])
        if kind == "live":
            if self.contact(shot)["type"] == "serve":
                on = 1 - ease(t + 0.05, t + 0.5, ms)
                tall = 7.6 * ppm + (1800 - 7.6 * ppm) * ease(t, t + 1.1, ms)
            else:
                tight = 8.4 * ppm
                wide = np.clip(np.percentile(np.abs(feet[:, 0] - bx), 80) * 1.3 / ASPECT, 1500, 1950)
                on = ease(t - ON_PLAYER_BEFORE_S, t - 0.25, ms) * (1 - ease(t + 0.1, t + ON_PLAYER_AFTER_S, ms))
                tall = wide + (tight - wide) * ease(t - 2.2, t - 0.15, ms) + (wide - tight) * ease(t + 0.1, t + 0.9, ms)
            # Wide enough for where the ball is flying.
            flight = np.hypot(np.gradient(bx), np.gradient(by)) * FPS
            tall = np.maximum(tall, np.minimum(SOURCE_H, gauss(flight, FPS * 0.2) * FLIGHT_IN_VIEW_S / ASPECT) * (1 - on))
            # Wide enough for both the player and the ball at their touch.
            both = np.maximum(np.abs(bx - feet[:, 0]) * 1.5 / ASPECT, np.abs(by - heads) * 1.5)
            near_touch = np.exp(-(((ms - t) / 0.6) ** 2))
            tall = np.maximum(tall, np.minimum(SOURCE_H, both) * near_touch)
        elif kind == "replay":
            on = np.ones(n)
            tall = 6.8 * ppm - 1.4 * ppm * ease(0, REPLAY_PRE, tau) - 0.9 * ppm * ease(REPLAY_PRE, REPLAY_PRE + FREEZE, tau) + 1.5 * ppm * ease(REPLAY_PRE + FREEZE, shot["length"], tau)
        else:
            on = np.ones(n)
            tall = 1750 - 330 * ease(0, shot["length"], tau) if kind == "intro" else 1050 + 650 * ease(0, shot["length"], tau)
        tall = np.clip(tall, 820, SOURCE_H)
        wide_px = tall * ASPECT
        # The player's feet in the lower third, clear of the caption.
        tx = on * (feet[:, 0] + room * 0.1 * wide_px) + (1 - on) * bx
        ty = on * (feet[:, 1] - 0.2 * tall) + (1 - on) * (0.6 * by + 0.4 * (feet[:, 1] - 0.25 * tall))
        if kind == "replay":
            near = np.exp(-(((ms - self.touch_time(shot)) / 0.5) ** 2))
            tx = tx + 0.35 * near * np.clip(bx - tx, -0.3 * wide_px, 0.3 * wide_px)
            ty = ty + 0.35 * near * np.clip(by - ty, -0.3 * tall, 0.3 * tall)
        if kind in ("live", "replay"):
            # Near the player only as long as the shot is on them.
            free = 1e4 * (1 - on)
            tx = np.clip(tx, feet[:, 0] - 0.3 * wide_px - free, feet[:, 0] + 0.3 * wide_px + free)
            ty = np.clip(ty, feet[:, 1] - 0.32 * tall - free, feet[:, 1] + 0.22 * tall + free)
        slack_x, slack_y = (0.13, 0.08) if kind == "live" else (0.05, 0.03)
        cx = gauss(holds(tx, float(np.median(slack_x * wide_px))), FPS * (0.42 if kind == "live" else 0.3))
        cy = gauss(holds(ty, float(np.median(slack_y * tall))), FPS * (0.5 if kind == "live" else 0.3))
        tall = np.exp(gauss(np.log(tall), FPS * 0.18))
        # An operator is a beat behind the play.
        if kind == "live" and n > 4:
            lag = int(0.07 * FPS)
            cx, cy = np.r_[np.full(lag, cx[0]), cx[:-lag]], np.r_[np.full(lag, cy[0]), cy[:-lag]]
        if kind == "live":
            # The player comes first while the shot is on them.
            watched = have & (on < 0.5)
            cx = keep_in_view(cx, bx, BALL_IN_VIEW * tall * ASPECT / 2, watched)
            cy = keep_in_view(cy, by, BALL_IN_VIEW * tall / 2, watched)
            cx = keep_in_view(cx, feet[:, 0], BALL_IN_VIEW * tall * ASPECT / 2, on >= 0.5)
            cy = keep_in_view(cy, feet[:, 1] - 0.5 * ppm, BALL_IN_VIEW * tall / 2, on >= 0.5)
        if kind == "live" and self.impact is not None:
            # A jolt and a push in on the point's touch.
            since = ms - self.impact
            after = since >= 0
            jolt = np.where(after, np.exp(-np.abs(since) / 0.14), 0)
            cx = cx + 0.012 * tall * jolt * np.sin(2 * np.pi * 13 * since)
            cy = cy + 0.009 * tall * jolt * np.cos(2 * np.pi * 17 * since)
            tall = tall * (1 - 0.07 * np.where(after, np.exp(-np.abs(since) / 0.3), 0))
        # Upright, as far as it costs no picture: a corner's full correction would push the player out of the video.
        leans = np.array([self.lean(a, b) for a, b in zip(cx[::10], cy[::10])])
        roll = gauss(np.clip(np.interp(np.arange(n), np.arange(n)[::10], -leans), -np.radians(7), np.radians(7)), FPS * 0.4) + np.radians(handheld(n, 0.07, self.rng))
        cx = cx + handheld(n, 0.0022, self.rng) * tall
        cy = cy + handheld(n, 0.0018, self.rng) * tall
        half_w = tall * ASPECT / 2 * np.abs(np.cos(roll)) + tall / 2 * np.abs(np.sin(roll))
        half_h = tall * ASPECT / 2 * np.abs(np.sin(roll)) + tall / 2 * np.abs(np.cos(roll))
        fit = np.minimum(1, np.minimum(SOURCE_W / 2 / half_w, SOURCE_H / 2 / half_h))
        return np.clip(cx, half_w * fit, SOURCE_W - half_w * fit), np.clip(cy, half_h * fit, SOURCE_H - half_h * fit), tall * fit, roll

    def shoot(self, shot: dict, encoder: subprocess.Popen) -> None:
        self.follow_body(shot)
        ms = self.moments(shot)
        # Each point's touch hits.
        punch = shot["kind"] == "live" and self.contact(shot).get("result") == "point"
        self.impact = self.touch_time(shot) if punch else None
        if self.impact is not None:
            self.impacts.append(shot["start"] + np.searchsorted(ms, self.impact) / FPS)
        cx, cy, tall, roll = self.camera(shot, ms)
        # The score stays put across the cuts within a rally.
        fresh, self.on_rally = shot["rally"] != self.on_rally, shot["rally"]
        first = int(round(ms.min() * FPS))
        last = int(round(ms.max() * FPS))
        process = decoder(self.video, self.times, first, last - first + 2)
        got, picture = first - 1, None
        people = np.zeros((HEIGHT, WIDTH), bool)
        for i, moment in enumerate(ms):
            want = int(round(moment * FPS))
            while got < want:
                next_picture = read_picture(process)
                if next_picture is None:
                    break
                picture, got = next_picture, got + 1
            if picture is None:
                continue
            z = HEIGHT / tall[i]
            c, s = np.cos(roll[i]), np.sin(roll[i])
            linear = z * np.array([[c, -s], [s, c]])
            m = np.c_[linear, np.array([WIDTH / 2, HEIGHT / 2]) - linear @ np.array([cx[i], cy[i]])]
            g = cv2.warpAffine(picture, m, (WIDTH, HEIGHT), flags=cv2.INTER_CUBIC if tall[i] < HEIGHT else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            tau = i / FPS
            if self.impact is not None and 0 <= moment - self.impact < 0.2:
                flash = 0.6 * np.exp(-(moment - self.impact) / 0.05)
                g[:] = cv2.addWeighted(g, 1 - flash, np.full_like(g, 255), flash, 0)
            if shot["kind"] in ("live", "replay"):
                # Everyone's outline changes slowly: what is painted on the court hides under it, read every other frame.
                if i % 2 == 0:
                    people = self.outlines(g)
                self.effects(g, shot, moment, tau, m, tall[i], people)
                if not shot.get("hook"):
                    self.tower(g, shot, tau if fresh else 1.0, moment)
                    self.caption(g, shot, tau)
                    self.banner(g, shot, moment)
                if shot["kind"] == "replay":
                    self.telemetry(g, shot, tau)
            elif shot["kind"] == "intro":
                self.title_card(g, tau)
            else:
                self.end_card(g, tau)
            self.stinger(g, shot["start"] + tau)
            encoder.stdin.write(g.tobytes())
        closed(process)

    def outlines(self, g: np.ndarray) -> np.ndarray:
        result = self.seg.predict(g, imgsz=640, classes=[0], device=tracker.default_device(), verbose=False, retina_masks=True)[0]
        return result.masks.data.cpu().numpy().max(0) > 0.5 if result.masks is not None else np.zeros((HEIGHT, WIDTH), bool)

    def cut_out(self, g: np.ndarray, frame: int, feet: np.ndarray, scale: float) -> np.ndarray | None:
        """The player's outline, from a zoomed crop around them, as (x0, y0, mask). The same frame frozen is read once."""
        if frame in self.masks:
            return self.masks[frame]
        x0, x1 = int(max(0, feet[0] - 2.2 * scale)), int(min(WIDTH, feet[0] + 2.2 * scale))
        y0, y1 = int(max(0, feet[1] - 3.6 * scale)), int(min(HEIGHT, feet[1] + 0.9 * scale))
        found = None
        if x1 - x0 > 40 and y1 - y0 > 40:
            result = self.fine.predict(g[y0:y1, x0:x1], imgsz=640, classes=[0], device=tracker.default_device(), verbose=False, retina_masks=True, conf=0.2)[0]
            if result.masks is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                bottoms = np.c_[(boxes[:, 0] + boxes[:, 2]) / 2 + x0, boxes[:, 3] + y0]
                distance = np.hypot(*(bottoms - feet).T)
                k = int(np.argmin(distance))
                if distance[k] < 1.5 * scale:
                    found = (x0, y0, result.masks.data[k].cpu().numpy() > 0.5)
        self.masks[frame] = found
        return found

    def effects(self, g: np.ndarray, shot: dict, moment: float, tau: float, m: np.ndarray, tall: float, people: np.ndarray) -> None:
        """What is drawn in the picture: the replay's drained colours and cut-out, the marks on the court, the ball's trail."""
        to = lambda p: (m[:, :2] @ np.asarray(p, float) + m[:, 2]).astype(int)  # noqa: E731
        kind, c = shot["kind"], self.contact(shot)
        t = self.touch_time(shot) if kind == "replay" else c["t"]
        since = moment - t
        frozen = kind == "replay" and REPLAY_PRE <= tau < REPLAY_PRE + FREEZE
        feet_px, ppm = self.hero_px(moment)
        hx, hy = self.hero_at(moment)
        scale = ppm * HEIGHT / tall
        feet = to(feet_px)
        mine = self.cut_out(g, int(round(moment * FPS)), feet, scale) if kind == "replay" else None
        if kind == "replay":
            amount = float(ease(REPLAY_PRE - 0.5, REPLAY_PRE, tau) * (1 - ease(REPLAY_PRE + FREEZE, REPLAY_PRE + FREEZE + 0.5, tau)))
            if amount > 0:
                gray = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY)
                drained = (cv2.merge([gray, gray, gray]) * np.array([0.62, 0.58, 0.55]) * amount + g * (1 - amount)).astype(np.uint8)
                if mine is not None:
                    x0, y0, mask = mine
                    h, w = mask.shape
                    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.2)[..., None]
                    drained[y0 : y0 + h, x0 : x0 + w] = (drained[y0 : y0 + h, x0 : x0 + w] * (1 - soft) + g[y0 : y0 + h, x0 : x0 + w] * soft).astype(np.uint8)
                g[:] = drained
        # What is painted on the court stays under the players.
        floor = np.zeros_like(g)

        def on_court(points: np.ndarray, closed_line: bool, color, thick: int) -> None:
            path = (m[:, :2] @ self.cal.to_image(points).T).T + m[:, 2]
            cv2.polylines(floor, [path.astype(np.int32)], closed_line, color, thick, cv2.LINE_AA)

        angles = np.linspace(0, 2 * np.pi, 40)
        on_court(np.c_[hx + 0.62 * np.cos(angles), hy + 0.62 * np.sin(angles)], True, GOLD, 4)
        following = next((q for q in self.page["contacts"][c["i"] + 1 : c["i"] + 6] if q["rally"] == c["rally"] and q["t"] > t), None)
        start = self.places.get(c["i"])
        if following and start and following.get("x") is not None and since > 0:
            u = min(1.0, since / max(following["t"] - t, 0.05))
            a, b = np.array(start[:2], float), np.array([following["x"], following["y"]], float)
            on_court(np.linspace(a, a + (b - a) * u, 16), False, GOLD if c.get("result") == "point" else WHITE, 4)
            if u >= 1 and following["type"] == "floor":
                age = moment - following["t"]
                for k in range(3):
                    r = 0.2 + 2.0 * max(0, age - 0.12 * k)
                    if age > 0.12 * k and r < 2.2:
                        on_court(b + np.c_[r * np.cos(angles), r * np.sin(angles)], True, GOLD, 3)
        painted = floor.any(2) & ~people
        g[painted] = (g[painted] * 0.15 + floor[painted] * 0.85).astype(np.uint8)
        if mine is not None:
            self.glow(g, mine, GOLD if frozen else (60, 170, 255), 0.8 if frozen else 0.45)
        self.comet(g, moment, to, ppm * HEIGHT / tall)
        hit = self.ball.get(int(round(t * FPS)))
        if hit and -0.02 <= since <= 0.35 and not frozen:
            u = (since + 0.02) / 0.37
            self.ring_light(g, to(hit), int(12 + 70 * u), WHITE, max(1, int(5 * (1 - u))), 1 - u)
        if frozen and hit:
            u = (tau - REPLAY_PRE) / FREEZE
            for k in range(2):
                q = u * 1.4 - k * 0.3
                if 0 < q < 1:
                    self.ring_light(g, to(hit), int(14 + 80 * q), GOLD, max(1, int(4 * (1 - q))), 1.0)
        if kind == "replay" and c.get("reach") and hit and start and tau >= REPLAY_PRE - 0.15:
            u = float(ease(REPLAY_PRE - 0.15, REPLAY_PRE + 0.2, tau))
            foot, top = to(self.cal.to_image(np.array([start[:2]], float))[0]), to(hit)
            cv2.line(g, tuple(int(v) for v in foot), tuple(int(v) for v in foot + (top - foot) * u), GOLD, 4, cv2.LINE_AA)
            for k in range(1, 7):
                if k / 6 <= u:
                    q = foot + (top - foot) * (k / 6)
                    cv2.line(g, (int(q[0]) - 9, int(q[1])), (int(q[0]) + 9, int(q[1])), GOLD, 2, cv2.LINE_AA)

    @staticmethod
    def glow(g: np.ndarray, cut: tuple, color, strength: float) -> None:
        """A soft light around the player cut out, and a fine edge."""
        x0, y0, mask = cut
        pad = 40
        h, w = mask.shape
        box = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
        box[pad : pad + h, pad : pad + w] = mask.astype(np.uint8) * 255
        inside = box > 0
        soft = cv2.GaussianBlur(cv2.dilate(box, np.ones((7, 7), np.uint8)), (0, 0), 10) / 255.0
        soft[inside] = 0
        add_light(g, (soft[..., None] * np.array(color) * strength).astype(np.int16), x0 - pad, y0 - pad)
        edge = (cv2.dilate(box, np.ones((3, 3), np.uint8)) > 0) & ~inside
        ys, xs = np.nonzero(edge)
        ys, xs = ys + y0 - pad, xs + x0 - pad
        keep = (ys >= 0) & (ys < HEIGHT) & (xs >= 0) & (xs < WIDTH)
        g[ys[keep], xs[keep]] = (g[ys[keep], xs[keep]] * 0.55 + np.array(WHITE) * 0.45).astype(np.uint8)

    @staticmethod
    def ring_light(g: np.ndarray, centre: np.ndarray, radius: int, color, thick: int, strength: float) -> None:
        size = radius + 12
        layer = np.zeros((2 * size, 2 * size, 3), np.uint8)
        cv2.circle(layer, (size, size), radius, color, thick, cv2.LINE_AA)
        add_light(g, (cv2.GaussianBlur(layer, (0, 0), 1.2) * strength).astype(np.int16), int(centre[0]) - size, int(centre[1]) - size)

    def comet(self, g: np.ndarray, moment: float, to: Callable, ppm: float) -> None:
        """The ball's trail: as wide as the ball at most, whiter towards it."""
        frame, tail, last = int(round(moment * FPS)), [], None
        for q in range(frame - 9, frame + 1):
            b = self.ball.get(q)
            if b and (last is None or np.hypot(b[0] - last[0], b[1] - last[1]) < 170):
                tail.append(to(b))
                last = b
        if len(tail) < 2:
            return
        width = 0.21 * ppm
        pad = int(max(12, 1.2 * width))
        points = np.array(tail)
        x0, y0 = points.min(0) - pad
        w, h = points.max(0) - points.min(0) + 2 * pad
        if w > 2 * WIDTH or h > 2 * HEIGHT:
            return
        layer = np.zeros((int(h), int(w), 3), np.uint8)
        for k in range(1, len(tail)):
            u = k / (len(tail) - 1)
            cv2.line(layer, tuple(int(v) for v in tail[k - 1] - [x0, y0]), tuple(int(v) for v in tail[k] - [x0, y0]), (int(170 + 70 * u), int(205 + 40 * u), 255), max(1, int((0.08 + 0.24 * u) * width)), cv2.LINE_AA)
        bloom = cv2.GaussianBlur(layer, (0, 0), max(1.5, 0.12 * width))
        add_light(g, (bloom * 0.3).astype(np.int16) + layer // 4, int(x0), int(y0))

    def telemetry(self, g: np.ndarray, shot: dict, tau: float) -> None:
        """The numbers slam in as the replay freezes on the touch."""
        begin = REPLAY_PRE - 0.1
        if tau < begin or tau >= shot["length"] - 0.05:
            return
        c = self.contact(shot)
        x, y, count = int(WIDTH - 380 + (1 - out_back((tau - begin) / 0.3)) * 420), 205, float(ease(begin, begin + 0.55, tau))
        if c.get("speed") is not None:
            label, value, unit = "VITESSE", str(int(round(c["speed"] * count))), "KM/H"
        elif c.get("reach"):
            label, value, unit = "HAUTEUR DE FRAPPE", f"{c['reach'] * count:.2f}".replace(".", ","), "M"
        elif self.film.get("kind") == "highlights":
            touches = sum(q[2] in TOUCHES for q in self.film["rallies"][str(shot["rally"])]["touches"])
            if touches < LONG_RALLY:
                return
            label, value, unit = "ÉCHANGE", str(int(round(touches * count))), "TOUCHES"
        elif c.get("result") == "point":
            rank = sum(1 for q in self.page["contacts"] if q.get("person") in self.film["persons"] and q.get("result") == "point" and q["t"] <= c["t"])
            label, value, unit = "POINT", str(int(round(rank * count))), f"SUR {self.film['points']}"
        else:
            return
        slant(g, x, y, 340, 170, INK, 0.86)
        slant(g, x, y, 8, 170, RED)
        write(g, label, x + 34, y + 38, 26, self.cond, GREY)
        write(g, value, x + 32, y + 138, 104, self.din, GOLD if count >= 1 else WHITE)
        write(g, unit, x + 320 - text_width(unit, self.cond, 34), y + 138, 34, self.cond)
        if c.get("speed") is not None:
            cv2.rectangle(g, (x + 30, y + 150), (x + 300, y + 158), (70, 70, 70), -1)
            cv2.rectangle(g, (x + 30, y + 150), (x + 30 + int(270 * count * min(1, c["speed"] / 110)), y + 158), GOLD, -1)

    def point_at(self, shot: dict) -> float | None:
        """When a shot's point is won: at its touch, or in the match's film at the end of a rally another touch ended."""
        c = self.contact(shot)
        if c.get("result") == "point":
            return c["t"]
        return self.film["rallies"][str(shot["rally"])]["end"] if self.film.get("kind") == "highlights" else None

    def tower(self, g: np.ndarray, shot: dict, tau: float, moment: float) -> None:
        """The score, as a timing tower, moving as a point lands."""
        rally = self.film["rallies"][str(shot["rally"])]
        before, after = rally["before"], rally["score"] or rally["before"]
        at = self.point_at(shot)
        landed = shot["kind"] == "live" and at is not None and moment - at > 0.35
        shown = after if landed else before
        off = int((1 - out_back(tau / 0.3)) * -520)
        teams = self.film["teams"] or ["", ""]
        slant(g, 30 + off, 62, 200, 54, INK, 0.9)
        write(g, teams[0], 46 + off, 100, 26, self.cond, widest=175)
        for k, x in enumerate((226, 284)):
            moved = landed and after[k] != before[k]
            slant(g, x + off, 62, 62, 54, GOLD if moved else (60, 60, 60))
            write(g, str(shown[k]), x + 34 + off, 102, 38, self.din, INK if moved else WHITE, center=True)
        slant(g, 342 + off, 62, 200, 54, INK, 0.9)
        write(g, teams[1], 362 + off, 100, 26, self.cond, widest=165)
        write(g, f"SET {rally['set']}", 556 + off, 100, 24, self.cond, GREY)

    def caption(self, g: np.ndarray, shot: dict, tau: float) -> None:
        off, top = int((1 - out_back((tau - 0.05) / 0.35)) * -760), HEIGHT - 232
        who = self.who(shot)
        c, jersey = self.contact(shot), who["jersey"]
        if jersey is not None:
            slant(g, 30 + off, top, 104, 118, RED)
            write(g, str(jersey), 86 + off, top + 86, 70, self.din, center=True)
            x = 138
        else:
            slant(g, 30 + off, top, 16, 118, RED)
            x = 50
        slant(g, x + off, top, 720 - x - 60, 118, INK, 0.88)
        write(g, who["name"].upper(), x + 26 + off, top + 58, 48, self.italic, widest=720 - x - 110)
        action = self.words["actions"].get(c["type"], {}).get(c.get("result"), c["type"])
        write(g, action.upper(), x + 24 + off, top + 98, 28, self.cond, GOLD, widest=720 - x - 110)
        if shot["kind"] == "replay":
            tag = self.words["broadcast"]["replayTag"].upper()
            wide = text_width(tag, self.italic, 30)
            left = int(30 + (1 - out_back(tau / 0.25)) * -300)
            slant(g, left, 128, wide + 88, 44, RED)
            write(g, tag, left + 24, 160, 30, self.italic)
            for k in range(3):
                at = left + 34 + wide + k * 11
                cv2.polylines(g, [np.array([[at, 138], [at + 8, 150], [at, 162]], np.int32)], False, WHITE if k == int(tau * 6) % 3 else (150, 150, 200), 3, cv2.LINE_AA)

    def banner(self, g: np.ndarray, shot: dict, moment: float) -> None:
        """A won point."""
        at = self.point_at(shot)
        if shot["kind"] != "live" or at is None or moment - at < 0.35:
            return
        age = moment - at - 0.35
        left = int(30 - float(ease(1.0, 1.2, age)) * 560)
        slant(g, left, HEIGHT - 310, int(400 * out_back(age / 0.22)), 66, GOLD, 1.0, 16)
        if age > 0.14:
            write(g, "POINT !", left + 28, HEIGHT - 262, 48, self.italic, INK)

    def stinger(self, g: np.ndarray, film_t: float) -> None:
        """Bars crossing the picture over a cut, hiding it."""
        for cut in self.cuts:
            u = (film_t - cut) / 0.24
            if -1 < u < 1:
                # As wide as the picture asks.
                f = max(1.0, WIDTH / 720)
                for k, (color, wide) in enumerate(((INK, 900 * f), (RED, 620 * f), (WHITE, 90 * f))):
                    x = -1100 * f + (u + 1) * 1.05 * (WIDTH + 1500 * f) - k * 140 * f
                    cv2.fillPoly(g, [np.array([[x + 300, 0], [x + wide + 300, 0], [x + wide - 300, HEIGHT], [x - 300, HEIGHT]], np.int32)], color, cv2.LINE_AA)

    def title_card(self, g: np.ndarray, tau: float) -> None:
        g[:] = (g * 0.42).astype(np.uint8)
        # Laid out for the upright picture, centred in any other.
        dx, dy = (WIDTH - 720) // 2, (HEIGHT - 1280) // 2
        off, off2 = int((1 - out_back((tau - 0.1) / 0.4)) * -(760 + dx)), int((1 - out_back((tau - 0.35) / 0.4)) * (760 + dx))
        match_film = self.film.get("kind") == "highlights"
        of = "d'" if re.match(r"[aeiouyhàâäéèêëîïôöùûü]", self.name, re.I) else "de"
        slant(g, dx + 20 + off, dy + 520, 680, 150, RED, 1.0, 30)
        write(g, "LE RÉSUMÉ DU MATCH" if match_film else f"LE FILM {of}".upper(), dx + 50 + off, dy + 505, 40, self.cond)
        title = " - ".join(self.film["teams"]) if match_film else self.name
        write(g, title.upper(), dx + 360 + off, dy + 634, 112, self.italic, widest=620, center=True)
        slant(g, dx + 60 + off2, dy + 680, 620, 50, INK, 1.0, 16)
        write(g, self.below, dx + 360 + off2, dy + 716, 28, self.cond, widest=580, center=True)

    def end_card(self, g: np.ndarray, tau: float) -> None:
        g[:] = (g * 0.28).astype(np.uint8)
        dx, dy = (WIDTH - 720) // 2, min(0, (HEIGHT - 1280) // 2 - 80)
        off = int((1 - out_back(tau / 0.35)) * -(760 + dx))
        slant(g, dx + 20 + off, dy + 300, 680, 130, RED, 1.0, 30)
        film = self.film
        if film.get("kind") == "highlights":
            title = f"{film['teams'][0]}  {film['won'][0]}-{film['won'][1]}  {film['teams'][1]}"
            rows = [("SETS", None, "   ".join(film["sets"])), ("ÉCHANGE LE PLUS LONG", film["longest"], " TOUCHES")]
            if film["fastest"]:
                rows.append(("SERVICE LE PLUS RAPIDE", film["fastest"], f" KM/H · {film['fastestName'].upper()}"))
        else:
            title = self.name
            rows = [("POINTS", film["points"], ""), ("BALLONS TOUCHÉS", film["touches"], "")]
            if film["fastest"]:
                rows.append(("SERVICE LE PLUS RAPIDE", film["fastest"], " KM/H"))
        write(g, title.upper(), dx + 360 + off, dy + 398, 96, self.italic, widest=620, center=True)
        for k, (label, value, unit) in enumerate(rows):
            begin = 0.35 + k * 0.3
            shift, y, count = int((1 - out_back((tau - begin) / 0.3)) * (760 + dx)), dy + 470 + k * 140, float(ease(begin, begin + 0.7, tau))
            slant(g, dx + 40 + shift, y, 640, 122, INK, 0.92)
            slant(g, dx + 40 + shift, y, 8, 122, GOLD)
            write(g, label, dx + 72 + shift, y + 42, 26, self.cond, GREY, widest=560)
            shown = unit if value is None else f"{int(round(value * count))}{unit}"
            write(g, shown, dx + 70 + shift, y + 106, 62, self.din, GOLD if count >= 1 else WHITE, widest=590)
        write(g, self.below, WIDTH // 2, HEIGHT - 120, 28, self.cond, (210, 210, 210), widest=620, center=True)

    def sound(self) -> np.ndarray:
        """The hall on the live shots, the commentary over it, a whoosh on each cut and a hit on each freeze."""
        rate, film = 48000, self.film
        total = int(film["length"] * rate) + rate
        hall, voice, marks_fx = (np.zeros((total, 2), np.float32) for _ in range(3))

        def read(args: list[str]) -> np.ndarray:
            raw = subprocess.run(["ffmpeg", "-v", "error", *args, "-f", "f32le", "-ac", "2", "-ar", str(rate), "-"], capture_output=True).stdout
            return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()

        def put(track: np.ndarray, at: float, clip: np.ndarray) -> None:
            k = max(0, int(at * rate))
            room = min(len(clip), total - k)
            track[k : k + room] += clip[:room]

        n = int(0.5 * rate)
        t = np.arange(n) / rate
        hit = (np.sin(2 * np.pi * (70 * t - 25 * t**2)) * np.exp(-t * 9) * 0.75 + np.random.default_rng(5).standard_normal(n) * np.exp(-t * 45) * 0.18).astype(np.float32)
        for shot in film["shots"]:
            if shot["kind"] == "live":
                clip = read(["-ss", f"{self.times[round(shot['from'] * FPS)]:.3f}", "-i", str(self.video), "-t", f"{shot['length']:.3f}", "-vn"])
                ramp = min(len(clip) // 2, int(0.06 * rate))
                clip[:ramp] *= np.linspace(0, 1, ramp)[:, None]
                clip[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
                put(hall, shot["start"], clip)
            elif shot["kind"] == "replay":
                put(marks_fx, shot["start"] + REPLAY_PRE, np.c_[hit, hit])
        for at in self.impacts:
            put(marks_fx, at, np.c_[hit, hit])
        for line in film["lines"]:
            put(voice, line["at"], read(["-i", str(self.match / "review" / "voice" / line["file"])]))
        n = int(0.55 * rate)
        noise = np.random.default_rng(3).standard_normal(n)
        bend = np.sin(np.linspace(0, np.pi, n)) ** 2
        rough = np.zeros(n)
        y = 0.0
        for k in range(n):
            y += (0.02 + 0.35 * bend[k]) * (noise[k] - y)
            rough[k] = y
        whoosh = (rough * bend * 0.5).astype(np.float32)
        for cut in self.cuts:
            put(marks_fx, cut - 0.27, np.c_[whoosh, whoosh])
        level = np.convolve(np.abs(voice).max(1), np.ones(rate // 5) / (rate // 5), "same")
        return np.clip(hall * 0.8 * (1 - 0.6 * np.clip(level * 20, 0, 1))[:, None] + voice + marks_fx * 0.55, -1, 1)[: int(film["length"] * rate)]


def children(match: Path, video: Path, court: Path) -> list[str]:
    return [sys.executable, "-m", "volleyball_stats.film", str(match), "--video", str(video), "--court", str(court)]


def build(match: Path, video: Path, court: Path, staged: Callable[[str | None], None] = lambda _: None, names: list[str] | None = None, kind: str | None = None) -> list[str]:
    """Makes the films missing or out of date, or those `names`, of `kind` alone if given, each in its own process so that the review
    stays free, the ball's search first; a film made is kept even if a later one fails. Returns those made."""
    page = read_page(match / "review")
    films = plan(page, match / "review", tracking_stamp(match)) if page else {}
    made = manifest(match)
    folder = match / FILMS
    folder.mkdir(exist_ok=True)
    todo = [n for n, f in films.items() if kind in (None, kind_of(n)) and (n in names if names else made.get(n, {}).get("hash") != f["hash"] or not (folder / f["file"]).exists())]
    if not todo:
        return []
    staged("filmsBall")
    subprocess.run([*children(match, video, court), "--search", ",".join(todo)], check=True)
    staged("filmsRender")

    def one(name: str) -> str:
        subprocess.run([*children(match, video, court), "--make", name], check=True)
        return name

    failed = None
    with ThreadPoolExecutor(WORKERS) as pool:
        for job in [pool.submit(one, n) for n in todo]:
            try:
                name = job.result()
            except subprocess.CalledProcessError as error:
                failed = error
                continue
            made[name] = {"hash": films[name]["hash"], "file": films[name]["file"], "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            files.write_text(folder / MANIFEST, json.dumps(made, indent=1, ensure_ascii=False) + "\n")
    # Films of players no longer in the match go.
    wanted = {f["file"] for f in films.values()}
    for path in folder.glob("*.mp4"):
        if path.name not in wanted:
            path.unlink()
    if failed:
        raise failed
    return todo


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the players' films, those that changed.")
    parser.add_argument("match", type=Path)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True)
    parser.add_argument("--names", help="Only these players, by name, comma separated, even if up to date")
    parser.add_argument("--search", help=argparse.SUPPRESS)
    parser.add_argument("--make", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.search or args.make:
        page = read_page(args.match / "review")
        films = plan(page, args.match / "review", tracking_stamp(args.match))
        if args.search:
            search_ball(args.match, args.video, args.court, {n: films[n] for n in args.search.split(",")}, page)
        else:
            film = films[args.make]
            target = args.match / FILMS / film["file"]
            draft = target.with_name(f"draft-{target.name}")
            Maker(args.match, args.video, args.court, page).make(film, draft)
            draft.replace(target)
        return
    started = time.time()
    made = build(args.match, args.video, args.court, print, args.names.split(",") if args.names else None)
    print(f"{len(made)} films in {time.time() - started:.0f} s: {', '.join(made)}")


if __name__ == "__main__":
    main()
