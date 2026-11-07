from volleyball_stats import defense


class TestSpots:
    def test_numbers_the_front_spots_4_3_2_from_left_to_right(self):
        # A single block on the right: the off-blocker left, the tip behind the block, the blocker at the net.
        assert defense.spots(3.0, False)[:3] == [(3.0, -3.5, 4), (3.0, 1.5, 3), (0.5, 3.0, 2)]
        # A double block on the left: the off-blocker right.
        assert [(depth, round(x, 2), position) for depth, x, position in defense.spots(-3.0, True)[:3]] == [(0.5, -3.45, 4), (0.5, -2.55, 3), (3.0, 3.5, 2)]
        # Through the middle under a single block, both outsides drop off.
        assert defense.spots(0.5, False)[:3] == [(3.0, -3.5, 4), (0.5, 0.5, 3), (3.0, 3.5, 2)]
        assert defense.spots(0.5, False)[3:] == defense.BACK

    def test_keeps_the_block_inside_the_court(self):
        assert defense.spots(6.0, False)[2] == (0.5, 4.0, 2)
        assert [(depth, round(x, 2), position) for depth, x, position in defense.spots(6.0, True)[1:3]] == [(0.5, 3.1, 3), (0.5, 4.0, 2)]


class TestAssign:
    def test_gives_each_defender_the_nearest_free_spot_a_double_block_read_from_the_net(self):
        defenders = {1: (0.5, 3.0), 2: (1.0, 2.0), 3: (2.0, -3.5), 4: (5.5, -3.5), 5: (7.0, 0.0), 6: (5.5, 3.5)}

        found = defense.assign(3.0, defenders)

        assert {person: spot[2] for person, spot in found.items()} == {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 1}
        assert round(found[2][1], 2) == 2.55

    def test_leaves_a_spot_free_or_a_defender_over(self):
        assert defense.assign(3.0, {1: (8.0, -1.0)}) == {1: (8.0, 0.0, 6)}
        assert len(defense.assign(0.0, {k: (6.5, -3.5 + k * 0.01) for k in range(7)})) == 6
        assert defense.assign(3.0, {}) == {}
