import hashlib
import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest

from volleyball_stats import app, hosted, netlify


class Netlify:
    """Netlify's API as the app uses it: OAuth tickets, sites, file digest deploys. `taken` site names answer 422, `fail`
    the next N requests with 500, `token` the one accepted."""

    def __init__(self):
        self.tickets, self.sites, self.deploys, self.stored = {}, {}, {}, {}
        self.taken, self.fail, self.token, self.puts, self.calls = set(), 0, "secret", [], []

    def answer(self, handler: BaseHTTPRequestHandler):
        path, _, query = handler.path.removeprefix("/api/v1").partition("?")
        body = handler.rfile.read(int(handler.headers.get("Content-Length") or 0))
        self.calls.append((handler.command, path, handler.headers.get("User-Agent")))
        if self.fail:
            self.fail -= 1
            return 500, {"message": "down"}
        method, parts = handler.command, path.strip("/").split("/")
        if parts[:2] == ["oauth", "tickets"]:
            if method == "POST" and len(parts) == 2:
                assert query == "client_id=app-id"
                ticket = f"t{len(self.tickets)}"
                self.tickets[ticket] = False
                return 201, {"id": ticket, "authorized": False}
            if parts[2] not in self.tickets:
                return 404, {"message": "Not Found"}
            if len(parts) == 4:
                return (201, {"access_token": self.token}) if self.tickets[parts[2]] else (401, {"message": "no"})
            return 200, {"id": parts[2], "authorized": self.tickets[parts[2]]}
        if handler.headers.get("Authorization") != f"Bearer {self.token}":
            return 401, {"message": "Access Denied"}
        if method == "POST" and parts == ["sites"]:
            name = json.loads(body)["name"]
            if name in self.taken or any(s["name"] == name for s in self.sites.values()):
                return 422, {"message": "subdomain must be unique"}
            site = {"id": f"s{len(self.sites)}", "name": name, "url": f"http://{name}.netlify.app", "ssl_url": f"https://{name}.netlify.app"}
            self.sites[site["id"]] = site
            return 201, site
        if method == "POST" and parts[0] == "sites" and parts[2:] == ["deploys"]:
            files = json.loads(body)["files"]
            deploy = {"id": f"d{len(self.deploys)}", "state": "preparing", "files": files, "polls": 0}
            self.deploys[deploy["id"]] = deploy
            return 200, {"id": deploy["id"], "state": "preparing", "required": None}
        if parts[0] == "deploys":
            deploy = self.deploys[parts[1]]
            if method == "PUT":
                path = "/" + "/".join(parts[3:])
                assert hashlib.sha1(body).hexdigest() == deploy["files"][path]
                self.stored[deploy["files"][path]] = body
                self.puts.append(path)
                return 200, {}
            deploy["polls"] += 1
            required = sorted({d for d in deploy["files"].values() if d not in self.stored})
            if deploy["state"] == "preparing":
                deploy["state"] = "prepared"
            elif deploy["state"] == "prepared" and not required:
                deploy["state"] = "ready"
            return 200, {"id": deploy["id"], "state": deploy["state"], "required": required}
        return 404, {"message": "Not Found"}


@pytest.fixture
def api(monkeypatch):
    fake = Netlify()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_one(self):
            status, data = fake.answer(self)
            text = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(text)))
            self.end_headers()
            self.wfile.write(text)

        do_GET = do_POST = do_PUT = handle_one

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(netlify, "API", f"http://127.0.0.1:{server.server_port}/api/v1")
    monkeypatch.setattr(netlify, "CLIENT_ID", "app-id")
    monkeypatch.setattr(netlify, "POLL_S", 0.0)
    monkeypatch.setattr(netlify.time, "sleep", lambda s: None)
    monkeypatch.setattr(netlify, "ready", lambda outputs: [])
    yield fake
    server.shutdown()


