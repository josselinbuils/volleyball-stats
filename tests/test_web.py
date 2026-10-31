import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from volleyball_stats.court import Calibration
from volleyball_stats import web
from volleyball_stats.teams import COLOURS
from volleyball_stats.web import ball_track, brand, brief, contacts, drop_rallies, match_data, people, photos, player_samples, playing_time, publish, receivers, result, settle, spot, touched, track_feet, write_site, zone, zone_cells

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

    def test_is_a_point_when_the_ball_lands_in_the_other_court_the_line_included_as_in_the_score(self):
        assert result(self.attack, self.landing("left", -5.0, 2.0)) == "point"
        assert result(self.attack, self.landing("left", -9.2)) == "point"

    def test_is_an_error_when_the_ball_lands_out_on_its_own_side_at_the_foot_of_the_net_or_in_it(self):
        assert result(self.attack, self.landing("left", -9.5)) == "error"
        assert result(self.attack, self.landing("left", -5.0, 4.9)) == "error"
        assert result(self.attack, self.landing("right", 4.0)) == "error"
        assert result(self.attack, self.landing("left", -0.8)) == "error"
        assert result(self.attack, {"type": "net", "side": "right", "x": 0.5, "y": 0.0}) == "error"

    def test_a_block_dropping_at_the_foot_of_the_net_is_its_point_as_in_the_score(self):
        assert result({"type": "block", "side": "left"}, self.landing("right", 0.5)) == "point"

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
        receivers(out, typed, players)

        assert out[0]["result"] == "point"
        assert out[0]["receiver"] == 6
        assert "receiver" not in out[1]

    def test_an_ace_without_a_landing_across_the_net_has_the_receiver_the_review_said_else_none_known(self):
        typed = [
            {"frame": "10", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
            {"frame": "20", "x": "-4", "y": "2", "type": "net", "side": "left"},
            {"frame": "50", "x": "-8", "y": "0", "type": "serve", "side": "left", "track": "1"},
        ]
        players = {20: [{"x1": "0", "y1": "0", "x2": "1", "y2": "1", "court_x": "-3.0", "court_y": "2.0", "track": "1"}]}
        out = contacts(typed, [(5, 40), (45, 80)], players, 10.0, IDENTITY, 15)
        # The points step made both serves aces: each was its rally's last touch and won it.
        out[0]["result"] = out[2]["result"] = "point"
        said = lambda track, frame, given=None: given[1] if given else track  # noqa: E731

        receivers(out, typed, players, said, {50: (2, 4)})
        assert "receiver" not in out[0]
        assert out[2]["receiver"] == 4

        receivers(out, typed, players, said, {10: None})
        assert out[0]["receiver"] is None

    def test_a_player_on_the_court_only_seconds_in_a_set_touches_nothing_known_there(self):
        table = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": 4}, 2: {"team": 1, "number": None}}
        times = {0: {"1": 7.0, "2": 300.0}, 1: {"1": 280.0}}
        found = [
            {"person": 0, "set": 1},  # 7 s in set 1: a slip
            {"person": 0, "set": 2},
            {"person": 0, "set": 1},  # the review said who touched it
            {"person": 2, "set": 1},  # a track without identity: already nobody's
            {"person": 1, "set": 1, "receiver": 0},  # an ace missed by the slip
        ]
        typed = [{"frame": str(f)} for f in (10, 20, 30, 40, 50)]

        brief(found, typed, table, times, {30: (1, 3)}, {})

        assert [(c["person"], c.get("brief")) for c in found] == [(None, True), (0, None), (0, None), (2, None), (1, None)]
        assert "receiver" not in found[4]
        brief(found, typed, table, {}, {}, {})  # without players' times, nothing changes
        assert found[1]["person"] == 0

    def test_a_receiver_of_the_serve_s_own_team_makes_it_their_missed_reception(self):
        # The window started late: its first touch, the left team's, was taken for a serve.
        typed = [{"frame": "10", "x": "-5", "y": "0", "type": "serve", "side": "left", "track": "1", "team": "2"}]
        out = contacts(typed, [(5, 40)], {}, 10.0, IDENTITY, 15)
        out[0]["result"] = "point"
        said = lambda track, frame, given=None: given[1] if given else track  # noqa: E731

        receivers(out, typed, {}, said, {10: (2, 7)})

        assert (out[0]["type"], out[0]["result"], out[0]["person"]) == ("pass", "error", 7)
        assert "receiver" not in out[0]

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
        assert who(None, 80, (1, 3)) == 0
        assert table == {0: {"team": 1, "number": 3, "jersey": 7, "name": "Julie"}}

    def test_a_touch_goes_to_the_player_the_review_named_by_name_else_by_number(self, tmp_path):
        touches = [{"frame": 5, "team": 2, "identity": 3, "name": "Julie"}, {"frame": 9, "team": 1, "identity": 4, "name": None}, {"frame": 12, "team": 1, "identity": None, "name": None}]
        (tmp_path / "identity_answers.json").write_text(json.dumps({"touch": touches}))

        assert touched(tmp_path, {(2, 7): {"name": "Julie", "jersey": None}}) == {5: (2, 7), 9: (1, 4), 12: None}


class TestPlayingTime:
    def test_counts_each_players_time_on_the_court_in_the_rallies_by_set(self):
        # 10 fps, a sample every 5 frames: frames 0, 5, 10, 15, 20.
        samples = [[1, 0.0, 0.0], [1, 11.5, 0.0, 2, 0.0, 6.0], [1, 0.0, 0.0, 2, 3.0, 4.0], [1, 13.0, 0.0], [2, 0.0, 0.0]]

        # Rallies over frames 3-12 (set 1) and 18-20 (set 2): player 1 serving 2.5 m behind the end
        # line counts, 4 m behind does not; player 2 on the bench 1.5 m out does not.
        found = playing_time(samples, 5, [(3, 12), (18, 20)], [1, 2], 10.0)

        assert found == {1: {"1": 1.0}, 2: {"1": 0.5, "2": 0.5}}


class TestBallTrack:
    def test_keeps_the_balls_place_seen_in_the_rallies_every_step(self, tmp_path):
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n20,40\n")
        rows = [f"{f},{int(f != 32)},{f * 10},{f * 5}" for f in range(0, 60, 2)]
        (tmp_path / "ball.csv").write_text("frame,visible,x,y\n" + "\n".join(rows) + "\n")

        # 10 fps: every frame, the rally from 3 frames before its start; frame 32 unseen.
        found = ball_track(tmp_path, (1000, 500), 10.0)

        frames = found["samples"][::3]
        assert frames == [18, 20, 22, 24, 26, 28, 30, 34, 36, 38, 40]
        assert found["samples"][:3] == [18, 0.18, 0.18] and found["fps"] == 10.0


class TestDropRallies:
    def test_a_window_said_to_be_no_rally_goes_with_its_contacts_and_points(self):
        windows = [(100, 200), (300, 400), (500, 600), (700, 800)]
        rows = [{"set": "1"}, {"set": "1"}, {"set": "1"}, {"set": "2"}]
        scores = [
            {"winner": "1", "score_1": "1", "score_2": "0"},
            {"winner": "2", "score_1": "1", "score_2": "1"},
            {"winner": "1", "score_1": "2", "score_2": "1"},
            {"winner": "2", "score_1": "0", "score_2": "1"},
        ]
        actions = [{"frame": "150"}, {"frame": "290"}, {"frame": "350"}, {"frame": "550"}]

        w, r, s, a = drop_rallies(windows, rows, scores, actions, {300}, 20)

        assert w == [(100, 200), (500, 600), (700, 800)] and len(r) == 3
        assert [(p["score_1"], p["score_2"]) for p in s] == [("1", "0"), ("2", "0"), ("0", "1")]
        assert [x["frame"] for x in a] == ["150", "550"]


class TestSettle:
    def test_a_rallys_last_touch_wins_or_loses_it_as_its_winner_says(self):
        def c(rally, kind, team, result="play"):
            return {"rally": rally, "type": kind, "team": team, "result": result}

        found = [c(0, "serve", 1), c(0, "attack", 2), c(0, "floor", None), c(1, "serve", 2), c(1, "dig", 1, "error"), c(2, "serve", 1)]

        settle(found, [2, 2, None])

        assert [x["result"] for x in found] == ["play", "point", "play", "play", "error", "play"]


class TestBrand:
    def test_copies_a_themes_logo_into_the_site_shrunk_and_lists_the_themes_for_an_unknown_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(web, "BRANDING", tmp_path / "branding")
        theme = tmp_path / "branding" / "club"
        theme.mkdir(parents=True)
        cv2.imwrite(str(theme / "logo.png"), np.zeros((500, 400, 4), np.uint8))
        (theme / "sponsors").mkdir()
        cv2.imwrite(str(theme / "sponsors" / "sponsor.png"), np.zeros((320, 200, 4), np.uint8))
        (theme / "sponsors" / "sponsors.json").write_text('[{"name": "Shop", "logo": "sponsor.png"}, {"name": "Bakery"}]')
        (theme / "brand.json").write_text('{"name": "Club", "logo": "logo.png", "light": {}, "dark": {}}')

        data = brand("club", tmp_path / "site")

        assert data["logo"] == "brand/logo.png"
        assert cv2.imread(str(tmp_path / "site" / "brand" / "logo.png"), cv2.IMREAD_UNCHANGED).shape == (128, 102, 4)
        inlined = base64.b64decode(data["sponsors"][0]["logo"].removeprefix("data:image/png;base64,"))
        assert cv2.imdecode(np.frombuffer(inlined, np.uint8), cv2.IMREAD_UNCHANGED).shape == (160, 100, 4)
        assert data["sponsors"][1] == {"name": "Bakery"}
        assert brand("none", tmp_path / "site") is None
        with pytest.raises(SystemExit, match="club, none"):
            brand("other", tmp_path / "site")


class TestMatchData:
    def test_reads_a_hand_edited_date_and_colour_and_refuses_what_it_cannot(self, tmp_path):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        writer.write(np.zeros((48, 64, 3), np.uint8))
        writer.release()
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n")
        (tmp_path / "actions.csv").write_text("frame,x,y,type,side,track\n")
        (tmp_path / "tracks.csv").write_text("track,team\n")
        teams = {"date": "25/10/2026", "teams": [{"name": "A", "colour": " Rouge", "jersey": "#ffffff"}, {"name": "B", "colour": None, "jersey": "#000080"}]}
        (tmp_path / "teams.json").write_text(json.dumps(teams))

        data, _ = match_data(tmp_path, video, IDENTITY)

        assert data["date"] == "2026-10-25" and [t["colour"] for t in data["teams"]] == [COLOURS["red"], "#000080"]
        teams["date"] = "25 octobre"
        (tmp_path / "teams.json").write_text(json.dumps(teams))
        with pytest.raises(ValueError, match="25 octobre"):
            match_data(tmp_path, video, IDENTITY)
        teams["date"], teams["teams"][0]["colour"] = "2026-10-25", "sparkly"
        (tmp_path / "teams.json").write_text(json.dumps(teams))
        with pytest.raises(ValueError, match="sparkly"):
            match_data(tmp_path, video, IDENTITY)


class TestWriteSite:
    def test_copies_the_page_next_to_data_js_and_the_video(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.write_bytes(b"not a video")
        site = tmp_path / "site"
        (site / "assets").mkdir(parents=True)
        (site / "assets" / "old.js").write_text("")

        write_site({"fps": 25.0, "rallies": [], "name": "Bègles"}, {"step": 3, "samples": [[]]}, video, site, copy=True)

        version = (site / "index.html").read_text().split('src="data.js?v=')[1].split('"')[0]
        assert len(version) == 10
        assert not (site / "assets" / "old.js").exists()
        assert (site / "data.js").read_text() == f'window.MATCH = {{"fps":25.0,"rallies":[],"name":"Bègles","video":"match.mp4","v":"{version}"}};\n'
        assert (site / "players.js").read_text() == 'window.MATCH_PLAYERS = {"step":3,"samples":[[]]};\n'

        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)

        assert f'src="data.js?v={version}"' not in (site / "index.html").read_text()

        assert not (site / "players.js").exists()
        assert (site / "match.mp4").read_bytes() == b"not a video"
        assert not (site / "poster.webp").exists()

    def test_offers_an_av1_copy_beside_the_video_both_keeping_their_dates(self, tmp_path):
        video, av1 = tmp_path / "match.mp4", tmp_path / "match_av1.mp4"
        video.write_bytes(b"h264")
        av1.write_bytes(b"av1")
        site = tmp_path / "site"

        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True, av1=av1)

        assert '"video":"match.mp4","av1":"match_av1.mp4"' in (site / "data.js").read_text()
        assert (site / "match_av1.mp4").read_bytes() == b"av1"
        assert (site / "match.mp4").stat().st_mtime == video.stat().st_mtime

    def test_leaves_the_video_out_and_removes_a_previous_one(self, tmp_path):
        # The camera names its files in capitals; a symlinked one too.
        video, other = tmp_path / "DJI_0001.MP4", tmp_path / "clip.mov"
        video.write_bytes(b"not a video")
        other.write_bytes(b"not a video")
        site = tmp_path / "site"
        write_site({"fps": 25.0, "rallies": []}, None, video, site, copy=True)
        (site / other.name).symlink_to(other)

        write_site({"fps": 25.0, "rallies": []}, None, None, site, copy=True)

        assert not (site / video.name).exists() and not (site / other.name).is_symlink()
        assert '"video":null' in (site / "data.js").read_text()


