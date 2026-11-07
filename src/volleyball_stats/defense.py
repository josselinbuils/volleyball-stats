"""Where the floor defenders stand when the other team attacks, against the perimeter defence the owner's team plays.

Places are in the defenders' half: metres from the net, then metres toward their right as they face the net."""

import itertools

import numpy as np

# A player this near the net at the hit blocks.
BLOCK_M = 1.2
# An attack this near the court's long axis comes through the middle.
MIDDLE_M = 1.5
# The spots' kinds, as the page names them: a front player not blocking, zone 1 or 5, zone 6.
FRONT, CORNER, DEEP = 0, 1, 2
# The perimeter for an attack on the defenders' right, mirrored for one on their left: the off-blocker on the 3 m line,
# the corners 1 m inside the sidelines, zone 6 1 m off the end line. Under a single block, the front player who does
# not block covers the tip behind it. Through the middle, both outside front players drop off.
SIDE = [(3.0, -3.5, FRONT), (6.5, -3.5, CORNER), (8.0, 0.0, DEEP), (6.5, 3.5, CORNER)]
TIP = (3.0, 1.5, FRONT)
MIDDLE = [(3.0, -3.5, FRONT), (3.0, 3.5, FRONT), (6.5, -3.5, CORNER), (8.0, 0.0, DEEP), (6.5, 3.5, CORNER)]


def spots(across: float, blockers: int) -> list[tuple[float, float, int]]:
    """The floor defenders' spots for an attack `across` metres toward the defenders' right, under `blockers`."""
    if abs(across) <= MIDDLE_M:
        return MIDDLE
    side = 1 if across > 0 else -1
    return [(depth, side * x, kind) for depth, x, kind in SIDE + ([TIP] if blockers < 2 else [])]


def gaps(across: float, defenders: dict[int, tuple[float, float]]) -> dict[int, tuple[int, float, float]]:
    """Each floor defender's spot kind and way to it: metres back from the net, metres out toward the spot's sideline
    (toward the centre for zone 6's). The spots go to the defenders by the least total distance; a defender left over
    has none."""
    floor = [(person, place) for person, place in defenders.items() if place[0] > BLOCK_M]
    targets = spots(across, len(defenders) - len(floor))
    if not floor:
        return {}
    places, ends = np.array([place for _, place in floor]), np.array([(depth, x) for depth, x, _ in targets])
    far = np.hypot(*(places[:, None] - ends[None]).transpose(2, 0, 1))
    n, m = far.shape
    # ponytail: every assignment tried, at most 7 defenders for 5 spots (2520); Hungarian if crowds ever come.
    if n <= m:
        pairs = min((list(zip(range(n), p)) for p in itertools.permutations(range(m), n)), key=lambda ps: sum(far[i, j] for i, j in ps))
    else:
        pairs = min((list(zip(p, range(m))) for p in itertools.permutations(range(n), m)), key=lambda ps: sum(far[i, j] for i, j in ps))
    out = {}
    for i, j in pairs:
        (depth, x), (to_depth, to_x, kind) = places[i], targets[j]
        outward = np.sign(to_x) or np.sign(x)
        out[floor[i][0]] = (kind, float(to_depth - depth), float((to_x - x) * outward))
    return out
