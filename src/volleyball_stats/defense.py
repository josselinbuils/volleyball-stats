"""Where the defenders stand when the other team attacks, against a defence system: the perimeter the owner's team plays,
the middle up, the rotation, or the spots learned from the matches' attacks.

Places are in the defenders' half: metres from the net, then metres toward their right as they face the net."""

import functools
import itertools

import numpy as np

MODES = ("perimeter", "up", "rotation", "learned")
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
MIRRORED = {4: 2, 2: 4, 5: 1, 1: 5}
# Learning: a dug ball would have landed this much further along its flight; a ball counts the more the nearer a spot,
# on a bell this wide (held out, each match on the other's spots: 70% and 69% of the balls within CATCH_M, against 66% and
# 55% counting those within CATCH_M); spots are looked for on this grid, off the net, from this many balls in each kind
# of attack. A defender gets to a ball this far from them in time.
DUG_M, SPREAD_M, CATCH_M = 1.0, 1.0, 1.5
GRID = np.stack(np.meshgrid(np.arange(1.5, 9.01, 0.25), np.arange(-4.5, 4.51, 0.25), indexing="ij"), -1).reshape(-1, 2)
LEARN_FROM = 30

Spot = tuple[float, float, int]


def block(across: float, double: bool) -> list[Spot]:
    """The blockers' spots in front of an attack `across` metres toward the defenders' right, `across` >= 0: a single
    block on the right by 2 (by 3 through the middle), a double one by 3 and 2."""
    at = float(min(across, REACH_M))
    if double:
        centre = min(at, REACH_M - PAIR_M / 2)
        return [(NET_M, centre - PAIR_M / 2, 3), (NET_M, centre + PAIR_M / 2, 2)]
    return [(NET_M, at, 3 if across <= MIDDLE_M else 2)]


def layout(mode: str, across: float, double: bool, learned: dict | None = None) -> list[Spot]:
    """The six spots with their positions in `mode` for an attack `across` metres toward the defenders' right."""
    if across < 0:
        return [(depth, -x, MIRRORED.get(p, p)) for depth, x, p in layout(mode, -across, double, learned)]
    middle = across <= MIDDLE_M
    front = block(across, double)
    if mode == "learned":
        # The blockers keep their positions; the front ones left take the spots nearest the net, left to right.
        floor = sorted(learned["middle" if middle else "side"][str(6 - len(front))], key=lambda s: s[0])
        free = [p for p in (4, 3, 2) if p not in {b[2] for b in front}]
        rows = ((floor[: len(free)], free), (floor[len(free) :], (5, 6, 1)))
        return front + [(depth, x, position) for row, positions in rows for (depth, x), position in zip(sorted(row, key=lambda s: s[1]), positions)]
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


def balls(contacts: list[dict]) -> list[tuple[float, float, float]]:
    """Where the attacks went, as (the attack's across, depth, across) in the defenders' frame (`flight`), a dug ball
    DUG_M further along its flight."""
    out = []
    for k, c in enumerate(contacts):
        if c["type"] != "attack" or c.get("x") is None or c.get("y") is None:
            continue
        start, end, played = flight(contacts, k)
        if end is None:
            continue
        a, b = np.array(start), np.array(end)
        if played:
            b = b + DUG_M * (b - a) / max(np.hypot(*(b - a)), 1e-9)
        out.append((float(a[1]), float(b[0]), float(b[1])))
    return out


def best(found: np.ndarray, k: int) -> list[tuple[float, float]]:
    """`k` spots on GRID nearest the most of the `found` balls, each ball counting the more the nearer its nearest spot
    (a bell SPREAD_M wide): picked one at a time, then each moved while that gains."""
    gain = np.exp(-0.5 * (np.hypot(*(found[:, None] - GRID[None]).transpose(2, 0, 1)) / SPREAD_M) ** 2)

    def pick(others: list[int]) -> int:
        return int(np.argmax((np.maximum(gain[:, others].max(1)[:, None], gain) if others else gain).sum(0)))

    chosen: list[int] = []
    for _ in range(k):
        chosen.append(pick(chosen))
    moved = True
    while moved:
        moved = False
        for i in range(k):
            others = chosen[:i] + chosen[i + 1 :]
            better = pick(others)
            if gain[:, others + [better]].max(1).sum() > gain[:, chosen].max(1).sum() + 1e-9:
                chosen[i], moved = better, True
    return sorted((round(float(GRID[c][0]), 2), round(float(GRID[c][1]), 2)) for c in chosen)


def learn(found: list[tuple[float, float, float]]) -> dict | None:
    """The floor defenders' spots from where the attacks went, for an attack on the defenders' right and one through the
    middle (made the same on both sides), 4 of them under a double block, 5 under a single one; None from too few balls."""
    side = np.array([(depth, x if across >= 0 else -x) for across, depth, x in found if abs(across) > MIDDLE_M]).reshape(-1, 2)
    middle = np.array([(depth, x) for across, depth, x in found if abs(across) <= MIDDLE_M]).reshape(-1, 2)
    if len(side) < LEARN_FROM or len(middle) < LEARN_FROM:
        return None
    middle = np.concatenate([middle, middle * [1, -1]])
    return {name: {str(k): best(group, k) for k in (4, 5)} for name, group in (("side", side), ("middle", middle))}
