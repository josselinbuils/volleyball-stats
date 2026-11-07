from volleyball_stats import review
from volleyball_stats.rekey import added_rallies, found, moved, moved_comments, overlaps, renamed_reports, with_reports


class TestOverlaps:
    def test_most_overlapped(self):
        assert overlaps([(100, 200), (300, 400)], [(90, 130), (140, 260), (500, 600)], 0) == {0: 1}

    def test_lead_counts(self):
        assert overlaps([(100, 200)], [(205, 300)], 10) == {0: 0}


class TestMovedReferee:
    def test_the_referee_s_error_follows_its_rally(self):
        out = moved([{"id": "edit:1", "referee": [{"start": 100, "wrong": True}]}], [(100, 200)], [(90, 200)], 10)
        assert out[0]["referee"] == [{"start": 90, "wrong": True}]


class TestMovedComments:
    def test_comments_follow_their_rally_and_two_on_one_window_are_joined(self):
        comments = {100: "a", 300: "b", 500: "c", 150: "started by the review"}
        out = moved_comments(comments, [(100, 200), (300, 400), (500, 600)], [(90, 200), (290, 610)], 10)
        assert out == {90: "a", 150: "started by the review", 290: "b\nc"}


class TestMoved:
    def test_starts_moved(self):
        log = [{"id": "report:a", "added": [{"start": 100, "frame": 95, "team": 1, "type": "serve"}], "checked": [100, 300]}, {"id": "rally:100", "rally": [{"start": 300, "play": False}]}]
        out = moved(log, [(100, 200), (300, 400)], [(90, 200), (310, 400)], 10)
        assert out[0]["added"][0]["start"] == 90
        assert out[0]["checked"] == [90, 310]
        assert out[1]["rally"] == [{"start": 310, "play": False}]

    def test_answer_a_lead_late_moved(self):
        assert moved([{"id": "rally:100", "rally": [{"start": 110, "play": False}]}], [(100, 200)], [(90, 200)], 10)[0]["rally"][0]["start"] == 90

    def test_no_play_stays_off_a_rally_it_was_joined_to(self):
        # A false window 300-330 now the tail of the rally 100-330.
        log = [{"id": "rally:300", "rally": [{"start": 300, "play": False}], "added": [{"start": 300, "frame": 310, "team": 1, "type": "dig"}]}]
        out = moved(log, [(100, 290), (300, 330)], [(100, 330)], 10)
        assert out[0]["rally"][0]["start"] == 300
        assert out[0]["added"][0]["start"] == 100

    def test_unmatched_kept(self):
        assert moved([{"id": "x", "rally": [{"start": 100, "play": True}]}], [(100, 200)], [(500, 600)], 10)[0]["rally"][0]["start"] == 100

    def test_join_in_one_window_goes(self):
        log = [{"id": "x", "join": [{"start": 100}]}]
        assert moved(log, [(100, 200), (220, 300)], [(100, 300)], 10)[0]["join"] == []
        assert moved(log, [(100, 200), (220, 300)], [(100, 200), (220, 300)], 10)[0]["join"] == [{"start": 100}]


class TestFound:
    def test_a_rally_the_review_added_now_found_moves_whole_and_its_split_goes(self):
        # The review split off 300 between the windows 100-200 and 500-600; its serve is at 250, its end 280.
        page = {"fps": 10, "rallies": [{"key": 100, "start": 10.0, "end": 20.0}, {"key": 300, "start": 25.0, "end": 28.0}, {"key": 500, "start": 50.0, "end": 60.0}]}
        before, after = [(100, 200), (500, 600)], [(100, 200), (245, 275), (500, 600)]
        added = added_rallies(page, before)
        assert added == {300: (250, 280)}
        adopted = found(added, before, after, 10)
        assert adopted == {300: 245}
        log = [{"id": "x", "split": [{"frame": 300}, {"frame": 550}], "end": [{"start": 300, "end": 280}], "pinned": [{"start": 300, "winner": 2}], "checked": [300]}]
        out = moved(log, before, after, 10, adopted)[0]
        assert out["split"] == [{"frame": 550}]
        assert out["end"] == [{"start": 245, "end": 280}]
        assert out["pinned"] == [{"start": 245, "winner": 2}]
        assert out["checked"] == [245]
        assert moved_comments({300: "a"}, before, after, 10, adopted) == {245: "a"}

    def test_a_new_window_over_an_old_one_adopts_nothing(self):
        assert found({300: (250, 280)}, [(100, 260)], [(100, 290)], 10) == {}


class TestReports:
    def test_renamed(self):
        page = lambda start: {"rallies": [{"start": start, "end": 20.0, "set": 1}], "contacts": [], "teams": None}  # noqa: E731
        keys = renamed_reports(page(10.0), page(9.5))
        assert len(keys) == 1
        assert list(keys) != list(keys.values())

    def test_a_report_at_the_rally_s_end_is_renamed(self):
        page = lambda start: {"rallies": [{"start": start, "end": 20.0, "set": 1}], "contacts": [], "teams": [{"name": "A"}, {"name": "B"}]}  # noqa: E731
        before, after = review.unusual(page(10.0)), review.unusual(page(9.5))
        assert "auto.noWinner" in [r["kind"] for r in before]
        assert renamed_reports(page(10.0), page(9.5)) == {b["key"]: a["key"] for b, a in zip(before, after)}

    def test_people_of_a_page_just_built(self):
        rallies = [{"start": 0.0, "end": 1.0, "set": 1}]
        contact = {"t": 0.1, "type": "serve", "team": 1, "side": "left", "rally": 0, "result": "error", "person": 0}
        people = {0: {"team": 1, "jersey": 10, "name": "Ana"}, 1: {"team": 1, "jersey": 10, "name": "Zoé"}}
        built = {"people": people, "rallies": rallies, "contacts": [contact]}
        read = {**built, "people": {str(p): q for p, q in people.items()}}
        assert renamed_reports(read, built)

    def test_ids(self):
        assert with_reports([{"id": "report:a+b"}, {"id": "touch:1"}], {"a": "c"}) == [{"id": "report:c+b"}, {"id": "touch:1"}]
