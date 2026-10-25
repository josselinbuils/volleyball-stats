import cv2
import numpy as np
import pytest

from volleyball_stats.court import Calibration
from volleyball_stats import web
from volleyball_stats.web import brand, contacts, people, photos, player_samples, publish, result, spot, track_feet, write_site, zone, zone_cells

# Pixels are court metres.
IDENTITY = Calibration(np.eye(3))


class TestSpot:
    boxes = np.array([[100.0, 50.0, 140.0, 200.0], [300.0, 80.0, 330.0, 180.0], [105.0, 120.0, 135.0, 160.0]])
    feet = np.array([[-3.0, 1.0], [2.0, -2.0], [-4.0, -3.0]])

    def test_places_a_floor_contact_at_the_balls_floor_projection(self):
        assert spot("floor", (1.5, -2.0), self.boxes, self.feet, IDENTITY, 15) == (1.5, -2.0)

    def test_takes_the_feet_of_the_player_under_the_ball_whose_head_is_nearest(self):
        assert spot("attack", (120.0, 40.0), self.boxes, self.feet, IDENTITY, 15) == (-3.0, 1.0)
        assert spot("dig", (120.0, 125.0), self.boxes, self.feet, IDENTITY, 15) == (-4.0, -3.0)

    def test_takes_the_nearest_player_horizontally_when_none_is_under_the_ball(self):
        assert spot("serve", (250.0, 60.0), self.boxes, self.feet, IDENTITY, 15) == (2.0, -2.0)

    def test_has_no_position_without_players(self):
        assert spot("set", (120.0, 40.0), np.empty((0, 4)), np.empty((0, 2)), IDENTITY, 15) is None


class TestTrackFeet:
    players = {
        10: [{"track": "4", "court_x": "1.0", "court_y": "2.0"}, {"track": "5", "court_x": "-3.0", "court_y": "0.0"}],
        14: [{"track": "4", "court_x": "3.0", "court_y": "4.0"}],
    }

    def test_takes_the_tracks_feet_at_the_frame(self):
        assert track_feet(4, 10, self.players, 2) == (1.0, 2.0)

    def test_interpolates_over_a_detection_gap(self):
        assert track_feet(4, 12, self.players, 2) == (2.0, 3.0)

    def test_has_no_position_when_the_track_is_not_that_close(self):
        assert track_feet(5, 13, self.players, 2) is None
        assert track_feet(7, 10, self.players, 2) is None


class TestZone:
    def test_numbers_the_left_half_from_its_end_line(self):
        # Facing the net, the left team's left hand is toward the far sideline (y < 0).
        assert [zone(-1.5, y) for y in (-3, 0, 3)] == [4, 3, 2]
        assert [zone(-6.0, y) for y in (-3, 0, 3)] == [5, 6, 1]

    def test_mirrors_the_right_half(self):
        assert [zone(1.5, y) for y in (-3, 0, 3)] == [2, 3, 4]
        assert [zone(6.0, y) for y in (-3, 0, 3)] == [1, 6, 5]

    def test_puts_points_off_the_court_in_the_nearest_zone(self):
        assert zone(-11.0, 5.5) == 1  # a server behind the end line, near corner
        assert zone(10.5, -6.0) == 1

    def test_cells_cover_both_halves_with_each_zone_once(self):
        cells = zone_cells()
        assert sorted(c["zone"] for c in cells if c["x"] < 0) == [1, 2, 3, 4, 5, 6]
        assert sorted(c["zone"] for c in cells if c["x"] >= 0) == [1, 2, 3, 4, 5, 6]
        assert sum(c["w"] * c["h"] for c in cells) == 18 * 9


class TestResult:
    attack = {"type": "attack", "side": "right"}

    def landing(self, side: str, x: float, y: float = 0.0) -> dict:
        return {"type": "floor", "side": side, "x": x, "y": y}

    def test_is_a_point_when_the_ball_lands_in_the_other_court(self):
        assert result(self.attack, self.landing("left", -5.0, 2.0)) == "point"

    def test_is_an_error_when_the_ball_lands_out_on_its_own_side_or_in_the_net(self):
        assert result(self.attack, self.landing("left", -9.5)) == "error"
        assert result(self.attack, self.landing("left", -5.0, 4.8)) == "error"
        assert result(self.attack, self.landing("right", 4.0)) == "error"
        assert result(self.attack, {"type": "net", "side": "right", "x": 0.5, "y": 0.0}) == "error"

    def test_is_in_play_when_the_ball_is_played_again_or_the_rally_ends(self):
        assert result(self.attack, {"type": "dig", "side": "left", "x": -6.0, "y": 0.0}) == "play"
        assert result(self.attack, None) == "play"