class TestPhotos:
    def test_saves_a_picture_of_each_numbered_player_from_their_longest_piece(self, tmp_path, monkeypatch):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(20):
            writer.write(np.full((48, 64, 3), 128, np.uint8))
        writer.release()
        rows = [f"{f},1,left,10,10,20,40,0.9,15,40,-3,0" for f in range(20)]
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "\n".join(rows) + "\n")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n1,0,19,1,3,,1.0\n")
        (tmp_path / "identity_candidates.json").write_text('{"segments": [], "merges": []}')
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n0,19\n")
        people = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": None}}

        # The picture as cut, without the upscaler.
        monkeypatch.setattr(web, "upscaler", lambda: None)
        photos(tmp_path, video, people, tmp_path / "players")

        assert people[0]["photo"].startswith("players/0.webp?v=")
        # The 10x30 box from a little above its top down to its waist (55 %), 3 wide for 4 tall.
        assert cv2.imread(str(tmp_path / "players" / "0.webp")).shape[:2] == (17, 13)
        assert "photo" not in people[1]


class TestPublish:
    def test_keeps_the_previous_choices_each_given_one_replacing_its_own(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[4:]) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "blur-opponents", "club": 1, "pictures": True})
        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": None, "pictures": False})

        # copy, theme, footage, club, pictured teams
        assert built == [(False, "aspom", "blur-opponents", 1, {1}), (False, "aspom", "blur-opponents", 1, set())]

    def test_a_page_to_host_shows_only_what_it_is_given_and_saves_nothing(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[4:]) or {})
        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "full", "club": 1, "pictures": True})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": 1}, tmp_path / "hosted")

        assert built[1] == (False, "aspom", "none", 1, set())
        assert json.loads((tmp_path / "page.json").read_text())["footage"] == "full"

    def test_plays_a_lighter_copy_of_the_full_footage_only(self, tmp_path, monkeypatch):
        with pytest.raises(ValueError):
            web.build(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", tmp_path / "site", footage="blur-all", light=tmp_path / "v_1080p.mp4")
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(kwargs) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"footage": "full", "light": "v_1080p.mp4", "link": None}, tmp_path / "hosted")

        assert built == [{"light": Path("v_1080p.mp4"), "link": None, "feedback": None, "av1": None}]

    def test_pictures_both_teams_of_the_club(self, tmp_path, monkeypatch):
        built = []
        monkeypatch.setattr(web, "build", lambda *args, **kwargs: built.append(args[8]) or {})

        publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": "both", "pictures": True}, tmp_path / "hosted")

        assert built == [{1, 2}]
        with pytest.raises(ValueError):
            publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"club": "both", "footage": "blur-opponents"}, tmp_path / "hosted")

    def test_refuses_pictures_or_a_blurred_opponent_without_a_club(self, tmp_path):
        with pytest.raises(ValueError):
            publish(tmp_path, tmp_path / "v.mp4", tmp_path / "c.json", "aspom", {"pictures": True})
