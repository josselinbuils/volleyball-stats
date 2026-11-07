from volleyball_stats import defense


class TestGaps:
    def test_sends_each_floor_defender_to_the_nearest_free_spot_of_a_side_attack(self):
        # Two blockers on the right, the four others each 1 m short of their spot.
        defenders = {1: (0.5, 3.0), 2: (0.5, 2.0), 3: (2.0, -3.5), 4: (5.5, -3.5), 5: (7.0, 0.0), 6: (5.5, 3.5)}

        found = defense.gaps(3.0, defenders)

        assert found == {3: (defense.FRONT, 1.0, 0.0), 4: (defense.CORNER, 1.0, 0.0), 5: (defense.DEEP, 1.0, 0.0), 6: (defense.CORNER, 1.0, 0.0)}

    def test_mirrors_an_attack_on_the_left_and_measures_out_toward_the_sideline(self):
        found = defense.gaps(-3.0, {1: (0.5, -3.0), 2: (0.5, -2.0), 3: (6.5, 2.5)})

        # Toward the right sideline for the corner there, zone 6's spot taken by nobody.
        assert found == {3: (defense.CORNER, 0.0, 1.0)}

    def test_gives_zone_6_its_way_toward_the_centre(self):
        found = defense.gaps(3.0, {1: (0.5, 3.0), 2: (0.5, 2.0), 3: (8.0, -1.0)})

        assert found == {3: (defense.DEEP, 0.0, -1.0)}

    def test_covers_the_tip_under_a_single_block_and_drops_both_outsides_through_the_middle(self):
        assert defense.gaps(3.0, {1: (0.5, 3.0), 2: (3.0, 1.0)}) == {2: (defense.FRONT, 0.0, 0.5)}
        assert set(defense.spots(0.5, 1)) == set(defense.MIDDLE)

    def test_leaves_a_defender_over_with_no_spot(self):
        defenders = {k: (6.5, -3.5 + k * 0.01) for k in range(7)}

        assert len(defense.gaps(0.0, defenders)) == 5
        assert defense.gaps(3.0, {1: (0.5, 3.0)}) == {}
