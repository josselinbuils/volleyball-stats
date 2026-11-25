import http.client
import json
import threading

import pytest

from volleyball_stats import app, review_server


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
        for error in (BrokenPipeError(), ConnectionResetError()):
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