class TestContacts:
    def test_builds_the_rallies_contacts_with_positions_zones_and_results(self):
        typed = [
            {"frame": "8", "x": "-10", "y": "3", "type": "serve", "side": "left"},  # in the window's lead
            {"frame": "40", "x": "6", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "45", "x": "7", "y": "-1", "type": "floor", "side": "right"},
            {"frame": "100", "x": "8", "y": "0", "type": "serve", "side": "right"},
        ]
        players = {8: [{"x1": "-10.5", "y1": "1", "x2": "-9.5", "y2": "3", "court_x": "-10.4", "court_y": "3.1"}]}

        out = contacts(typed, [(10, 60), (100, 130)], players, 10.0, IDENTITY, 15)

        assert [(c["t"], c["rally"], c["type"]) for c in out] == [(0.8, 0, "serve"), (4.0, 0, "floor"), (4.5, 0, "floor"), (10.0, 1, "serve")]
        assert (out[0]["x"], out[0]["y"], out[0]["zone"]) == (-10.4, 3.1, 1)
        # The floor contact is the ball's floor projection; the dead ball after it has no position.
        assert (out[1]["x"], out[1]["y"]) == (6.0, -1.0)
        assert out[2]["x"] is None and out[2]["zone"] is None
        assert out[3]["x"] is None  # no player at that frame
        assert [c["result"] for c in out] == ["point", "play", "play", "play"]
        assert [c["person"] for c in out] == [None, None, None, None]
        assert [c["team"] for c in out] == [None, None, None, None]

    def test_an_ace_names_the_receiver_nearest_to_where_it_lands(self):
        typed = [
            {"frame": "10", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
            {"frame": "30", "x": "5", "y": "2", "type": "floor", "side": "right"},
        ]
        feet = lambda track, x, y: {"x1": "0", "y1": "0", "x2": "1", "y2": "1", "court_x": str(x), "court_y": str(y), "track": str(track)}
        players = {10: [feet(1, -8.0, 0.0)], 30: [feet(1, -2.0, 2.0), feet(5, 7.0, -3.0), feet(6, 4.0, 3.0)]}

        out = contacts(typed, [(5, 40)], players, 10.0, IDENTITY, 15)

        assert out[0]["result"] == "point"
        assert out[0]["receiver"] == 6
        assert "receiver" not in out[1]

    def test_places_an_attributed_contact_at_its_players_feet_else_under_the_ball(self):
        typed = [
            {"frame": "10", "x": "0", "y": "0", "type": "attack", "side": "left", "track": "7"},
            {"frame": "20", "x": "0", "y": "0", "type": "dig", "side": "right", "track": "9", "team": "2"},  # track not found
        ]
        under = {"x1": "-1", "y1": "-1", "x2": "1", "y2": "1", "court_x": "-1.0", "court_y": "0.5", "track": "8"}
        players = {
            10: [under, {"x1": "5", "y1": "5", "x2": "6", "y2": "7", "court_x": "-4.0", "court_y": "2.0", "track": "7"}],
            20: [{**under, "court_x": "2.0"}],
        }

        out = contacts(typed, [(5, 30)], players, 10.0, IDENTITY, 15)

        assert [(c["x"], c["y"], c["person"], c["team"]) for c in out] == [(-4.0, 2.0, 7, None), (2.0, 0.5, 9, 2)]


class TestPlayerSamples:
    def test_keeps_every_steps_frame_of_the_video_as_track_and_feet_rounded_to_the_centimetre(self):
        rows = [
            {"frame": "3", "track": "5", "court_x": "3.14159", "court_y": "-1.005"},
            {"frame": "3", "track": "2", "court_x": "-2.0", "court_y": "1.234"},
            {"frame": "4", "track": "2", "court_x": "-2.1", "court_y": "1.2"},
            {"frame": "9", "track": "2", "court_x": "-4.0", "court_y": "0.0"},
        ]

        assert player_samples(rows, 3, 10) == [[], [5, 3.14, -1.0, 2, -2.0, 1.23], [], [2, -4.0, 0.0]]


class TestPeople:
    def test_one_player_per_identity_across_its_tracks_and_one_per_track_without_identity(self):
        # Track 1 is identity 3 then, past a crowd at frame 50, identity 4; track 2 continues 4.
        identities = [(1, 0, 49, 1, 3), (1, 51, 90, 1, 4), (2, 100, 200, 1, 4)]

        who, table = people({1: 1, 2: 1, 5: 2}, identities)

        assert [who(1, 10), who(1, 60), who(2, 150), who(5, 10), who(None, 10)] == [0, 1, 1, 2, None]
        assert table == {
            0: {"team": 1, "number": 3, "jersey": None, "name": None},
            1: {"team": 1, "number": 4, "jersey": None, "name": None},
            2: {"team": 2, "number": None, "jersey": None, "name": None},
        }

    def test_an_identity_takes_the_name_and_jersey_number_the_user_gave_it(self):
        who, table = people({1: 1}, [(1, 0, 49, 1, 3)], {(1, 3): {"name": "Julie", "jersey": 7}})

        assert who(1, 10) == 0
        assert table == {0: {"team": 1, "number": 3, "jersey": 7, "name": "Julie"}}


class TestBrand:
    def test_copies_a_themes_logo_into_the_site_shrunk_and_lists_the_themes_for_an_unknown_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web, "BRANDING", tmp_path / "branding")
        theme = tmp_path / "branding" / "club"
        theme.mkdir(parents=True)
        cv2.imwrite(str(theme / "logo.png"), np.zeros((500, 400, 4), np.uint8))
        (theme / "brand.json").write_text('{"name": "Club", "logo": "logo.png", "light": {}, "dark": {}}')

        data = brand("club", tmp_path / "site")

        assert data["logo"] == "brand/logo.png"
        assert cv2.imread(str(tmp_path / "site" / "brand" / "logo.png"), cv2.IMREAD_UNCHANGED).shape == (128, 102, 4)
        assert brand("none", tmp_path / "site") is None
        with pytest.raises(SystemExit, match="club, none"):
            brand("other", tmp_path / "site")


