"""Rally winners and the running score of each set, from how each rally ends.

A rally is lost by the side of the net the ball dies on. The last touch is the last contact that is
neither the floor nor the net. When the ball then lands (actions.py's floor contact), its floor
projection decides: in the court (the line is in) the side it lands on loses, out the side of the
last touch loses, at the foot of the net the side that sent it there. Without a landing, a ball that
crossed the net after the last touch and was not played again was not returned: the other side
loses; one that did not cross or died at the net loses for the side that sent it. A serve is a touch
like any other: into the net, out, or not returned (an ace). Faults the referee whistles (net
touch, foot fault, rotation) leave no trace in the ball's path.

The team serving the next rally won the previous one (the sideout rule). It only holds when the
next rally found is the next one played: a missed rally in between breaks it. `combine` weighs the
two; see benchmarks/points/README.md for the numbers.

    uv run python -m volleyball_stats.points outputs/VIDEO --court COURT_JSON

reads match.py's actions.csv, net.csv, rallies.csv and teams.json, and writes points.csv: each
rally's server, winner, reason and the score after it (team 1, team 2) in its set.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from volleyball_stats.actions import LEAD_S, Typed
from volleyball_stats.court import LENGTH, WIDTH, Calibration
from volleyball_stats.teams import parse_score

# Meters outside a line within which a landing still counts as in: the calibration's error on the
# floor. ponytail: one margin for the whole court; the far end, 20 px per metre, is the least sure.
IN_M = 0.3
# Court x (meters from the net) under which a contact is at the net: the camera stands in the net
# plane, so a ball at the net projects there whatever its height, and a landing there fell at the
# foot of the net.
NET_M = 1.0
# Seconds from a rally's end to the next serve under which no rally fits in between: twice the
# shortest gap between consecutive rallies of the tuning clips (12-51 s).
NEXT_S = 25.0
NOT_TOUCHES = ("floor", "net")


def other(side: str) -> str:
    return "right" if side == "left" else "left"


def side_lost(typed: list[Typed], crossings: list[int], calibration: Calibration | None) -> tuple[str | None, str]:
    """The side ("left", "right") that lost a rally from its typed contacts and net crossings, and
    why: "in", "out", "net" (did not cross, or died at the net) or "over" (crossed, not played
    again), prefixed "serve_" when the ball was last sent by the serve; (None, "unknown") without
    any touch.

    Trailing touches at the net are the ball hitting the net or a block: the side that sent the ball
    there loses. ponytail: a ball off the block and out without a landing seen counts for the
    blocker's side.
    """
    typed = sorted(typed)
    touches = [c for c in typed if c[3] not in NOT_TOUCHES]
    if not touches:
        return None, "unknown"
    court = {c[0]: calibration.to_court(np.array([c[1:3]], float))[0] for c in typed} if calibration else {}
    at_net = [c[0] in court and abs(court[c[0]][0]) <= NET_M for c in touches]
    sender = next((c for c, net in zip(reversed(touches), reversed(at_net)) if not net), touches[0])
    last = touches[-1]
    landing = next((c for c in typed if c[3] == "floor" and c[0] > last[0]), None)
    if landing and calibration is not None:
        x, y = court[landing[0]]
        if abs(x) <= NET_M:
            return sender[4], "serve_net" if sender[3] == "serve" else "net"
        prefix = "serve_" if last[3] == "serve" else ""
        if abs(x) <= LENGTH / 2 + IN_M and abs(y) <= WIDTH / 2 + IN_M:
            return landing[4], prefix + "in"
        return last[4], prefix + "out"
    prefix = "serve_" if sender[3] == "serve" else ""
    if at_net[-1]:
        return sender[4], prefix + "net"
    crossed = sum(last[0] < c for c in crossings) % 2
    return (other(last[4]), prefix + "over") if crossed else (last[4], prefix + "net")


def server_side(typed: list[Typed]) -> str | None:
    """Side of the rally's serve, None when no contact is typed serve."""
    return next((c[4] for c in sorted(typed) if c[3] == "serve"), None)


def team(side: str | None, left: int) -> int | None:
    """Team (1, 2) on `side` when `left` is on the left."""
    return None if side is None else left if side == "left" else 3 - left


def next_servers(servers: list[int | None], sets: list[int]) -> list[int | None]:
    """Per rally, the team serving the next rally of the same set; None for a set's last rally."""
    return [servers[k + 1] if k + 1 < len(servers) and sets[k + 1] == sets[k] else None for k in range(len(servers))]


