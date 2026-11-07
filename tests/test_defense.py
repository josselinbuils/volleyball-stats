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


    def test_shifts_laeticias_block_inside_and_sends_the_line_digger_deep_on_the_line(self):
        found = defense.layout("laeticia", 3.0, True)

        assert [(depth, round(x, 2), p) for depth, x, p in found[:2]] == [(0.5, 1.35, 3), (0.5, 2.25, 2)]
        assert (6.05, 3.9, 1) in found and (2.4, -0.4, 4) in found
        # Mirrored, the line digger is 5; through the middle under a double block, 4 drops off alone.
        assert (6.05, -3.9, 5) in defense.layout("laeticia", -3.0, True)
        assert sorted(p for _, _, p in defense.layout("laeticia", 0.5, True)) == [1, 2, 3, 4, 5, 6]


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
