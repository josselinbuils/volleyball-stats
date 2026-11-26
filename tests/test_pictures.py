import json

import cv2
import numpy as np

from volleyball_stats import pictures


class TestPhotos:
    def test_saves_a_picture_of_each_numbered_player_from_their_longest_piece(self, tmp_path, monkeypatch):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(20):
            writer.write(np.full((48, 64, 3), 128, np.uint8))
        writer.release()
        rows = [f"{f},1,left,10,10,20,40,0.9,15,40,-3,0" for f in range(20)]
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "\n".join(rows) + "\n", encoding="utf-8")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n1,0,19,1,3,,1.0\n", encoding="utf-8")
        (tmp_path / "identity_candidates.json").write_text('{"segments": [], "merges": []}', encoding="utf-8")
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n0,19\n", encoding="utf-8")
        people = {0: {"team": 1, "number": 3}, 1: {"team": 2, "number": None}}

        # The picture as cut, without the upscaler.
        monkeypatch.setattr(pictures, "upscaler", lambda: None)
        pictures.photos(tmp_path, video, people, tmp_path / "players", record=tmp_path / pictures.PHOTO_SHOWN)

        assert people[0]["photo"].startswith("players/0.webp?v=")
        # Where it was taken, for an apply to keep it on that player.
        assert json.loads((tmp_path / pictures.PHOTO_SHOWN).read_text(encoding="utf-8"))["players/0.webp"]["track"] == 1
        # The 10x30 box from a little above its top down to its waist (55 %), 3 wide for 4 tall.
        assert cv2.imread(str(tmp_path / "players" / "0.webp")).shape[:2] == (17, 13)
        assert "photo" not in people[1]

    def test_a_picked_moment_swaps_only_that_picture_on_the_page(self, tmp_path, monkeypatch):
        video = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for k in range(20):
            writer.write(np.full((48, 64, 3), 10 * k, np.uint8))
        writer.release()
        rows = [f"{f},1,left,10,10,20,40,0.9,15,40,-3,0" for f in range(20)]
        (tmp_path / "players.csv").write_text("frame,track,team,x1,y1,x2,y2,conf,feet_x,feet_y,court_x,court_y\n" + "\n".join(rows) + "\n", encoding="utf-8")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n1,0,19,1,3,,1.0\n", encoding="utf-8")
        (tmp_path / "identity_candidates.json").write_text('{"segments": [], "merges": []}', encoding="utf-8")
        (tmp_path / "rallies.csv").write_text("start_frame,end_frame\n0,19\n", encoding="utf-8")
        monkeypatch.setattr(pictures, "upscaler", lambda: None)
        site = tmp_path / "review"
        people = {"0": {"team": 1, "number": 3}}
        pictures.photos(tmp_path, video, people, site / "players", record=tmp_path / pictures.PHOTO_SHOWN)
        (site / "data.js").write_text(f"window.MATCH = {json.dumps({'people': people, 'v': 'a'})};\n", encoding="utf-8")
        (site / "index.html").write_text('<script src="data.js?v=a"></script>', encoding="utf-8")
        first, *others = json.loads((tmp_path / pictures.PHOTO_CANDIDATES).read_text(encoding="utf-8"))["1:3"]
        pick = next(m for m in others if m["frame"] != first["frame"])

        found = pictures.swap_photo(tmp_path, video, site, 1, 3, pick["frame"], pick["box"], lambda frame, box: 1)

        from volleyball_stats.web import page_data

        assert found["photo"] != people["0"]["photo"]
        assert page_data(site)["people"]["0"]["photo"] == found["photo"]
        # Offered first from now on, and recorded where it was taken.
        assert json.loads((tmp_path / pictures.PHOTO_CANDIDATES).read_text(encoding="utf-8"))["1:3"][0] == pick
        assert json.loads((tmp_path / pictures.PHOTO_SHOWN).read_text(encoding="utf-8"))["players/0.webp"] == {"track": 1, "frame": pick["frame"]}
        # A moment never scored: the pages are built again instead.
        assert pictures.swap_photo(tmp_path, video, site, 1, 3, 19, [0, 0, 5, 5], lambda frame, box: 1) is None


class TestKeptPhotos:
    def site(self, tmp_path, people):
        (tmp_path / "data.js").write_text(f"window.MATCH = {json.dumps({'people': people})};\n", encoding="utf-8")
        (tmp_path / "players").mkdir()
        for key in people:
            (tmp_path / "players" / f"{key}.webp").write_bytes(b"x")

    def test_keeps_each_picture_on_the_player_it_shows(self, tmp_path):
        # An apply moved the player of #3's picture to #8, and #3 to someone else.
        self.site(tmp_path, {"0": {"team": 1, "number": 3, "photo": "players/0.webp?v=a"}, "1": {"team": 2, "number": 4, "photo": "players/1.webp?v=b"}})
        (tmp_path / pictures.PHOTO_SHOWN).write_text(json.dumps({"players/0.webp": {"track": 7, "frame": 150}, "players/1.webp": {"track": 9, "frame": 50}}), encoding="utf-8")
        (tmp_path / "identities.csv").write_text("track,start_frame,end_frame,team,identity,runner_up,confidence\n7,100,200,1,8,,1\n9,0,100,2,4,,1\n", encoding="utf-8")
        built = {5: {"team": 1, "number": 3}, 6: {"team": 1, "number": 8}, 7: {"team": 2, "number": 4}}

        pictures.kept_photos(built, tmp_path, tmp_path)

        assert built == {5: {"team": 1, "number": 3}, 6: {"team": 1, "number": 8, "photo": "players/0.webp?v=a"}, 7: {"team": 2, "number": 4, "photo": "players/1.webp?v=b"}}

    def test_without_where_it_was_taken_keeps_a_named_players_picture_only(self, tmp_path):
        self.site(tmp_path, {"0": {"team": 1, "number": 3, "name": "Ana", "photo": "players/0.webp?v=a"}, "1": {"team": 2, "number": 4, "photo": "players/1.webp?v=b"}})
        (tmp_path / "players" / "1.webp").unlink()
        built = {5: {"team": 1, "number": 6, "name": "Ana"}, 6: {"team": 2, "number": 4}}

        pictures.kept_photos(built, tmp_path, tmp_path)

        assert built == {5: {"team": 1, "number": 6, "name": "Ana", "photo": "players/0.webp?v=a"}, 6: {"team": 2, "number": 4}}
