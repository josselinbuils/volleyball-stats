"""Where the defenders stand when the other team attacks, against the perimeter defence the owner's team plays.

Places are in the defenders' half: metres from the net, then metres toward their right as they face the net."""

import functools
import itertools

import numpy as np

# A player this near the net at the hit blocks: two or more make a double block.
BLOCK_M = 1.2
# An attack this near the court's long axis comes through the middle.
MIDDLE_M = 1.5
# The blockers' feet off the net, a double block's two blockers apart, and how far inside the sidelines they block.
NET_M, PAIR_M, REACH_M = 0.5, 0.9, 4.0
# Off the net: the off-blocker on the 3 m line 1 m inside the sideline, away from the attack; under a single block on a
# side attack, the front player who does not block covers the tip behind it; the corners 1 m inside the sidelines, zone 6
# 1 m off the end line.
OFF, TIP = (3.0, 3.5), (3.0, 1.5)
BACK = [(6.5, -3.5, 5), (8.0, 0.0, 6), (6.5, 3.5, 1)]


def spots(across: float, double: bool) -> list[tuple[float, float, int]]:
    """The six spots with their positions for an attack `across` metres toward the defenders' right, under a single or
    a double block in front of it: the front ones 4, 3, 2 from left to right, then 5, 6, 1."""
    at = float(np.clip(across, -REACH_M, REACH_M))
    side = 1 if across >= 0 else -1
    if double:
        centre = float(np.clip(at, PAIR_M / 2 - REACH_M, REACH_M - PAIR_M / 2))
        front = [(NET_M, centre - PAIR_M / 2), (NET_M, centre + PAIR_M / 2), (OFF[0], -side * OFF[1])]
    elif abs(across) <= MIDDLE_M:
        front = [(NET_M, at), (OFF[0], -OFF[1]), (OFF[0], OFF[1])]
    else:
        front = [(NET_M, at), (TIP[0], side * TIP[1]), (OFF[0], -side * OFF[1])]
    return [(depth, x, position) for (depth, x), position in zip(sorted(front, key=lambda s: s[1]), (4, 3, 2))] + BACK


@functools.cache
def orders(n: int, m: int) -> np.ndarray:
    """Every way to pair n defenders with m spots: row k gives each defender's spot (n <= m), else each spot's defender."""
    return np.array(list(itertools.permutations(range(max(n, m)), min(n, m))))


def assign(across: float, defenders: dict[int, tuple[float, float]]) -> dict[int, tuple[float, float, int]]:
    """Each defender's spot (`spots`), the block single or double as the players near the net at the hit: the spots go
    to the defenders by the least total distance; a defender left over has none."""
    if not defenders:
        return {}
    targets = spots(across, sum(depth <= BLOCK_M for depth, _ in defenders.values()) >= 2)
    people = list(defenders)
    places, ends = np.array([defenders[p] for p in people]), np.array([(depth, x) for depth, x, _ in targets])
    far = np.hypot(*(places[:, None] - ends[None]).transpose(2, 0, 1))
    n, m = far.shape
    # ponytail: every pairing tried at once, 20160 for 8 defenders; Hungarian if crowds ever come.
    ways = orders(n, m)
    if n <= m:
        best = ways[far[np.arange(n), ways].sum(1).argmin()]
        return {people[i]: targets[j] for i, j in enumerate(best)}
    best = ways[far[ways, np.arange(m)].sum(1).argmin()]
    return {people[i]: targets[j] for j, i in enumerate(best)}
