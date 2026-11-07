import numpy as np

from volleyball_stats import defense


def rounded(spots):
    return [(depth, round(x, 2), position) for depth, x, position in spots]


class TestLayout:
    def test_puts_the_block_in_front_of_the_attack_and_the_perimeter_off_the_net(self):
        # A single block on the right: the blocker 2, the off-blocker 4 left, 3 behind the block.
        assert defense.layout("perimeter", 3.0, False) == [(0.5, 3.0, 2), (3.0, -3.5, 4), (3.0, 1.5, 3), *defense.BACK["perimeter"]]
        # A double block on the left: 3 inside, 4 outside, the off-blocker 2 right.
        assert rounded(defense.layout("perimeter", -3.0, True)[:3]) == [(0.5, -2.55, 3), (0.5, -3.45, 4), (3.0, 3.5, 2)]
        # Through the middle under a single block, both outsides drop off.
        assert defense.layout("perimeter", 0.5, False)[:3] == [(0.5, 0.5, 3), (3.0, -3.5, 4), (3.0, 3.5, 2)]

    def test_keeps_the_block_inside_the_court(self):
        assert defense.layout("perimeter", 6.0, False)[0] == (0.5, 4.0, 2)
        assert rounded(defense.layout("perimeter", 6.0, True)[:2]) == [(0.5, 3.1, 3), (0.5, 4.0, 2)]

    def test_moves_6_up_and_1_up_on_the_attacks_side_and_mirrors_them(self):
        assert (3.0, 2.0, 6) in defense.layout("up", 3.0, True)
        assert (3.5, -3.0, 5) in defense.layout("rotation", -3.0, True)
        assert (7.5, -3.0, 6) in defense.layout("rotation", -3.0, True)
        # Through the middle, the rotation stays the perimeter; the front player free under a single block takes the middle.
        assert defense.layout("rotation", 0.5, False)[3:] == defense.BACK["perimeter"]
        assert (3.5, 0.0, 3) in defense.layout("up", 3.0, False)

    def test_numbers_the_learned_spots_by_row_and_side(self):
        learned = {"side": {"5": [(3.0, -3.0), (3.0, 0.0), (6.0, -2.0), (6.0, 2.0), (8.0, 0.0)]}, "middle": {}}

        assert defense.layout("learned", 3.0, False, learned) == [(3.0, -3.0, 4), (3.0, 0.0, 3), (0.5, 3.0, 2), (6.0, -2.0, 5), (8.0, 0.0, 6), (6.0, 2.0, 1)]


class TestAssign:
    def test_gives_each_defender_the_nearest_free_spot(self):
        defenders = {1: (0.5, 3.0), 2: (1.0, 2.0), 3: (2.0, -3.5), 4: (5.5, -3.5), 5: (7.0, 0.0), 6: (5.5, 3.5)}

        found = defense.assign(defense.layout("perimeter", 3.0, defense.doubled(defenders)), defenders)

        assert {person: spot[2] for person, spot in found.items()} == {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 1}

    def test_leaves_a_spot_free_or_a_defender_over(self):
        spots = defense.layout("perimeter", 3.0, False)
        assert defense.assign(spots, {1: (8.0, -1.0)}) == {1: (7.0, 0.0, 6)}
        assert len(defense.assign(spots, {k: (6.5, -3.5 + k * 0.01) for k in range(7)})) == 6
        assert defense.assign(spots, {}) == {}


class TestLearn:
    @staticmethod
    def attack(t: float, x: float, y: float, side: str = "left", result: str = "play") -> dict:
        return {"type": "attack", "t": t, "rally": int(t), "side": side, "x": x, "y": y, "result": result}

    def test_reads_where_each_attack_went_a_dug_ball_further_along_its_flight(self):
        contacts = [
            self.attack(0, -1.0, 3.0),
            {"type": "dig", "rally": 0, "x": 4.0, "y": 3.0},
            self.attack(1, 1.0, 0.0, side="right"),
            {"type": "floor", "rally": 1, "x": -6.0, "y": 2.0},
            self.attack(2, -1.0, 0.0, result="error"),
            {"type": "floor", "rally": 2, "x": 6.0, "y": 0.0},
            self.attack(3, -1.0, 0.0),
            {"type": "block", "rally": 3, "x": 0.5, "y": 0.0},
            self.attack(4, -1.0, 0.0),
            {"type": "floor", "rally": 4, "x": 15.5, "y": -108.5},
        ]

        assert defense.balls(contacts) == [(-3.0, 5.0, -3.0), (0.0, 6.0, 2.0)]

    def test_puts_the_spots_where_the_balls_went_from_enough_of_them(self):
        rng = np.random.default_rng(0)
        clusters = [(7.5, -3.0), (7.5, 3.0), (4.0, 0.0), (8.5, 0.0), (3.0, -3.5)]
        found = [(across, depth + rng.normal(0, 0.2), x + rng.normal(0, 0.2)) for across in (3.0, 0.5) for depth, x in clusters for _ in range(8)]

        learned = defense.learn(found)

        assert all(min(np.hypot(depth - d, x - u) for d, u in learned["side"]["5"]) < 0.5 for depth, x in clusters)
        assert len(learned["middle"]["4"]) == 4
        assert defense.learn(found[:20]) is None