def test_signs_in_through_a_ticket_and_makes_the_site_named_after_the_club(tmp_path, api, monkeypatch):
    monkeypatch.setattr(netlify, "club_name", lambda outputs: "ASPOM Bègles")
    api.taken.add("aspom-begles-stats")
    assert netlify.state(tmp_path)["url"] is None
    page = netlify.connect(tmp_path)
    assert page.endswith("/authorize?response_type=ticket&ticket=t0")
    # Until the user consents on Netlify's page.
    waiting = netlify.state(tmp_path)
    assert waiting["connecting"] and waiting["url"] is None
    api.tickets["t0"] = True
    signed = netlify.state(tmp_path)
    (site,) = api.sites.values()
    assert site["name"].startswith("aspom-begles-stats-") and signed["url"] == f"https://{site['name']}.netlify.app/" and not signed["connecting"]
    assert netlify.account(tmp_path)["token"] == "secret"
    # A generic client, nothing of the user's.
    assert {agent for *_, agent in api.calls} == {"volleyball-stats"}
    netlify.disconnect(tmp_path)
    assert netlify.state(tmp_path)["url"] is None and not (tmp_path / "netlify").exists()


def test_no_sign_in_without_the_apps_client_id(tmp_path, api, monkeypatch):
    monkeypatch.setattr(netlify, "CLIENT_ID", "")
    assert not netlify.state(tmp_path)["available"]
    with pytest.raises(LookupError):
        netlify.connect(tmp_path)


def test_a_ticket_netlify_forgot_starts_again(tmp_path, api):
    netlify.write(tmp_path / "netlify" / netlify.ACCOUNT, json.dumps({"ticket": "gone"}))
    assert not netlify.state(tmp_path)["connecting"]
    assert not (tmp_path / "netlify" / netlify.ACCOUNT).exists()


def test_retries_a_servers_error_and_tells_a_refused_token(api):
    api.fail = 2
    assert netlify.request("POST", "/oauth/tickets?client_id=app-id")["id"] == "t0"
    api.fail = netlify.TRIES
    with pytest.raises(RuntimeError, match="netlify 500: down"):
        netlify.request("POST", "/oauth/tickets?client_id=app-id")
    with pytest.raises(PermissionError):
        netlify.request("GET", "/deploys/d0", "wrong")


def test_network_down(monkeypatch):
    def unreachable(*args, **kwargs):
        raise netlify.urllib.error.URLError("refused")

    monkeypatch.setattr(netlify.urllib.request, "urlopen", unreachable)
    monkeypatch.setattr(netlify.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="^network$"):
        netlify.request("GET", "/sites")


def test_deploys_the_whole_site_sending_only_what_netlify_lacks(tmp_path, api):
    site = tmp_path / "site"
    (site / "a").mkdir(parents=True)
    (site / "index.html").write_text("list")
    (site / "index.html.gz").write_bytes(b"gz")
    (site / "a" / "data.js").write_text("one")
    (site / "a" / "same.js").write_text("one")
    shares = []
    assert netlify.deploy("secret", "s0", site, shares.append)["state"] == "ready"
    assert api.deploys["d0"]["files"].keys() == {"/index.html", "/a/data.js", "/a/same.js"}
    # One file per content, its bytes counted.
    assert len(api.puts) == 2 and shares[-1] == 1.0 and shares == sorted(shares)
    (site / "a" / "data.js").write_text("two")
    netlify.deploy("secret", "s0", site)
    assert api.puts[2:] == ["/a/data.js"]


def test_qr_code_reads_back():
    image = cv2.imdecode(np.frombuffer(netlify.qr("https://club-stats.netlify.app/"), np.uint8), cv2.IMREAD_GRAYSCALE)
    assert cv2.QRCodeDetector().detectAndDecode(image)[0] == "https://club-stats.netlify.app/"


def test_counts_the_deploys_of_the_last_30_days():
    now = datetime(2026, 11, 26)
    found = {"deploys": [(now - timedelta(days=d)).isoformat() for d in (1, 10, 29, 31, 50)]}
    assert netlify.recent_deploys(found, now) == 3