def combine(ends: list[int | None], nexts: list[int | None], windows: list[tuple[int, int]], fps: float) -> list[tuple[int | None, int | None]]:
    """Per rally, its winner and the team credited with a rally missed between it and the next one.

    The end-of-rally winners (`ends`) and the next rallies' servers (`nexts`) mostly agree. When
    they differ and the next serve comes within NEXT_S, the end rule is wrong: the sideout rule
    decides. Later, a rally was likely missed in between: the end rule keeps this rally and the
    missed one goes to the next server. Without an end-of-rally winner, the next server.

    ponytail: one missed rally at most per gap, and only one the other team won; a gap's length
    could count them.
    """
    out: list[tuple[int | None, int | None]] = []
    for k, (end, following) in enumerate(zip(ends, nexts)):
        if following is None or end == following:
            out.append((end, None))
        elif end is None or (windows[k + 1][0] - windows[k][1]) / fps <= NEXT_S:
            out.append((following, None))
        else:
            out.append((end, following))
    return out


def running_score(found: list[tuple[int | None, int | None]], sets: list[int]) -> list[tuple[int, int]]:
    """Score (team 1, team 2) after each rally, from 0-0 at each set's first rally, from `combine`'s
    winners and missed rallies; a rally without a winner leaves it."""
    out, score, current, missed = [], [0, 0], None, None
    for (winner, after), number in zip(found, sets):
        if number != current:
            score, current = [0, 0], number
        elif missed:
            score[missed - 1] += 1
        if winner:
            score[winner - 1] += 1
        out.append((score[0], score[1]))
        missed = after
    return out


def set_drift(totals: dict[int, tuple[int, int]], given: list[str | None]) -> dict[int, tuple[int, int] | None]:
    """Per set, estimated (`totals`) minus given final score (teams.json's "25-21", team 1 first),
    team 1 then team 2; None when the set's score is not given."""
    out: dict[int, tuple[int, int] | None] = {}
    for number, (one, two) in totals.items():
        final = parse_score(given[number - 1] or "") if number <= len(given) else None
        a, b = map(int, final.split("-")) if final else (0, 0)
        out[number] = (one - a, two - b) if final else None
    return out


def by_rally(frames: list, windows: list[tuple[int, int]], lead: int) -> list[list]:
    """The items (frames, or tuples starting with their frame) of each rally window, started `lead`
    frames early as actions.classify's."""
    out: list[list] = [[] for _ in windows]
    for item in frames:
        frame = item[0] if isinstance(item, tuple) else item
        k = next((i for i, (s, e) in enumerate(windows) if s - lead <= frame <= e), None)
        if k is not None:
            out[k].append(item)
    return out


def points(typed: list[Typed], crossings: list[int], windows: list[tuple[int, int]], lefts: list[int], sets: list[int], fps: float, calibration: Calibration | None) -> list[dict]:
    """Per rally: its server, the end-of-rally winner and reason, the next rally's server, the
    winner, the team credited with a rally missed after it, its set and the score after it."""
    lead = round(LEAD_S * fps)
    rallies = by_rally(typed, windows, lead)
    lost = [side_lost(r, c, calibration) for r, c in zip(rallies, by_rally(crossings, windows, lead))]
    servers = [team(server_side(r), left) for r, left in zip(rallies, lefts)]
    ends = [team(None if side is None else other(side), left) for (side, _), left in zip(lost, lefts)]
    nexts = next_servers(servers, sets)
    found = combine(ends, nexts, windows, fps)
    out = []
    for (_, reason), server, end, following, (winner, missed), number, score in zip(lost, servers, ends, nexts, found, sets, running_score(found, sets)):
        if winner is None:
            reason = "unknown"
        elif winner != end:
            reason = "next_serve"
        out.append({"server": server, "end": end, "next": following, "winner": winner, "missed": missed, "reason": reason, "set": number, "score": score})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Find who won each rally and the running score.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO)")
    parser.add_argument("--court", type=Path, help="Court calibration JSON the match was run with")
    parser.add_argument("--fps", type=float, default=29.97, help="The video's frame rate")
    args = parser.parse_args()

    with open(args.match / "rallies.csv") as f:
        rows = list(csv.DictReader(f))
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rows]
    lefts = [int(r.get("left") or 1) for r in rows]
    sets = [int(r.get("set") or 1) for r in rows]
    with open(args.match / "actions.csv") as f:
        typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in csv.DictReader(f)]
    with open(args.match / "net.csv") as f:
        crossings = [int(r["frame"]) for r in csv.DictReader(f)]
    calibration = Calibration.load(args.court) if args.court else None
    found = points(typed, crossings, windows, lefts, sets, args.fps, calibration)
    with open(args.match / "points.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["start_frame", "end_frame", "set", "server", "winner", "reason", "score_1", "score_2"])
        for (start, end), p in zip(windows, found):
            out.writerow([start, end, p["set"], p["server"] or "", p["winner"] or "", p["reason"], *p["score"]])
    teams_path = args.match / "teams.json"
    given = json.loads(teams_path.read_text()).get("scores") or [] if teams_path.exists() else []
    totals = {p["set"]: p["score"] for p in found}
    for number, drift in set_drift(totals, given).items():
        one, two = totals[number]
        print(f"Set {number}: {one}-{two} estimated" + ("" if drift is None else f", {given[number - 1]} given, drift {drift[0]:+d} {drift[1]:+d}"))
    print(args.match / "points.csv")


if __name__ == "__main__":
    main()
