import http.client
import json
import threading
import time

import pytest

from volleyball_stats import app, files, presence, review_server
from volleyball_stats.review_server import list_page, match_list, openable, range_of, with_review


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The review's server on the list of the matches of an empty folder, on a free port."""
    monkeypatch.setattr(app, "OUTPUTS", tmp_path)
    (tmp_path / "matches").mkdir()
    found = review_server.Server(tmp_path / "matches", "none", 0, tmp_path / "roster.json")
    threading.Thread(target=found.serve_forever, daemon=True).start()
    yield found
    found.shutdown()
    found.server_close()


def ask(server, method, path, body=None, headers=None):
    """The status, headers and body of `path` asked of `server`."""
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    connection.request(method, path, body, {"Content-Type": "application/json", **(headers or {})})
    got = connection.getresponse()
    return got.status, dict(got.getheaders()), got.read()


class TestServer:
    def test_is_quiet_when_a_page_goes_and_reports_any_other_error(self, server, capsys):
        for error in (BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()):
            try:
                raise error
            except OSError:
                server.handle_error(None, ("127.0.0.1", 1))
        assert capsys.readouterr().err == ""
        try:
            raise ValueError("bad answer")
        except ValueError:
            server.handle_error(None, ("127.0.0.1", 1))
        assert "bad answer" in capsys.readouterr().err

    def test_each_page_answers_with_and_without_a_trailing_slash(self, server):
        for path, there in (("/matches?x=1", "/matches/?x=1"), ("/review/", "/review"), ("/page/", "/page"), ("/", "/matches/"), ("/review", "/matches/")):
            status, headers, _ = ask(server, "GET", path)
            assert (status, headers["Location"]) == (302, there)

    def test_without_a_match_it_serves_the_list(self, server):
        assert json.loads(ask(server, "GET", "/current")[2]) == {"name": None}
        status, headers, _ = ask(server, "GET", "/matches/")
        assert status == 200 and headers["Content-Type"].startswith("text/html")
        assert ask(server, "GET", "/nothing")[0] == 404

    def test_opens_only_a_match_of_the_list(self, server):
        status, _, body = ask(server, "POST", "/open", json.dumps({"name": "none"}))
        assert (status, json.loads(body)) == (400, {"error": "no such match"})
        assert ask(server, "POST", "/open", "{")[0] == 400

    def test_refuses_another_site_and_what_needs_a_match(self, server):
        assert ask(server, "GET", "/current", headers={"Host": "evil.example:80"})[0] == 403
        assert ask(server, "POST", "/open", "{}", {"Origin": "http://evil.example"})[0] == 403
        assert ask(server, "POST", "/open", "{}", {"Content-Type": "text/plain"})[0] == 403
        assert ask(server, "POST", "/answer", "{}")[0] == 403
        assert ask(server, "POST", "/open", "{}", {"Content-Length": str(review_server.MAX_BODY + 1)})[0] == 413


class FakeReview:
    """A review that opens at once: the server's switching alone is tested."""

    def __init__(self, match, *_):
        self.match, self.lock, self.progress, self.closed, self.started = match, threading.Lock(), {}, False, False

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def get(self, path, query):
        return review_server.reply({"match": self.match.name})

    def app_context(self):
        return {"open_match": self.match.name}


@pytest.fixture
def two(server, monkeypatch):
    """Two ready matches in the server's list, opened as FakeReviews; `gate` holds an opening until set."""
    gate = threading.Event()
    gate.set()

    def read(match, *args):
        gate.wait()
        if match.name == "broken":
            raise ValueError("no video")
        if match.name == "exits":
            raise SystemExit("unknown theme")
        return FakeReview(match)

    monkeypatch.setattr(review_server, "read_review", read)
    monkeypatch.setattr(review_server, "openable", lambda out, name: out / name)
    server.gate = gate
    return server


def opened(server, name):
    """Asks `server` to open `name`, then waits until it no longer opens."""
    status, _, body = ask(server, "POST", "/open", json.dumps({"name": name}))
    assert (status, json.loads(body)) == (200, {})
    for _ in range(200):
        if not server.opening:
            return
        time.sleep(0.01)
    raise AssertionError("still opening")


class TestSwitch:
    def test_opens_one_match_then_another_in_the_same_process(self, two):
        opened(two, "a")
        first = two.review
        assert first.started and json.loads(ask(two, "GET", "/current")[2]) == {"name": "a"}
        assert json.loads(ask(two, "GET", "/anything")[2]) == {"match": "a"}

        opened(two, "b")

        assert first.closed and two.review.match.name == "b" and two.review.started
        assert json.loads(ask(two, "GET", "/current")[2]) == {"name": "b"}

    def test_answers_busy_while_a_match_opens(self, two):
        two.gate.clear()
        assert ask(two, "POST", "/open", json.dumps({"name": "a"}))[0] == 200
        try:
            status, _, body = ask(two, "GET", "/current")
            assert (status, json.loads(body)) == (503, {"opening": "a"})
            assert ask(two, "GET", "/review.js")[0] == 503
            assert ask(two, "POST", "/answer", "{}")[0] == 503
            assert ask(two, "POST", "/open", json.dumps({"name": "b"}))[0] == 409
            assert not two.may_stop()
        finally:
            two.gate.set()

    def test_shows_the_list_when_a_match_fails_to_open(self, two):
        opened(two, "a")
        opened(two, "broken")

        assert two.review is None
        assert json.loads(ask(two, "GET", "/current")[2]) == {"name": None, "failed": "broken"}
        opened(two, "exits")
        assert json.loads(ask(two, "GET", "/current")[2]) == {"name": None, "failed": "exits"}

    def test_starts_again_on_the_match_open_now(self, two, monkeypatch):
        assert "--with-window" not in two.arguments() and str(two.out / "a") not in two.arguments()
        opened(two, "a")
        monkeypatch.setattr(presence, "ON", True)

        args = two.arguments()

        assert args[0] == str(two.out / "a") and "--no-browser" in args and "--with-window" in args