class TestPages:
    @pytest.fixture
    def match(self, tmp_path, monkeypatch):
        match = tmp_path / "outputs" / "matches" / "m"
        (match / "review").mkdir(parents=True)
        (match / "review" / "data.js").write_text("x")
        page = {"data": {"rallies": 3}}
        monkeypatch.setattr(hosted, "page_stamp", lambda m: json.dumps(page["data"]))
        monkeypatch.setattr(hosted, "page_content", lambda m: json.loads(json.dumps(page)))
        monkeypatch.setattr(hosted, "sent_page", lambda m, taken: taken)
        monkeypatch.setattr(hosted, "site_code", lambda site: {"behind": False, "change": None})
        return match, page

    def test_late_once_the_match_changed_then_up_to_date(self, match):
        match, page = match
        outputs = match.parent.parent
        assert netlify.page_state(outputs, match, netlify.published(outputs), None, None)["new"]
        netlify.record(outputs, {match: hosted.page_taken(match)})
        done = netlify.published(outputs)
        assert len(done["deploys"]) == 1 and not netlify.page_state(outputs, match, done, None, None)["behind"]
        page["data"]["rallies"] = 4
        late = netlify.page_state(outputs, match, done, None, None)
        assert late["behind"] and late["changes"]
        netlify.record(outputs, {match: hosted.page_taken(match)})
        assert not netlify.page_state(outputs, match, netlify.published(outputs), None, None)["behind"]

    def test_late_when_the_sites_code_is(self, match):
        match, _ = match
        outputs = match.parent.parent
        netlify.record(outputs, {match: hosted.page_taken(match)})
        late = netlify.page_state(outputs, match, netlify.published(outputs), None, {"behind": True, "change": {"part": "code", "keys": ["page"]}})
        assert late["behind"] and late["changes"][-1]["part"] == "siteCode"

    def test_publishes_then_records_the_matches(self, match, api, monkeypatch):
        match, _ = match
        outputs = match.parent.parent
        netlify.write(outputs / "netlify" / netlify.ACCOUNT, json.dumps({"token": "secret", "site": "s0", "url": "https://x.netlify.app/"}))
        monkeypatch.setattr(netlify, "ready", lambda o: [(match, Path("v.mp4"), Path("c.json"), {})])

        def build(outputs, chosen, theme, url, told):
            (netlify.folder(outputs) / netlify.SITE / "m").mkdir(parents=True)
            (netlify.folder(outputs) / netlify.SITE / "m" / "data.js").write_text("page")

        monkeypatch.setattr(netlify, "build", build)
        with pytest.raises(LookupError):
            netlify.publish(outputs, ["other"])
        netlify.publish(outputs, ["m"])
        assert api.puts == ["/m/data.js"] and "m" in netlify.published(outputs)["matches"]

    def test_never_deploys_a_video(self, tmp_path, monkeypatch):
        site = tmp_path / "netlify" / netlify.SITE
        (site / "m" / "video").mkdir(parents=True)
        (site / "m" / "data.js").write_text("x")
        (site / "old.mp4").write_bytes(b"v")
        for name in ("build", "write_code"):
            monkeypatch.setattr(netlify.matches, name, lambda *a, **k: None)
        monkeypatch.setattr(netlify.matches, "page_format", lambda p: 0)
        monkeypatch.setattr(netlify.matches, "unguarded_videos", lambda site: [])

        class Told:
            share_of_stage = staticmethod(lambda s: None)

        with pytest.raises(RuntimeError, match="old.mp4"):
            netlify.build(tmp_path, [], "club", "https://x/", Told())


def test_app_starts_the_publish_of_ready_matches_only(tmp_path, api, monkeypatch):
    monkeypatch.setattr(app, "OUTPUTS", tmp_path)
    monkeypatch.setattr(netlify, "ready", lambda outputs: [(tmp_path / "matches" / "one", None, None, {})])
    started = []
    monkeypatch.setattr(app.jobs, "start", lambda outputs, job_id, kind, steps: started.append(steps[0][1]))
    for wrong in (["two"], [], "one"):
        assert app.handle("POST", "/app/netlify/publish", "", {"matches": wrong}, list)[2] == 400
    assert app.handle("POST", "/app/netlify/publish", "", {"matches": ["one"]}, list)[2] == 200
    assert started == [["volleyball_stats.netlify", "--outputs", str(tmp_path), "one"]]
    # No QR code before the site.
    assert app.handle("GET", "/app/netlify/qr", "", {}, list)[2] == 404
