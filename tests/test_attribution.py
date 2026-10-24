from volleyball_stats.attribution import GAP_S, REACH, attribute, box_at, distance, read_players
from volleyball_stats.players import Row, write_csv

FPS = 30.0


def row(frame: int, track: int, box: tuple[float, float, float, float], team: str = "left") -> Row:
    return Row(frame, track, box, 0.9, ((box[0] + box[2]) / 2, box[3]), (0.0, 0.0), team)


class TestDistance:
    def test_is_zero_inside_and_in_box_heights_outside(self):
        box = (100.0, 200.0, 140.0, 300.0)

        assert distance((120.0, 250.0), box) == 0
        assert distance((160.0, 250.0), box) == 0.2

    def test_the_reach_extends_the_box_upward_only(self):
        box = (100.0, 200.0, 140.0, 300.0)

        assert distance((120.0, 160.0), box, 0.5) == 0
        assert distance((120.0, 140.0), box, 0.5) == 0.1
        assert distance((120.0, 320.0), box, 0.5) == 0.2


class TestBoxAt:
    BOXES = {10: (0.0, 0.0, 10.0, 20.0), 14: (8.0, 0.0, 18.0, 20.0)}

    def test_takes_the_track_s_own_box(self):
        assert box_at(self.BOXES, 10, 5) == (0.0, 0.0, 10.0, 20.0)

    def test_interpolates_over_a_gap_and_holds_the_nearest_box_at_an_end(self):
        assert box_at(self.BOXES, 12, 5) == (4.0, 0.0, 14.0, 20.0)
        assert box_at(self.BOXES, 17, 5) == (8.0, 0.0, 18.0, 20.0)

    def test_is_none_beyond_the_gap(self):
        assert box_at(self.BOXES, 20, 5) is None


class TestAttribute:
    def test_picks_the_nearest_box_of_the_contact_s_side(self):
        # The opponent across the net is nearer to the ball in the image.
        rows = [row(50, 1, (100, 200, 140, 300)), row(50, 2, (200, 200, 240, 300)), row(50, 3, (150, 200, 190, 300), "right")]

        assert attribute([(50, 170, 250, "dig", "left"), (50, 170, 250, "dig", "right")], rows, FPS) == [1, 3]

    def test_floor_net_and_uncovered_contacts_have_no_player(self):
        rows = [row(50, 1, (100, 200, 140, 300))]

        typed = [(50, 120, 250, "floor", "left"), (50, 120, 250, "net", "left"), (50, 120, 250, "set", "right"), (200, 120, 250, "set", "left")]

        assert attribute(typed, rows, FPS) == [None, None, None, None]

    def test_an_attack_goes_to_the_player_under_the_ball_and_a_set_to_the_nearest_box(self):
        # The hitter's arm is outside her box: the ball is 0.3 heights above it. A teammate's box
        # top is level with the ball, 15 px to the side.
        hitter, teammate = row(50, 1, (100, 200, 140, 300)), row(50, 2, (145, 170, 185, 270))
        ball = (130, 170)

        assert 0.3 < REACH
        assert attribute([(50, *ball, "attack", "left"), (50, *ball, "set", "left")], [hitter, teammate], FPS) == [1, 2]

    def test_keeps_a_track_missing_at_the_contact_frame(self):
        # The toucher is lost 3 frames on each side of the contact, a teammate stands 1 height away.
        gap = round(GAP_S * FPS)
        rows = [row(f, 1, (100, 200, 140, 300)) for f in (47, 53)] + [row(f, 2, (240, 200, 280, 300)) for f in range(40, 60)]

        assert gap >= 3
        assert attribute([(50, 120, 250, "pass", "left")], rows, FPS) == [1]


class TestReadPlayers:
    def test_reads_back_what_players_writes(self, tmp_path):
        rows = [Row(7, 3, (10.5, 20.0, 30.0, 80.0), 0.912, (20.2, 80.0), (-2.5, 1.25), "left")]
        write_csv(rows, tmp_path / "players.csv")

        assert read_players(tmp_path / "players.csv") == rows