class TestMatchList:
    @staticmethod
    def folder(out, name, date, finished=True):
        (out / name).mkdir(parents=True)
        video, court = out / f"{name}.mp4", out / f"{name}.json"
        video.touch()
        court.touch()
        files.write_source(out / name, video, court)
        (out / name / "teams.json").write_text(json.dumps({"date": date, "teams": [{"name": "A", "colour": None}, {"name": "B", "colour": None}], "scores": ["25-20", None]}), encoding="utf-8")
        if finished:
            (out / name / "report.md").touch()

    def test_lists_the_matches_with_a_source_newest_first_and_which_are_finished(self, tmp_path):
        self.folder(tmp_path, "old", "2026-10-29")
        self.folder(tmp_path, "new", "2026-11-02", finished=False)
        (tmp_path / "bench").mkdir()

        listed = match_list(tmp_path)

        assert [(m["path"], m["ready"]) for m in listed] == [("new", False), ("old", True)]
        assert listed[0]["sets"] == 1 and listed[0]["rallies"] == 0

    def test_a_match_whose_video_is_gone_is_not_ready(self, tmp_path):
        self.folder(tmp_path, "m", "2026-10-29")
        (tmp_path / "m.mp4").unlink()

        assert not match_list(tmp_path)[0]["ready"]

    def test_opens_only_a_finished_match_of_the_list(self, tmp_path):
        self.folder(tmp_path, "done", "2026-10-29")
        self.folder(tmp_path, "running", "2026-11-02", finished=False)

        assert openable(tmp_path, "done") == tmp_path / "done"
        for name in ("running", "nothing", "../done"):
            with pytest.raises(LookupError):
                openable(tmp_path, name)

    def test_the_page_lists_them_for_the_review_and_serves_only_its_own_files(self, tmp_path):
        self.folder(tmp_path, "m", "2026-10-29")

        html, kind = list_page("/matches/", tmp_path, "none")

        assert b"matches.js" in html and kind.startswith("text/html")
        body, _ = list_page("/matches/matches.js", tmp_path, "none")
        assert b'"review": true' in body and b'"path": "m"' in body
        assert list_page("/matches/../../secret", tmp_path, "none") is None
        assert list_page("/matches/nothing.js", tmp_path, "none") is None
        assert list_page("/matches/../secret/data.js", tmp_path, "none") is None
        assert list_page("/matches/m/data.js", tmp_path, "none") is None
        (tmp_path / "m" / "review").mkdir()
        (tmp_path / "m" / "review" / "data.js").write_text("window.MATCH = {};", encoding="utf-8")
        assert list_page("/matches/m/data.js", tmp_path, "none")[0] == b"window.MATCH = {};"
        assert list_page("/matches/other/data.js", tmp_path, "none") is None

    def test_the_server_s_matches_come_apart_and_only_for_a_machine_keeping_its_matches_there(self, tmp_path, monkeypatch):
        out = tmp_path / "matches"
        self.folder(out, "m", "2026-10-29")
        reached = []
        monkeypatch.setattr("volleyball_stats.sync.listing", lambda outputs: reached.append(outputs) or {"m": {}, "2026-11-02-x": {}})

        list_page("/matches/", out, "none")
        assert json.loads(list_page("/matches/remote.json", out, "none")[0]) == []
        assert not reached
        (tmp_path / "server.json").write_text("{}", encoding="utf-8")
        found = json.loads(list_page("/matches/remote.json", out, "none")[0])

        assert [(m["path"], m["date"], m["remote"]) for m in found] == [("2026-11-02-x", "2026-11-02", True)]


class TestRange:
    def test_reads_byte_ranges_for_the_video_to_seek(self):
        assert range_of("bytes=0-99", 1000) == (0, 99)
        assert range_of("bytes=500-", 1000) == (500, 999)
        assert range_of("bytes=-100", 1000) == (900, 999)
        assert range_of("bytes=0-5000", 1000) == (0, 999)

    def test_has_no_range_without_a_header_or_past_the_end(self):
        assert range_of(None, 1000) is None
        assert range_of("bytes=2000-", 1000) is None


class TestWithReview:
    def test_loads_review_js_after_data_js_with_or_without_its_hash(self):
        for src in ("data.js", "data.js?v=1b236973b3"):
            html = f'<script defer src="{src}"></script><script defer src="./assets/index.js"></script>'

            assert with_review(html) == f'<script defer src="{src}"></script><script defer src="review.js"></script><script defer src="./assets/index.js"></script>'