class TestWriteSite:
    def test_copies_the_page_next_to_data_js_and_the_video(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"not a video")
        site = tmp_path / "site"
        (site / "assets").mkdir(parents=True)
        (site / "assets" / "old.js").write_text("")

        write_site({"fps": 25.0, "rallies": [], "name": "Bègles"}, {"step": 3, "samples": [[]]}, video, site, copy=True)

        assert (site / "index.html").read_text().count('src="data.js"') == 1
        assert not (site / "assets" / "old.js").exists()
        assert (site / "data.js").read_text() == 'window.MATCH = {"fps":25.0,"rallies":[],"name":"Bègles","video":"match.mp4"};\n'
        assert (site / "players.js").read_text() == 'window.MATCH_PLAYERS = {"step":3,"samples":[[]]};\n'

        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)

        assert not (site / "players.js").exists()
        assert (site / "match.mp4").read_bytes() == b"not a video"
        assert not (site / "poster.webp").exists()

    def test_leaves_the_video_out_and_removes_a_previous_one(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"not a video")
        site = tmp_path / "site"
        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)

        write_site({"fps": 25.0, "rallies": []}, None, None, site, copy=True)

        assert not (site / "match.mp4").exists()
        assert '"video":null' in (site / "data.js").read_text()


class TestPhotos:
    def test_saves_a_picture_of_each_numbered_player_from_their_longest_piece(self, tmp_path):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(20):
            writer.write(np.full((48, 64, 3), 128, np.uint8))
        writer.release()
        rows = [f"{f},1,left,10,10,20,40,0.9,15,40,-3,0" for f in range(20)]
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "\n".join(rows) + "\n")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n1,0,19,1,3,,1.0\n")
        (tmp_path / "identity_candidates.json").write_text('{"segments": [], "merges": []}')
        people = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": None}}

        photos(tmp_path, video, people, tmp_path / "players")

        assert people[0]["photo"] == "players/0.webp"
        # The 10x30 box, 38 px tall with its margins and widened to 3 for 4.
        assert cv2.imread(str(tmp_path / "players" / "0.webp")).shape[:2] == (38, 28)
        assert "photo" not in people[1]


class TestPublish:
    def test_keeps_the_previous_choices_each_given_one_replacing_its_own(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args: built.append(args[4:]) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "blur-opponents", "club": 1, "pictures": True})
        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": None, "pictures": False})

        # copy, theme, footage, club, pictured teams
        assert built == [(False, "aspom", "blur-opponents", 1, {1}), (False, "aspom", "blur-opponents", 1, set())]

    def test_refuses_pictures_or_a_blurred_opponent_without_a_club(self, tmp_path):
        with pytest.raises(ValueError):
            publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"pictures": True})
