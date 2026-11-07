"""Where the defenders stand when the other team attacks, against a defence system: the perimeter the owner's team plays,
Laëticia's version of it, the middle up or the rotation.

Places are in the defenders' half: metres from the net, then metres toward their right as they face the net."""

import functools
import itertools

import numpy as np

MODES = ("perimeter", "laeticia", "up", "rotation")
# The positions in court order: the front row left to right, then the back row.
POSITIONS = (4, 3, 2, 5, 6, 1)
# Where an attack comes from on each side, as the page draws it: metres toward the defenders' right.
ATTACKERS = {"left": -3.0, "middle": 0.0, "right": 3.0}
# A player this near the net at the hit blocks: two or more make a double block.
BLOCK_M = 1.2
# An attack this near the court's long axis comes through the middle.
MIDDLE_M = 1.5
# The blockers' feet off the net, a double block's two blockers apart, and how far inside the sidelines they block.
NET_M, PAIR_M, REACH_M = 0.5, 0.9, 4.0
# The spots off the net for an attack on the defenders' right (mirrored for one on their left), from AVCA's descriptions,
# distances approximate. Front: the off-blocker on the 3 m line 1 m inside the sideline; under a single block, the front
# player who does not block covers the tip behind it, or the middle of the 3 m line where another player covers the tip.
OFF = (3.0, -3.5, 4)
TIP, SHORT = (3.0, 1.5, 3), (3.5, 0.0, 3)
# Back: the perimeter's corners 2 m inside the sidelines 6 m off the net and 6 at 7 m (the owner's, 7 Nov: the textbook's
# corners 1 m inside left the middle open at this level); the middle up's corners near the end line, 6 behind the block;
# the rotation's 1 up for the tip down the line, 6 deep on the line, 5 deep across. A middle attack's rotation is the perimeter.
BACK = {
    "perimeter": [(6.0, -2.5, 5), (7.0, 0.0, 6), (6.0, 2.5, 1)],
    "up": [(8.0, -3.0, 5), (3.0, 2.0, 6), (8.0, 3.0, 1)],
    "rotation": [(7.0, -2.0, 5), (7.5, 3.0, 6), (3.5, 3.0, 1)],
}
# Laëticia's, a teammate's diagrams (7 Nov, read off photos to about 0.3 m), for an attack on the defenders' right: the
# block this far inside the attacker, the free front players in the middle short (behind a single block on the line side),
# the line digger deep on the line, the cross digger forward, 6 deep toward the cross. The middle attack's spots also
# serve under a double block, which the diagrams do not show.
INSIDE = {True: 1.2, False: 0.8}
LAETICIA = {
    "double": [(2.4, -0.4, 4), (4.85, -2.4, 5), (7.5, -1.0, 6), (6.05, 3.9, 1)],
    "single": [(2.5, 3.6, 3), (1.8, -1.2, 4), (5.5, -2.7, 5), (7.3, -0.7, 6), (7.1, 3.8, 1)],
    "middle": [(2.8, -1.8, 4), (2.8, 1.8, 2), (5.75, -2.45, 5), (7.7, 0.0, 6), (5.75, 2.45, 1)],
}
MIRRORED = {4: 2, 2: 4, 5: 1, 1: 5}
Spot = tuple[float, float, int]


def block(across: float, double: bool) -> list[Spot]:
    """The blockers' spots in front of an attack `across` metres toward the defenders' right, `across` >= 0: a single
    block on the right by 2 (by 3 through the middle), a double one by 3 and 2."""
    at = float(min(across, REACH_M))
    if double:
        centre = min(at, REACH_M - PAIR_M / 2)
        return [(NET_M, centre - PAIR_M / 2, 3), (NET_M, centre + PAIR_M / 2, 2)]
    return [(NET_M, at, 3 if across <= MIDDLE_M else 2)]


def layout(mode: str, across: float, double: bool) -> list[Spot]:
    """The six spots with their positions in `mode` for an attack `across` metres toward the defenders' right."""
    if across < 0:
        return [(depth, -x, MIRRORED.get(p, p)) for depth, x, p in layout(mode, -across, double)]
    middle = across <= MIDDLE_M
    front = block(across, double)
    if mode == "laeticia":
        if middle:
            return front + [s for s in LAETICIA["middle"] if s[2] not in {b[2] for b in front}]
        return [(depth, x - INSIDE[double], p) for depth, x, p in front] + LAETICIA["double" if double else "single"]
    if middle and not double:
        front += [OFF, (OFF[0], -OFF[1], 2)]
    else:
        front += [OFF] + ([] if double else [TIP if mode == "perimeter" else SHORT])
    return front + BACK["perimeter" if middle and mode == "rotation" else mode]


@functools.cache
def orders(n: int, m: int) -> np.ndarray:
    """Every way to pair n defenders with m spots: row k gives each defender's spot (n <= m), else each spot's defender."""
    return np.array(list(itertools.permutations(range(max(n, m)), min(n, m))))


def doubled(defenders: dict[int, tuple[float, float]]) -> bool:
    """Whether two players or more stand near enough the net to block."""
    return sum(depth <= BLOCK_M for depth, _ in defenders.values()) >= 2


def assign(spots: list[Spot], defenders: dict[int, tuple[float, float]]) -> dict[int, Spot]:
    """Each defender's spot among `spots`, by the least total distance; a defender left over has none."""
    if not defenders:
        return {}
    people = list(defenders)
    places, ends = np.array([defenders[p] for p in people]), np.array([(depth, x) for depth, x, _ in spots])
    far = np.hypot(*(places[:, None] - ends[None]).transpose(2, 0, 1))
    n, m = far.shape
    # ponytail: every pairing tried at once, 20160 for 8 defenders; Hungarian if crowds ever come.
    ways = orders(n, m)
    if n <= m:
        best = ways[far[np.arange(n), ways].sum(1).argmin()]
        return {people[i]: spots[j] for i, j in enumerate(best)}
    best = ways[far[ways, np.arange(m)].sum(1).argmin()]
    return {people[i]: spots[j] for j, i in enumerate(best)}


def flight(contacts: list[dict], k: int) -> tuple[tuple[float, float], tuple[float, float] | None, bool]:
    """Attack `k`'s place and where it went in the defenders' frame: the defenders' first touch but a block, or where it
    landed untouched (None for an attack missed or whose ball is not seen there), and whether a defender played it."""
    c = contacts[k]
    sign = 1 if c["side"] == "left" else -1
    start = (sign * c["x"], -sign * c["y"])
    after = next((n for n in contacts[k + 1 :] if n["rally"] == c["rally"]), None)
    if c["result"] == "error" or not after or after["type"] in ("block", "fault", "net") or after.get("x") is None or after.get("y") is None:
        return start, None, False
    end = (sign * after["x"], -sign * after["y"])
    # Inside the court give or take a metre: a floor contact read off the picture can be anywhere.
    return start, (end if 0 < end[0] <= 10 and abs(end[1]) <= 5.5 else None), after["type"] != "floor"


def table() -> dict:
    """What the page draws: each side's attacker (`ATTACKERS`) and every system's six spots against it, for a single and a
    double block, flat [depth, across] in POSITIONS order."""
    spots = {
        mode: {side: {str(n): [round(v, 2) for p in POSITIONS for v in next(s[:2] for s in layout(mode, across, n == 2) if s[2] == p)] for n in (1, 2)} for side, across in ATTACKERS.items()}
        for mode in MODES
    }
    return {"attackers": ATTACKERS, "spots": spots}
