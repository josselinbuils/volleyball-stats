"""The review's server: the list of the matches, and a match's review once one is open (`Review`), on this machine only
unless the app opens it to the local network (`network`). Opening another match starts the process again on it: everything
is read again, with the code as it now is.

    uv run python -m volleyball_stats.review_server [MATCH] [--outputs DIR] [--theme NAME] [--roster PATH] [--port PORT]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs, unquote, urlparse

import cv2

from volleyball_stats import app, applog, decode, feedback, film, files, git_check, hosted, identity, jobs, matches, network, presence, rename, sync, timeouts, web
from volleyball_stats.review import (
    APPLIED,
    CROP_MARGIN,
    CROP_PX,
    ROSTER,
    STALE_PHOTOS,
    TIMINGS,
    TOOK,
    Questions,
    applied_too,
    checked,
    commented,
    constraints,
    due,
    eta,
    follow_teams,
    given_sets,
    load_log,
    load_roster,
    locked,
    mark_odd,
    name_absent,
    name_merges,
    page_data,
    piece_conflict,
    piece_key,
    pinned,
    rally_answer,
    read_comments,
    reanchor,
    receiver_answer,
    remember,
    report_answer,
    save,
    set_end,
    set_look,
    set_name,
    set_photo,
    set_start,
    set_team,
    settled,
    state,
    supersede,
    superseded,
    touch_answer,
    undo,
    unlocked,
    waiting,
    write_comments,
    write_names,
)
from volleyball_stats.teams import given_end, match_end

PORT = 8765
# 4K readers at once in the server, its pictures and its new cards' together: about 1 GB each; 7 at once beside another job
# froze the PC (15 Nov).
READERS = 2
# Undo takes back the UNDOS latest of the CHANGES whole, then drops the last answer. Request bodies
# are at most MAX_BODY bytes.
UNDOS, MAX_BODY = 100, 1 << 20
CHANGES = ("/answer", "/odd", "/more", "/repin", "/forget", "/cut", "/separate")
# The club carries its pictures.
CLUB_BODY = 16 << 20
# Where the review's copy of the match page keeps the reports of what is wrong in a moment.
FEEDBACK = "feedback.log"
BACKUP_EVERY_S = 600
FILE_KINDS = {".js": "text/javascript", ".css": "text/css", ".mp4": "video/mp4", ".mov": "video/quicktime", ".webp": "image/webp", ".png": "image/png"}
# Each page's other spelling, with or without a trailing slash, and the page's own: its files are relative to it.
SPELLINGS = {"/matches": "/matches/", "/review/": "/review", "/page/": "/page"}
# The parts of the online page's state a change of the review's page moves (`hosted.read_hosted`).
PAGE_STATE = ("behind", "changes", "copiesStale")


class Reply(NamedTuple):
    """A response: its body (a file goes by byte ranges, its type guessed when `kind` is empty), its type and status, where
    it sends the browser on (a 302), and what to do once it has left."""

    body: bytes | Path
    kind: str = "application/json"
    status: int = 200
    then: Callable[[], None] | None = None
    location: str | None = None


def reply(data, status: int = 200, then: Callable[[], None] | None = None) -> Reply:
    return Reply(json.dumps(data).encode(), "application/json", status, then)


def failed(error: BaseException, status: int) -> Reply:
    return reply({"error": str(error) or type(error).__name__}, status)


NOT_FOUND = Reply(b"Not found", "text/plain", 404)
FORBIDDEN = Reply(b"", "text/plain", 403)


def moved(location: str) -> Reply:
    return Reply(b"", "text/plain", 302, location=location)


def with_review(html: str) -> str:
    """The page loading review.js right after data.js (its build hash in the query or not), before
    the app that reads both."""
    return re.sub(r'(<script defer [^>]*src="data\.js[^"]*"></script>)', r'\1<script defer src="review.js"></script>', html, count=1)


def send_file(handler, path: Path, kind: str | None = None) -> None:
    """A file by byte ranges, for a video to seek: `handler` a request's (BaseHTTPRequestHandler)."""
    size = path.stat().st_size
    span = range_of(handler.headers.get("Range"), size)
    first, last = span or (0, size - 1)
    handler.send_response(206 if span else 200)
    handler.send_header("Content-Type", kind or FILE_KINDS.get(path.suffix.lower(), "application/octet-stream"))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(last - first + 1))
    # An apply rewrites the page's data under the same names.
    if path.suffix.lower() == ".js":
        handler.send_header("Cache-Control", "no-cache")
    if span:
        handler.send_header("Content-Range", f"bytes {first}-{last}/{size}")
    handler.end_headers()
    with open(path, "rb") as f:
        f.seek(first)
        left = last - first + 1
        try:
            while left > 0:
                chunk = f.read(min(left, 1 << 20))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def range_of(header: str | None, size: int) -> tuple[int, int] | None:
    """(first, last) byte of a "bytes=a-b" Range header, None without one or when unsatisfiable."""
    if not header or not header.startswith("bytes="):
        return None
    a, _, b = header[6:].split(",")[0].partition("-")
    first, last = (size - int(b), size - 1) if not a else (int(a), int(b) if b else size - 1)
    return (max(0, first), min(last, size - 1)) if first < size else None


def match_list(out: Path) -> list[dict]:
    """The matches of `out` that have a SOURCE, newest first, as the hosted list shows them, by their folder's name; `ready` once
    their pipeline has ended and their files are there."""
    found = []
    for source in out.glob(f"*/{files.SOURCE}"):
        folder, given = source.parent, json.loads(source.read_text())
        if (folder / "review" / "data.js").exists():
            item = matches.listed(folder / "review")
        else:
            saved = files.read_json(folder / "teams.json", {})
            scores = saved.get("scores") or []
            item = {"name": folder.name, "date": saved.get("date"), "title": saved.get("title"), "teams": saved.get("teams"), "scores": scores, "sets": sum(map(bool, scores)), "rallies": 0}
        item["path"] = folder.name
        item["ready"] = all(p.exists() for p in (folder / "report.md", Path(given["video"]), Path(given["court"])))
        if item["ready"]:
            item["due"] = due(folder)
        if not Path(given["video"]).exists():
            item["missing"] = "video"
        elif not Path(given["court"]).exists() and (folder / "report.md").exists():
            item["missing"] = "court"
        found.append(item)
    return sorted(found, key=lambda m: (m["date"] or "", m["path"]), reverse=True)


def on_server(out: Path, listed: list[dict]) -> list[dict]:
    """The matches with a copy on the server and none here, to download; none when the server cannot be reached."""
    try:
        found = sync.listing(out.parent)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return []
    here = {m["path"] for m in listed}
    dated = lambda name: name[:10] if re.match(r"\d{4}-\d{2}-\d{2}", name) else None  # noqa: E731
    return [{"name": n, "path": n, "date": dated(n), "title": None, "teams": None, "scores": [], "sets": 0, "rallies": 0, "ready": False, "remote": True} for n in sorted(found) if n not in here]


def list_page(path: str, out: Path, theme: str) -> tuple[bytes, str] | None:
    """The response to `path` under /matches/, the hosted list's page for the matches of `out`; None when there is no such file."""
    site = out / ".review_matches"
    if path == "/matches/":
        shutil.rmtree(site, ignore_errors=True)
        shutil.copytree(matches.TEMPLATE, site)
        club = web.club_page(theme, site)
        if club:
            club.pop("sponsors")
        # The server's matches come after (`/matches/remote.json`): reaching it takes a second, or ssh's timeout.
        listed = match_list(out)
        (site / "matches.js").write_text(f"window.MATCHES = {json.dumps({'matches': listed, 'club': club, 'review': True}, ensure_ascii=False)};\n")
        return (site / "matches.html").read_bytes(), "text/html; charset=utf-8"
    if path == "/matches/remote.json":
        found = on_server(out, match_list(out)) if sync.active(out.parent) else []
        return json.dumps(found, ensure_ascii=False).encode(), "application/json"
    parts = Path(unquote(path).removeprefix("/matches/")).parts
    file = site.joinpath(*parts)
    # The season reads each match's data.
    if len(parts) == 2 and parts[1] == "data.js" and (out / parts[0] / files.SOURCE).exists():
        file = out / parts[0] / "review" / "data.js"
    if ".." in parts or not file.is_file():
        return None
    kinds = {".js": "text/javascript", ".css": "text/css", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml"}
    return file.read_bytes(), kinds.get(file.suffix.lower(), "application/octet-stream")


def reopening(name: str, out: Path, theme: str, port: int, roster: Path) -> list[str]:
    """The command opening the review on the match `name`, one of `match_list`'s ready ones; LookupError otherwise."""
    if not any(m["path"] == name and m["ready"] for m in match_list(out)):
        raise LookupError(name)
    return [sys.executable, "-m", "volleyball_stats.review_server", str(out / name), "--outputs", str(out), "--theme", theme, "--port", str(port), "--roster", str(roster), "--no-browser", *(["--with-window"] if presence.ON else [])]


class Busy(Exception):
    """A request that would wait on the review's run until it ends: refused instead."""


def switch(command: list[str], lock: threading.Lock) -> None:
    """Replaces this server by `command`, once the response on its way has left and no answer is being saved."""

    def replace() -> None:
        time.sleep(0.2)
        lock.acquire()
        os.execv(command[0], command)

    threading.Thread(target=replace, daemon=True).start()


def pulled(body, out: Path) -> Reply:
    """The response to /pull: the match `name` brought from the server."""
    try:
        sync.pull(str(body["name"]), out.parent)
    except (LookupError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        return failed(error, 400)
    return reply({})


def same_site(headers, port: int, lan: bool = False) -> bool:
    """Whether a request comes from this server's own pages: named by 127.0.0.1 or localhost, else with `lan` by this
    machine's address on the local network (`network.named_here`), and from no other site."""
    host = headers.get("Host", "")
    return (
        network.named_here(host, port, lan)
        and headers.get("Origin") in (None, f"http://{host}")
        and headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")
    )


def network_route(method: str, path: str, body: dict, port: int) -> Reply | None:
    """The app's "Réseau local": GET /app/network its state (`network.state`); POST it switched (`on`: the server
    starts again to listen so, `network_restart`), kept from every start (`action` "always", `on`) or Windows set up for
    it (`action` "windows"). None for another path."""
    if path != "/app/network":
        return None
    if method == "POST":
        try:
            if body.get("action") == "windows":
                network.configure_windows(port)
            elif body.get("action") == "always":
                network.keep(app.OUTPUTS, bool(body.get("on")))
            else:
                network.share(app.OUTPUTS, bool(body.get("on")))
        except (OSError, subprocess.SubprocessError) as error:
            return failed(error, 500)
    return reply(network.state(app.OUTPUTS, port))


def network_restart(path: str, body: dict, answer: tuple, lock=None) -> None:
    """The server started again once the switch's answer has left: it listens on the network, or no longer."""
    if path == "/app/network" and answer[2] == 200 and body.get("action") is None:
        app.restart_after(lock)


def backing_all(outputs: Path) -> None:
    """While the copies are automatic and no match is open: every match changed here sent and what sits beside them kept in
    step, as the Site tab's job (`app.start_backup`: it shows there, and neither starts while the other runs), the copies
    checked once a week (`sync.verify`)."""
    while True:
        if sync.server(outputs) and sync.auto(outputs) and not jobs.is_running(app.OUTPUTS, app.BACKUP):
            try:
                app.start_backup(auto=True)
                while jobs.is_running(app.OUTPUTS, app.BACKUP):
                    time.sleep(2)
                sync.verify_weekly(outputs)
            except (jobs.Running, OSError, RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
                print(f"backup failed: {error}", flush=True)
        time.sleep(BACKUP_EVERY_S)


@dataclass
class Edit:
    """The answers' log as the request to `path` changes it, from `before`; the names to write (`renamed`, those it replaces for undo
    `names_before`), and what an undo took away (`undone`, `undo_applied`: an apply had followed it)."""

    path: str
    log: list[dict]
    before: list[dict]
    renamed: list[dict] | None = None
    names_before: list[dict] | None = None
    undone: str | None = None
    undo_applied: bool = False


class Review:
    """A match open in the review: its page built, its questions, the answers' runs one at a time (`lock`, `run_steps`) and
    what they leave for later (the players' pictures), its copies on the server, its upload."""

    def __init__(self, match: Path, video: Path, court: Path, squad, theme: str, port: int, roster: Path) -> None:
        self.match, self.video, self.court, self.squad, self.theme, self.port, self.roster = match, video, court, squad, theme, port, roster
        # First the server's newer copy, if nothing changed here (`sync.check`); changed on both sides, the page asks which to keep.
        conflict = sync.check(match) if sync.active(files.root(match)) else None
        matches.ensure_publish(match, video, theme)
        self.site = match / "review"
        # Open at once: the pictures follow (`afterwards`), minutes if their scores are out of date.
        before = hosted.page_stamp(match) if (self.site / "data.js").exists() else None
        web.review_page(match, video, court, theme, pictures=False)
        hosted.restamp(match, before)
        (match / STALE_PHOTOS).touch()
        cap = cv2.VideoCapture(str(video))
        self.fps, self.width, self.height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.answers = match / "identity_answers.json"
        # The answers the review's page was last built with: it shows their corrections.
        self.shown = {e["id"] for e in load_log(self.answers)}
        if not (match / "identity_candidates.json").exists():
            identity.rerun(match, video, squad)
        self.questions = Questions(match, self.fps, court)
        self.pin_checked()
        self.computed = match / APPLIED
        done = match / "identities.csv"
        if not self.computed.exists() and done.exists() and all(not f.exists() or f.stat().st_mtime < done.stat().st_mtime for f in (self.answers, match / identity.NAMES)):
            files.write_text(self.computed, json.dumps(state(match, load_log(self.answers))))
        # The answers and names before each change since the server started, for undo (see `undo`).
        self.history: list[dict] = []
        self.lock = threading.Lock()
        # The review's data as the running run started, and the request that started it: a page opened meanwhile is
        # answered from them, not left waiting on `lock` until the run ends.
        self.at_start: dict = {"data": None, "action": None}
        # The reports sent from the review's copy of the match page, one at a time.
        self.reports_lock = threading.Lock()
        self.acting: str | None = None
        self.later = threading.Event()
        # Set while that work runs, for the app not to stop under it.
        self.after_apply = threading.Event()
        self.generation = 0
        self.stale_photos = match / STALE_PHOTOS
        # Why the last new pictures failed, until the next build.
        self.photos_error: str | None = None
        # Pictures are cut from the video by READERS at once, then kept on disk: a 4K seek costs 0.4 s.
        decode.limit_readers(READERS)
        self.kept = match / "crops"
        # Where an apply stands, for the page's progress bar: the steps, the one running since when and
        # its stage (the pipeline's). Each step's and stage's last duration ("STEP:STAGE"), kept per match
        # (TIMINGS) to outlive a restart, first guessed from the first ASPOM match.
        self.progress: dict = {}
        # The last run's failure until the user dismisses it: `step` and `error`.
        self.failure: dict = {}
        self.took = {**TOOK, **(files.read_json(match / TIMINGS, {}))}
        # The last hosting (publish.json): when, why it failed, and whether the page has changed since; the
        # page says it. The user puts the pages online ("/host"), an apply does not.
        self.online: dict = hosted.read_hosted(match)
        self.films_error: str | None = None
        # The last fetch of the viewers' reports from the hosting: when, and how many for this match.
        self.fetched: dict = {}
        # The last copy on the hosting server: when, why it failed.
        self.backed: dict = {"at": None, "error": None}
        self.outputs = files.root(match)
        publish = files.read_json(match / matches.PUBLISH, {})
        self.can_back_up = bool(publish.get("upload") and publish.get("key"))
        # The match changed both here and on another machine since this one's copy (`sync.check`, a push refused): the page
        # asks which to keep.
        self.elsewhere: dict = dict(conflict or {})
        self.backup_lock = threading.Lock()
        # The timer woken when automatic copies are switched on.
        self.wake = threading.Event()
        # The review's page as this server last wrote or read it: another one comes from the app's update.
        self.page_seen = self.page_mark()
        self.gets: dict[str, Callable[[dict], Reply]] = {
            "/review.js": self.get_data,
            "/photos": self.get_photos,
            "/progress": self.get_progress,
            "/failure": lambda q: reply(self.failure),
            "/sync": lambda q: reply(self.elsewhere or None),
            "/more": self.get_more,
            "/nearest": lambda q: reply(self.questions.nearest(int(q["f"][0]), q["type"][0])),
            "/crop": self.get_crop,
            "/review": lambda q: Reply(with_review((self.site / "index.html").read_text()).encode(), "text/html; charset=utf-8"),
            "/page": lambda q: Reply((self.site / "index.html").read_bytes(), "text/html; charset=utf-8"),
        }
        self.posts: dict[str, Callable[[dict], Reply]] = {
            "/failure": self.post_failure,
            "/backup": self.post_backup,
            "/autoBackup": self.post_auto_backup,
            "/sync/take": self.post_sync_take,
            "/sync/keep": self.post_sync_keep,
        }
        # Those changing the answers or the match's files, one at a time, never under the app's update: None goes on to
        # `commit`, which saves the log, keeps the change for undo and, for an apply, runs it.
        self.edits: dict[str, Callable[[Edit, dict], Reply | None]] = {
            "/photo": self.post_photo,
            "/look": self.post_look,
            "/end": self.post_end,
            "/team": self.post_team,
            "/name": self.post_name,
            "/comment": self.post_comment,
            "/pick": self.post_pick,
            "/timeout": self.post_timeout,
            "/answer": self.post_answer,
            "/odd": self.post_odd,
            "/more": self.post_more,
            "/repin": self.post_repin,
            "/forget": self.post_forget,
            "/separate": self.post_separate,
            "/cut": self.post_cut,
            "/reports": self.post_reports,
            "/host": self.post_host,
            "/hostAll": self.post_host_all,
            "/films": self.post_films,
            "/film": self.post_films,
            "/highlights": self.post_films,
            "/sets": self.post_sets,
            "/undo": self.post_undo,
        }

    def pin_checked(self) -> None:
        """The rallies checked before the winners were pinned: those their page shows. First in the log: an undo after a
        restart takes away the last answer."""
        log = load_log(self.answers)
        have = {p["start"] for e in log for p in e.get("pinned", [])}
        first = pinned(self.questions.page, [k for k in checked(log) if k not in have])
        if first:
            save(self.answers, first + log)
            print(f"{len(first[0]['pinned'])} winners of rallies checked pinned", flush=True)
            log = first + log
        have = {p["start"] for e in log for p in e.get("locked", [])}
        locks = locked(self.questions.page, [k for k in checked(log) if k not in have], identity.named(self.questions.table, identity.read_names(self.match)))
        if locks:
            save(self.answers, locks + log)
            applied_too(self.match, locks)
            print(f"{len(locks[0]['locked'])} rallies checked locked", flush=True)

    def start(self) -> None:
        """The work beside the requests: the pictures cut ahead, what applies leave for later, the copies, the reports."""
        threading.Thread(target=self.warm, daemon=True).start()
        threading.Thread(target=self.afterwards, daemon=True).start()
        if self.can_back_up:
            threading.Thread(target=self.backing, daemon=True).start()
        threading.Thread(target=feedback.watch, args=(self.outputs, self.reports_came), daemon=True).start()

    def may_stop(self) -> bool:
        """Never in an apply nor the work it leaves for later (the pictures), nor in a job."""
        return not self.progress and not self.later.is_set() and not self.after_apply.is_set() and not any(j["running"] for j in jobs.state(app.OUTPUTS))

    def app_context(self) -> dict:
        """What the app's requests (`app.handle`) know of the match open."""
        return {"busy": lambda: bool(self.progress), "club_changed": self.club_changed, "open_match": self.match.name, "review": self.review_task}

    def where(self, ref: dict):
        return identity.lookup(self.questions.table, ref["track"], ref["frame"])

    def waiting(self, log: list[dict]) -> dict:
        return waiting(self.match, log, self.shown)

    def answered(self, log: list[dict], rebuilt: bool = False, undone: str | None = None, **more) -> Reply:
        return reply({"answered": len(log), **self.waiting(log), "rebuilt": rebuilt, "undone": undone, **more})

    def page_changed(self) -> None:
        """The review's page written: whether the online one is late read again."""
        self.online.update({k: v for k, v in hosted.read_hosted(self.match).items() if k in PAGE_STATE})

    def picture(self, frame: int, box: tuple[int, int, int, int]) -> bytes:
        path = self.kept / f"{CROP_PX}_{frame}_{'_'.join(map(str, box))}.jpg"
        if path.exists():
            return path.read_bytes()
        with decode.reader():
            image = decode.frame_at(self.video, frame)
        if image is None:
            return b""
        x1, y1, x2, y2 = box
        mx, my = round((x2 - x1) * CROP_MARGIN), round((y2 - y1) * CROP_MARGIN)
        part = image[max(0, y1 - my) : max(0, y2 + my), max(0, x1 - mx) : max(0, x2 + mx)]
        if not part.size:
            return b""
        part = cv2.resize(part, (max(1, round(part.shape[1] * CROP_PX / part.shape[0])), CROP_PX), interpolation=cv2.INTER_CUBIC)
        body = cv2.imencode(".jpg", part, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
        self.kept.mkdir(exist_ok=True)
        files.write_bytes(path, body)
        return body

    def backup_state(self) -> dict | None:
        """What the page shows of the copies on the server; None without one."""
        return {**self.backed, "auto": sync.auto(self.outputs)} if self.can_back_up else None

    def back_up(self) -> bool:
        """A copy on the hosting server now, its time or failure for the page; whether it was made. One at a time: the page
        can ask for one while the timer makes another."""
        with self.backup_lock:
            try:
                sync.push(self.match)
                self.backed.update(at=time.strftime("%H:%M"), error=None)
                return True
            except sync.Conflict as error:
                self.elsewhere.update(error.claim)
                self.backed.update(at=time.strftime("%H:%M"), error=str(error))
                return False
            except (OSError, RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
                self.backed.update(at=time.strftime("%H:%M"), error=str(error) or type(error).__name__)
                print(f"backup failed: {self.backed['error']}", flush=True)
                return False

    def backing(self) -> None:
        """While the copies are automatic: the match sent whenever it changed here since it was last sent or brought
        (`sync.changed`), else what sits beside it kept in step (`sync.keep_shared`): a change there alone moves no
        match's version."""
        while True:
            # A copy of a match (a test's) reaches no server: it would send itself as this machine's (`sync.own`). None
            # while the Site tab's backup still runs.
            if sync.auto(self.outputs) and sync.own(self.match) and not jobs.is_running(app.OUTPUTS, app.BACKUP):
                try:
                    if sync.changed(self.match):
                        self.back_up()
                    else:
                        config = sync.server(self.outputs)
                        if config:
                            sync.keep_shared(self.outputs, config)
                except OSError:
                    # A file gone while it was read: the next round reads them again.
                    pass
                except (RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
                    print(f"backup failed: {error}", flush=True)
            self.wake.wait(BACKUP_EVERY_S)
            self.wake.clear()

    def hosting(self, every: bool = False) -> None:
        """This match put online, or with `every` all the matches online, rebuilt then uploaded at once."""
        match = self.match
        try:
            target = ["--all", str(match.parent)] if every else ["--host", str(match), "--video", str(self.video), "--court", str(self.court)]
            done = [m for m, *_ in matches.online(match.parent)] if every else [match]
            # Those newer on the server are left as they are online (`matches.main`).
            newer = sync.behind(done)
            done = [m for m in done if m.name not in newer]
            # Each page as the upload begins: a change made while it runs stays late.
            taken = {m: hosted.page_taken(m) for m in done if (m / "review" / "data.js").exists()}
            # In its own process, with the code as it now is, whenever this server started.
            # Its own stages' share told (`jobs.PROGRESS` lines) goes to `shared`; its errors kept for the message.
            child = subprocess.Popen([sys.executable, "-m", "volleyball_stats.matches", *target, "--theme", self.theme], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            errors: list[str] = []
            reader = threading.Thread(target=lambda: errors.extend(child.stderr), daemon=True)
            reader.start()
            for line in child.stdout:
                if line.startswith(jobs.PROGRESS):
                    self.shared(float(line.removeprefix(jobs.PROGRESS).split()[0]))
            code = child.wait()
            reader.join()
            if code:
                raise RuntimeError(("".join(errors).strip().splitlines() or [f"exit {code}"])[-1])
            for m, page in taken.items():
                hosted.record_hosted(m, page)
            self.online.update(hosted.read_hosted(match))
        except Exception as error:  # noqa: BLE001
            # The answers stay applied: only the hosted page is behind.
            self.online.update(at=time.strftime("%H:%M"), day=None, error=str(error) or type(error).__name__)

    def filming(self, kind: str, names: list[str] | None = None, strict: bool = False) -> None:
        """The films of `kind` made (`film.build`), a failure kept for the page; raised too with `strict`."""
        try:
            film.build(self.match, self.video, self.court, self.staged, names, kind, self.shared)
            self.films_error = None
        except Exception as error:  # noqa: BLE001
            # The films made are kept: the next press makes those left.
            self.films_error = str(error) or type(error).__name__
            if strict:
                raise

    def page_mark(self) -> int | None:
        """When the review's page was last written."""
        path = self.site / "data.js"
        return path.stat().st_mtime_ns if path.exists() else None

    def updating(self) -> bool:
        """Whether the app's update runs (learn.update): it may make this match again under the review."""
        return jobs.is_running(self.outputs, app.LEARN)

    def follow(self) -> None:
        """The match made again outside this server (the app's update): read again once that update has ended, the
        answers moved onto its rallies (no undo across it)."""
        if self.page_seen == self.page_mark() or self.progress or self.updating():
            return
        with self.lock:
            self.questions.load()
            self.history.clear()
            self.shown.clear()
            self.shown.update(e["id"] for e in load_log(self.answers))
            self.page_changed()
            self.generation += 1
            self.page_seen = self.page_mark()

    def pages(self, pictures: bool = True) -> list:
        """The steps rebuilding the review's page, its pictures later (`afterwards`) unless `pictures`,
        and the published one with its own choices."""
        match, video, court, theme = self.match, self.video, self.court, self.theme

        def own() -> None:
            web.review_page(match, video, court, theme, pictures, self.shared)
            self.page_seen = self.page_mark()
            self.generation += 1
            self.photos_error = None
            if pictures:
                self.stale_photos.unlink(missing_ok=True)
            else:
                self.stale_photos.touch()
            self.shown.clear()
            self.shown.update(e["id"] for e in load_log(self.answers))
            self.page_changed()

        steps = [("review", own)]
        if (match / "page.json").exists():
            steps.append(("page", lambda: web.publish(match, video, court, theme, {}, share=self.shared)))
        return steps

    def club_changed(self) -> None:
        """The pages rebuilt with the club as it now is, before the page reloads."""
        with self.lock:
            self.acting = None
            self.run_steps(self.pages())

    def afterwards(self) -> None:
        """What an apply leaves for later, one run at a time, once more when asked during one: the
        players' pictures, kept on the page if no build came since, then the numbers they read."""
        while True:
            self.later.wait()
            self.after_apply.set()
            self.later.clear()
            try:
                built = self.generation
                if self.stale_photos.exists():
                    try:
                        people = web.refresh_photos(self.match, self.video, self.site)
                    except Exception as error:
                        self.photos_error = str(error) or type(error).__name__
                        raise
                    with self.lock:
                        if built == self.generation:
                            web.patch_people(self.site, people)
                            self.page_seen = self.page_mark()
                            self.stale_photos.unlink(missing_ok=True)
                            self.page_changed()
                self.questions.read_pictures(self.picture)
            except Exception:
                traceback.print_exc()
            finally:
                self.after_apply.clear()

    def run_steps(self, steps: list) -> None:
        try:
            self.at_start.update(data=self.review_data(), action=self.acting)
        except Exception:  # noqa: BLE001
            # A page opened during the run then waits for it.
            traceback.print_exc()
            self.at_start.update(data=None, action=None)
        progress = self.progress
        # The weights of the share stay as the run started: the durations it records go to the next one.
        progress.update(steps=[name for name, _ in steps], started=time.time(), weights=dict(self.took))
        self.failure.clear()
        try:
            for k, (name, work) in enumerate(steps):
                progress.update(done=k, since=time.time(), stage=None, own=None, passed=0.0)
                try:
                    work()
                except Exception as error:
                    self.failure.update(step=name, error=repr(error))
                    raise
                self.staged(None)
                self.took[name] = time.time() - progress["since"]
                files.write_text(self.match / TIMINGS, json.dumps(self.took, indent=1) + "\n")
        finally:
            progress.clear()
            self.at_start.update(data=None, action=None)

    def taken(self, answered: bool = True) -> bool:
        """`lock` taken once free; False instead while a run holds it (`progress`), for a request not to wait on it
        until the run ends; with `answered` only if the run's start data (`at_start`) can answer it instead."""
        while not self.lock.acquire(timeout=0.2):
            if self.progress and (not answered or self.at_start["data"] is not None):
                return False
        return True

    @contextmanager
    def free(self):
        """`lock` held, or Busy while a run holds it."""
        if not self.taken(answered=False):
            raise Busy
        try:
            yield
        finally:
            self.lock.release()

    def review_task(self) -> dict | None:
        """The review's run for the app's tasks: where it stands, else how the last one failed."""
        now = dict(self.progress)
        if now:
            return {"running": True, **eta(now, self.took, time.time())}
        return {"running": False, "failed": self.failure["step"], "error": self.failure["error"]} if self.failure else None

    def staged(self, name: str | None) -> None:
        """The running step's stage `name` starts (None: the step ends): the last one's time is kept, its weight counted
        as done."""
        progress = self.progress
        now, step = time.time(), progress["steps"][progress["done"]]
        if progress.get("stage"):
            key = f"{step}:{progress['stage']}"
            self.took[key] = now - progress["stage_since"]
            progress["passed"] = progress.get("passed", 0.0) + progress["weights"].get(key, 0.0)
        progress.update(stage=name, stage_since=now, own=None)

    def shared(self, share: float) -> None:
        """The running step, or its stage, counted that share of its work (0-1)."""
        if self.progress:
            self.progress["own"] = min(1.0, max(0.0, share))

    def warm(self) -> None:
        """Cuts the review's pictures ahead of the user, READERS at a time."""
        found, _ = self.questions.build(set())
        urls = re.findall(r"crop\?f=(\d+)&b=([\d,-]+)", json.dumps([found, self.questions.players([], self.team_names())]))
        with ThreadPoolExecutor(READERS) as pool:
            list(pool.map(lambda u: self.picture(int(u[0]), tuple(int(v) for v in u[1].split(","))), dict.fromkeys(urls)))
        self.later.set()

    def team_names(self) -> list[str | None]:
        teams = web.read_teams(self.match)
        return [t["name"] for t in teams["teams"]] if teams else [None, None]

    def card_photos(self) -> dict:
        """Each player's card picture first, then the other best moments for one, as picked by
        web.photos; whether the cards' pictures are out of date (an apply came since), why the new
        ones failed."""
        offered = self.match / web.PHOTO_CANDIDATES
        photos = {
            who: [{**m, "crop": f"crop?f={m['frame']}&b={','.join(map(str, m['box']))}"} for m in found]
            for who, found in (files.read_json(offered, {})).items()
        }
        return {"photos": photos, "photosPending": self.stale_photos.exists() and not self.photos_error, "photosError": self.photos_error}

    def reports_came(self, found: dict[str, int]) -> None:
        """New reports fetched by the timer (`feedback.watch`): this match's in its questions (after an apply running),
        for the page to show once it reloads."""
        if self.match.name in found:
            with self.lock:
                self.questions.load()

    def review_data(self) -> dict:
        """What review.js gives the page."""
        match, questions = self.match, self.questions
        log = load_log(self.answers)
        found, _ = questions.build({entry["id"] for entry in log})
        follow_teams(self.roster, match.parent)
        known, teams = load_roster(self.roster), self.team_names()
        players = questions.players(known, teams)
        # The roster's players of each team, for typing names: all of them for an unnamed team.
        names = [[{"name": p["name"], "jersey": p.get("jersey")} for p in known if not team or not p.get("team") or p["team"] == team] for team in teams]
        # Each marked piece, with the player it was said to be, numbered as now; not those now there.
        odd, done = {}, settled(log, self.where)
        for entry in log:
            for o, t in zip(entry.get("odd", []), entry.get("to") or [None] * len(entry.get("odd", []))):
                if piece_key(o) in done:
                    continue
                who = t if t == "not_player" else t and identity.lookup(questions.table, t["track"], t["frame"])
                odd[piece_key(o)] = who if isinstance(who, str) or who is None else f"{who[0]}:{who[1]}"
        conflicts = questions.conflicts(log, identity.read_names(match))
        publish = match / matches.PUBLISH
        return {
            "width": self.width,
            "height": self.height,
            "matchEnd": given_end(match),
            "sets": given_sets(match),
            "answered": len(log),
            **self.waiting(log),
            "comments": commented(read_comments(match), questions.page, log),
            "picks": sorted(film.read_picks(match)),
            "timeouts": timeouts.shown(match, questions.fps),
            "questions": found,
            "players": players,
            "roster": names,
            "odd": odd,
            "conflicts": conflicts,
            **self.card_photos(),
            "hosted": {**self.online, "chosen": "video" in json.loads(publish.read_text())} if publish.exists() else None,
            "updating": self.updating(),
            "fetched": self.fetched or None,
            "backup": self.backup_state(),
            "filmsError": self.films_error,
        }

    # The requests: `get` and `post` answer those of the match, the Handler the others.

    def get(self, path: str, query: str) -> Reply:
        route = self.gets.get(path)
        if route:
            return route(parse_qs(query))
        parts = Path(unquote(path).lstrip("/")).parts
        file = self.site.joinpath(*parts)
        if ".." in parts or not file.is_file():
            return NOT_FOUND
        # A static file, by byte ranges for the video to seek.
        return Reply(file, "")

    def get_data(self, q: dict) -> Reply:
        self.follow()
        if self.taken():
            try:
                # The page shows this match's new reports.
                feedback.seen(self.outputs, self.match.name)
                data = self.review_data()
            finally:
                self.lock.release()
        else:
            # A run goes: the page as it started, which follows the run (`running`, the request that started
            # it) and reloads once it ends.
            data = {**self.at_start["data"], "running": self.at_start["action"] or "apply"}
        return Reply(f"window.REVIEW = {json.dumps(data, separators=(',', ':'))};\n".encode(), "text/javascript")

    def get_photos(self, q: dict) -> Reply:
        if not self.taken():
            # The new pictures come after the run: the page asks again.
            pending = {k: self.at_start["data"][k] for k in ("photos", "photosError")}
            return reply({**pending, "photosPending": True, "people": {}})
        try:
            people = {k: p.get("photo") for k, p in ((page_data(self.site) or {}).get("people") or {}).items()}
            body = {**self.card_photos(), "people": people}
        finally:
            self.lock.release()
        return reply(body)

    def get_progress(self, q: dict) -> Reply:
        now = dict(self.progress)
        return reply(eta(now, self.took, time.time()) if now else {})

    def get_more(self, q: dict) -> Reply:
        team, number = int(q["team"][0]), int(q["identity"][0])
        questions = self.questions
        with self.free():
            log = load_log(self.answers)
            questions.avoid = {questions.segment_of(o) for entry in log for o in entry.get("odd", [])}
            seen = {questions.segment_of(r) for entry in log if entry.get("choice") == "more" for r in entry["pieces"]}
            found = questions.more(team, number, seen)
        return reply(found)

    def get_crop(self, q: dict) -> Reply:
        body = self.picture(int(q["f"][0]), tuple(int(v) for v in q["b"][0].split(",")))
        return Reply(body, "image/jpeg") if body else Reply(b"", "text/plain", 404)

    def feedback(self, raw: bytes) -> Reply:
        """A report of what is wrong in a moment, from the review's copy of the match page: kept as the hosting's nginx keeps
        the viewers' (volleyball_stats.feedback reads both)."""
        with self.reports_lock, open(self.match / FEEDBACK, "a") as f:
            f.write(json.dumps({"received": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "report": raw.decode()}, ensure_ascii=False) + "\n")
        return Reply(b"", "text/plain", 204)

    def post(self, path: str, body: dict) -> Reply:
        route = self.posts.get(path)
        if route:
            return route(body)
        # The app's update makes this match again: nothing changes under it, and what it made is read first.
        if self.updating():
            return reply({"error": "updating"}, 409)
        self.follow()
        questions = self.questions
        with self.free():
            self.acting = path.strip("/")
            log = load_log(self.answers)
            questions.avoid = {questions.segment_of(o) for entry in log for o in entry.get("odd", [])}
            edit = Edit(path, log, list(log))
            change = self.edits.get(path)
            return (change and change(edit, body)) or self.commit(path, body, edit)

    def post_failure(self, body: dict) -> Reply:
        self.failure.clear()
        return reply({})

    def post_backup(self, body: dict) -> Reply:
        if not self.can_back_up:
            return reply({"error": "no server"}, 400)
        self.back_up()
        return reply(self.backup_state())

    def post_auto_backup(self, body: dict) -> Reply:
        if not self.can_back_up or not isinstance(body.get("on"), bool):
            return reply({"error": "no server"}, 400)
        sync.set_auto(self.outputs, body["on"])
        self.wake.set()
        return reply(self.backup_state())

    def post_sync_take(self, body: dict) -> Reply:
        """The server's copy kept, this machine's set aside."""
        if self.progress:
            return reply({"error": "busy"}, 409)
        with self.free(), self.backup_lock:
            try:
                sync.take(self.match)
            except (LookupError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                return failed(error, 502)
        # Everything read from the match's files again.
        command = [sys.executable, "-m", "volleyball_stats.review_server", *[a for a in sys.argv[1:] if a != "--no-browser"], "--no-browser"]
        return reply({}, then=lambda: switch(command, self.lock))

    def post_sync_keep(self, body: dict) -> Reply:
        """This machine's copy kept, the server's set aside there."""
        if self.progress:
            return reply({"error": "busy"}, 409)
        with self.free(), self.backup_lock:
            try:
                sync.keep(self.match)
            except (LookupError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                return failed(error, 502)
        self.elsewhere.clear()
        self.backed.update(at=time.strftime("%H:%M"), error=None)
        return reply({})

    def post_photo(self, e: Edit, body: dict) -> Reply:
        team, number, frame = int(body["team"]), int(body["identity"]), int(body["frame"])
        set_photo(self.match, self.questions.table, team, number, frame, body["box"])
        # Only that picture cut, the page patched; the pages built again only for a moment never scored.
        person = web.swap_photo(self.match, self.video, self.site, team, number, frame, body["box"], self.questions.track_at)
        if person is None:
            self.run_steps(self.pages())
        else:
            self.page_seen = self.page_mark()
            self.page_changed()
        return reply({**self.waiting(e.log), "person": person})

    def post_look(self, e: Edit, body: dict) -> Reply:
        set_look(self.match, self.questions.table, int(body["team"]), int(body["identity"]), str(body["field"]), str(body["value"]))
        self.page_seen = self.page_mark()
        self.page_changed()
        return reply(self.waiting(e.log))

    def post_end(self, e: Edit, body: dict) -> Reply:
        match, questions = self.match, self.questions
        set_end(match, body.get("time"))
        end = match_end(match)
        if end is not None:
            e.log, moved_names = reanchor(e.log, identity.read_names(match), questions.past_end(round(end * questions.fps)), questions.segment_of)
            write_names(match, moved_names)
            save(self.answers, e.log)
        for change in self.history:
            change["names"] = None
        return reply(self.waiting(e.log))

    def post_team(self, e: Edit, body: dict) -> Reply:
        match = self.match
        set_team(match, int(body["team"]), body.get("name"), body.get("colour"))
        # Its name follows its teams, the folders and the video with it: the server restarts on them.
        new = rename.target_name(match)
        if new and new != match.name and not self.progress and not (match.parent / new).exists():
            # In its own process, with the code as it now is, whenever this server started.
            run = subprocess.run([sys.executable, "-m", "volleyball_stats.rename", str(match), new, "--from-review"], capture_output=True, text=True)
            if run.returncode:
                raise ValueError(run.stderr.strip())
            return reply({"renamed": new}, then=lambda: switch(reopening(new, match.parent, self.theme, self.port, self.roster), threading.Lock()))
        self.run_steps(self.pages(pictures=False))
        self.later.set()
        return reply(self.waiting(e.log))

    def post_name(self, e: Edit, body: dict) -> Reply:
        match, questions = self.match, self.questions
        # One name, or a team's proposed ones at once (`names`).
        for given in body.get("names") or [body]:
            jersey, team, number = given.get("jersey"), int(given["team"]), int(given["identity"])
            # A name removed, or a proposal cleared (`refused`): that player is not in the match.
            removed = (identity.named(questions.table, identity.read_names(match)).get((team, number)) or {}).get("name") or given.get("refused")
            set_name(match, questions, team, number, given.get("name"), None if jersey in (None, "") else int(jersey))
            name_absent(match, questions.table, team, given.get("name"), removed)
        # Undo leaves the names as typed since.
        for change in self.history:
            change["names"] = None
        # A player of the other team: the card goes there, undone like an answer.
        if body.get("moved"):
            entry = questions.to_other_team(int(body["team"]), int(body["identity"]))
            self.history.append({"log": e.before, "names": None, "applied": False})
            del self.history[:-UNDOS]
            e.log = [*(x for x in e.log if x["id"] != entry["id"]), entry]
            save(self.answers, e.log)
        return reply(self.waiting(e.log))

    def post_comment(self, e: Edit, body: dict) -> Reply:
        comments = commented(read_comments(self.match), self.questions.page, e.log)
        key, text = int(body["rally"]), str(body["text"]).strip()
        if text:
            comments[key] = text
        else:
            comments.pop(key, None)
        write_comments(self.match, comments)
        return reply({})

    def post_pick(self, e: Edit, body: dict) -> Reply:
        picks, frame = film.read_picks(self.match), int(body["frame"])
        film.write_picks(self.match, picks | {frame} if body["picked"] else picks - {frame})
        return reply({})

    def post_timeout(self, e: Edit, body: dict) -> Reply:
        # The page shows them: an apply takes them in.
        return reply({"timeouts": timeouts.answer(self.match, self.questions.fps, body), **self.waiting(e.log)})

    def post_answer(self, e: Edit, body: dict) -> Reply | None:
        match, questions, log = self.match, self.questions, e.log
        _, refs = questions.build({entry["id"] for entry in log})
        # Corrections saved from the match tab, about no question.
        edit = str(body["id"]).startswith("edit:")
        if body["id"] not in refs and not edit:
            return reply({"error": "unknown question"}, 400)
        choice = "report" if edit else str(body["choice"])
        said = choice.split(":") if choice.startswith("player:") else None
        player = said and questions.ref(int(said[1]), int(said[2]))
        if edit or "report" in refs[body["id"]]:
            given = identity.named(questions.table, identity.read_names(match))
            # An edit sent without corrections only checks or unchecks rallies: the corrections stay.
            sent = choice == "report" and "changes" in body
            changes = body.get("changes") or {}
            teams, windows, keys = questions.page_index()
            fixes = report_answer(changes, teams, windows, given, round(web.LEAD_S * questions.fps), keys) if sent else {}
            if sent:
                log[:] = superseded(log, self.shown)
            ok = [int(k) for k in body.get("checked") or []] if edit else []
            off = [int(k) for k in body.get("unchecked") or []] if edit else []
            asked = {entry["id"] for entry in log}
            # Before the answer: an undo after a restart takes that one away.
            log += pinned(questions.page, ok) + locked(questions.page, ok, given) + unlocked(off)
            wrong = choice == "wrong" and not edit and refs[body["id"]]["report"].get("record")
            log.append({"id": body["id"], "choice": choice, **fixes, **({"changes": changes} if sent else {}), **({"checked": ok} if ok else {}), **({"unchecked": off} if off else {}), **({"wrong": [wrong]} if wrong else {}), "applied": False})
            # The reports on a rally checked are handled with it.
            log += [{"id": qid, "choice": "checked", "applied": False} for qid, ref in refs.items() if "report" in ref and ref["report"]["start"] in ok and qid not in asked]
        elif "rally" in refs[body["id"]]:
            log.append({"id": body["id"], "choice": choice, **rally_answer(refs[body["id"]]["rally"], choice), "applied": False})
        elif "receiver" in refs[body["id"]]:
            given = identity.named(questions.table, identity.read_names(match))
            log.append({"id": body["id"], "choice": choice, **receiver_answer(refs[body["id"]]["receiver"], choice, given, refs[body["id"]].get("start")), "applied": False})
        elif "touch" in refs[body["id"]]:
            given = identity.named(questions.table, identity.read_names(match))
            log.append({"id": body["id"], "choice": choice, **touch_answer(refs[body["id"]]["touch"], choice, given), "applied": False})
        else:
            cut = None
            if choice == "cut":
                c = next(c for c in questions.candidates["segments"] if f"piece:{c['track']}:{c['start_frame']}" == body["id"])
                cut = questions.cut(c["track"], c["start_frame"], c["end_frame"], float(body["at"]))
                if cut is None:
                    return reply({"error": "cut at the edge of the piece"}, 400)
            entry = {"id": body["id"], "choice": choice, **constraints(choice, refs[body["id"]], player, cut), "applied": False}
            # Said to be a player when earlier answers say another: the user settles it.
            if player or choice.isdigit():
                names = identity.read_names(match)
                freed, earlier = piece_conflict(log, entry, refs[body["id"]]["piece"], names, questions.segment_of)
                if earlier and not body.get("replace") and not body.get("force"):
                    return reply({"conflict": earlier}, 409)
                if earlier and body.get("replace"):
                    log = freed
            log.append(entry)
        e.log = log
        return None

    def post_odd(self, e: Edit, body: dict) -> None:
        questions = self.questions
        refs = [[{"track": int(r["track"]), "frame": int(r["frame"])} for r in body[k]] for k in ("odd", "rest")]
        to = [t if t == "not_player" else t and questions.ref(int(t["team"]), int(t["identity"])) for t in body.get("to") or [None] * len(refs[0])]
        # Pictures left unmarked that an earlier mark moved here stay marked as moved.
        e.log = mark_odd(e.log, *refs, to, frozenset(settled(e.log, self.where) & {piece_key(r) for r in refs[1]}))
        marking = e.log[-1]["id"] if refs[0] else None
        # The player's pins on the pictures marked move to their first picture left; then
        # the earlier answers giving them those pieces let go: the latest judgment wins.
        if refs[0] and refs[1]:
            moved = {questions.segment_of(o): refs[1][0] for o in refs[0]}
            e.names_before = identity.read_names(self.match)
            e.log, e.renamed = reanchor(e.log, e.names_before, moved, questions.segment_of)
        if marking and body.get("owner"):
            owner = (int(body["owner"]["team"]), int(body["owner"]["identity"]))
            e.log = supersede(e.log, refs[0], marking, lambda r: self.where(r) == owner, questions.segment_of)

    def post_more(self, e: Edit, body: dict) -> None:
        # Pieces looking like a player: those kept are them, the others someone else.
        team, number = int(body["team"]), int(body["identity"])
        yes, no = ([{"track": int(r["track"]), "frame": int(r["frame"])} for r in body[k]] for k in ("yes", "no"))
        pin = self.questions.ref(team, number)
        e.log.append({
            "id": f"more:{team}:{number}:{len(e.log)}", "choice": "more", "pieces": yes + no,
            **({"same": [[pin, *yes]]} if yes else {}), **({"different": [[r, pin] for r in no]} if no else {}), "applied": False,
        })

    def post_repin(self, e: Edit, body: dict) -> None:
        # A question answer said again: its piece is `who`'s, pinned where they are.
        questions = self.questions
        track, start = (int(v) for v in str(body["id"]).split(":")[1:3])
        own = questions.segment_of({"track": track, "frame": start})
        team, number = (int(v) for v in str(body["who"]).split(":"))
        pin = questions.ref(team, number)
        e.log = [
            {**x, "same": [[r if questions.segment_of(r) == own else pin for r in g] for g in x.get("same", [])], "applied": False} if x["id"] == body["id"] else x
            for x in e.log
        ]

    def post_forget(self, e: Edit, body: dict) -> None:
        e.log = [x for x in e.log if x["id"] != body["id"]]

    def post_separate(self, e: Edit, body: dict) -> None:
        e.log = self.questions.separated(e.log, identity.read_names(self.match), body["team"], body["identity"])

    def post_cut(self, e: Edit, body: dict) -> Reply | None:
        # A piece answer in a conflict, cut where the person changes, in place of the answer.
        questions = self.questions
        track, start = (int(v) for v in str(body["id"]).split(":")[1:3])
        _, a, b = questions.segment_of({"track": track, "frame": start})
        cut = questions.cut(track, a, b, float(body["at"]))
        if cut is None:
            return reply({"error": "cut at the edge of the piece"}, 400)
        e.log = [x for x in e.log if x["id"] != body["id"]]
        e.log.append({"id": f"cut:{track}:{cut[0]['frame']}", "choice": "cut", **constraints("cut", {"choices": []}, cut=cut), "applied": False})
        return None

    def post_reports(self, e: Edit, body: dict) -> Reply | None:
        if not (self.match / matches.PUBLISH).exists():
            return None

        def fetched() -> None:
            try:
                # Every hosting's: the others' new ones wait for their match.
                got = feedback.fetch_all(self.outputs)
                self.fetched.update(at=time.strftime("%H:%M"), count=got.get(self.match.name, 0), error=None)
            except Exception as error:  # noqa: BLE001
                self.fetched.update(at=time.strftime("%H:%M"), count=0, error=str(error) or type(error).__name__)

        self.run_steps([("reports", fetched), ("questions", self.questions.load)])
        return self.answered(e.log, fetched=self.fetched)

    def post_host(self, e: Edit, body: dict) -> Reply | None:
        match, video = self.match, self.video
        if not (match / matches.PUBLISH).exists():
            return None
        config = json.loads((match / matches.PUBLISH).read_text())
        if "video" not in config:
            if body.get("video") and not matches.password(self.outputs):
                # The first match online with its video: the password chosen with it.
                matches.set_password(self.outputs, body.get("password"))
            config = matches.choose(match, bool(body["video"]))
        # Hours of encoding only for a match that goes online with its video; copies cut by a former zoom
        # only when the owner says so (`remake`).
        remake = bool(body.get("remake"))
        needed = config["video"] and (matches.copies_missing(config) or (remake and matches.copies_stale(match, config)))
        copies = [("copies", lambda: matches.add_copies(match, video, self.shared, remake))] if needed else []
        # A first upload with the video takes the players' films and the highlights, those not made yet.
        stale = film.status(match) if matches.first_with_video(match, config) else {}
        films = [(step, lambda kind=kind: self.filming(kind, strict=True)) for step, kind in (("films", "players"), ("highlights", "highlights")) if stale.get(kind, {}).get("stale")]
        self.run_steps([*copies, *films, *(self.pages() if films else []), ("hosting", self.hosting)])
        return self.answered(e.log)

    def post_host_all(self, e: Edit, body: dict) -> Reply | None:
        if not (self.match / matches.PUBLISH).exists():
            return None
        # As each match's own upload: the video copies missing or at a former height made first.
        copies = [("copies", lambda m=m, v=v: matches.add_copies(m, v, self.shared)) for m, v, _, c in matches.online(self.match.parent) if c["video"] and v.exists() and matches.copies_missing(c)]
        self.run_steps([*copies, ("hostingAll", lambda: self.hosting(every=True))])
        return self.answered(e.log)

    def post_films(self, e: Edit, body: dict) -> Reply:
        # The page then shows them, the hosted one on its next upload; "/film" makes the player `name`'s alone.
        path = e.path
        names = [str(body["name"])] if path == "/film" else None
        step, kind = ("highlights", "highlights") if path == "/highlights" else (path[1:], "players")
        self.run_steps([(step, lambda: self.filming(kind, names)), *self.pages()])
        return self.answered(e.log)

    def post_sets(self, e: Edit, body: dict) -> Reply:
        from volleyball_stats import learn

        match = self.match
        set_start(match, self.questions.fps, body.get("add"), body.get("remove"))
        # The pipeline again, its identities with every answer: an apply too. Undo
        # stops here: the answers moved onto the new rallies.
        own, *published = self.pages()
        self.run_steps([("pipeline", lambda: learn.rerun(match, self.video, self.court, self.staged)), own, ("questions", self.questions.load), *published])
        self.history.clear()
        log = load_log(self.answers)
        for entry in log:
            entry["applied"] = True
        save(self.answers, log)
        files.write_text(self.computed, json.dumps(state(match, log)))
        return self.answered(log, rebuilt=True)

    def post_undo(self, e: Edit, body: dict) -> None:
        if self.history or e.log:
            e.log, e.renamed, e.undone, e.undo_applied = undo(e.log, self.history)

    def commit(self, path: str, body: dict, e: Edit) -> Reply:
        """The answers' log `e` saved, the change kept for undo; with "/apply" (or an undo past one) applied: the identities
        computed again, the pages rebuilt."""
        match, questions = self.match, self.questions
        # An answer joining two players of different names waits for the user's go.
        if path in ("/answer", "/odd", "/more", "/repin") and not body.get("force"):
            names = identity.read_names(match)
            new = name_merges(e.log, e.renamed or names, questions.segment_of) - name_merges(e.before, names, questions.segment_of)
            if new:
                return reply({"merges": sorted(sorted(m) for m in new)}, 409)
        if path in CHANGES and (e.log != e.before or e.renamed is not None):
            self.history.append({"log": e.before, "names": e.names_before if e.renamed is not None else None, "applied": False})
            del self.history[:-UNDOS]
        if e.renamed is not None:
            write_names(match, e.renamed)
        save(self.answers, e.log)
        # A change not applied yet is only in the log; undoing one an apply followed (`undo`)
        # recomputes, as applying does.
        rebuilt = path == "/apply" or e.undo_applied
        if rebuilt:
            # The review's own page first: the questions ask what it leaves unidentified.
            own, *published = self.pages(pictures=False)
            steps = [("players", lambda: identity.rerun(match, self.video, self.squad, self.shared)), own, ("questions", questions.load)]
            if path == "/apply":
                steps.append(("roster", lambda: remember(self.roster, match.name, identity.named(questions.table, identity.read_names(match)), questions.vectors, self.team_names())))
            self.run_steps(steps + published)
            # Counted in the app's log: how many applies a match's naming takes.
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {path.strip('/')}: {sum(not x.get('applied', True) for x in e.log)} answers", flush=True)
            self.later.set()
            for entry in e.log:
                entry["applied"] = True
            for change in self.history:
                change["applied"] = True
            save(self.answers, e.log)
            files.write_text(self.computed, json.dumps(state(match, e.log)))
        return self.answered(e.log, rebuilt, e.undone)


class Server(ThreadingHTTPServer):
    """The review's server: the list of the matches of `out`, and `review`'s match when one is open. Quiet when a page goes
    before its answer (a reload, a closed tab)."""

    def __init__(self, out: Path, theme: str, port: int, roster: Path, review: Review | None = None) -> None:
        self.out, self.theme, self.port, self.roster, self.review = out, theme, port, roster, review
        # On the local network too when the app says so (`network`): the process starts again to change it.
        self.lan = network.shared(app.OUTPUTS)
        # A restart waits for no answer being saved.
        self.lock = review.lock if review else None
        super().__init__((network.bind(app.OUTPUTS), port), Handler)
        # The one given, or the one found for port 0.
        self.port = self.server_address[1]

    def handle_error(self, request, client_address) -> None:
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    """The review's requests: the list's and the app's, the match's to its `Review`."""

    server: Server

    def log_message(self, *_) -> None:
        pass

    def do_GET(self) -> None:
        self.answer(self.get)

    def do_POST(self) -> None:
        self.answer(self.post)

    def answer(self, handle: Callable[[], Reply]) -> None:
        """`handle`'s response, then what it leaves to do; 400 for a request it cannot read (a field missing or of the wrong type)."""
        try:
            found = handle()
        except Busy:
            found = reply({"error": "busy"}, 503)
        except (LookupError, TypeError, ValueError, AttributeError, StopIteration) as error:
            traceback.print_exc()
            found = reply({"error": repr(error)}, 400)
        self.send(found)
        if found.then:
            found.then()

    def send(self, found: Reply) -> None:
        if found.location:
            self.send_response(found.status)
            self.send_header("Location", found.location)
            self.end_headers()
            return
        # A file: by byte ranges, for a video to seek (a card's video for the import's player, the review's).
        if isinstance(found.body, Path):
            return send_file(self, found.body, found.kind or None)
        self.send_response(found.status)
        self.send_header("Content-Type", found.kind)
        self.send_header("Content-Length", str(len(found.body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(found.body)

    def ours(self) -> bool:
        """Whether a request comes from the review itself: binding 127.0.0.1 keeps other machines
        out unless the app opens it to the local network (`network`), not another site open in the same
        browser (its requests name another Origin or a cross-site Sec-Fetch-Site) nor one rebinding its
        domain to this machine (another Host)."""
        return same_site(self.headers, self.server.port, self.server.lan)

    def app_context(self) -> dict:
        review = self.server.review
        return review.app_context() if review else {}

    def get(self) -> Reply:
        s, review = self.server, self.server.review
        if not self.ours():
            return FORBIDDEN
        url = urlparse(self.path)
        if url.path in SPELLINGS:
            return moved(SPELLINGS[url.path] + (f"?{url.query}" if url.query else ""))
        if url.path == "/current":
            return reply({"name": review.match.name if review else None})
        if url.path == "/" or (url.path == "/review" and not review):
            return moved("/matches/")
        found = network_route("GET", url.path, {}, s.port) or app.handle("GET", url.path, url.query, {}, lambda: match_list(s.out), **self.app_context())
        if found:
            return Reply(*found)
        if url.path == "/matches.json":
            return reply(match_list(s.out))
        if url.path.startswith("/matches/"):
            page = list_page(url.path, s.out, s.theme)
            return Reply(*page) if page else NOT_FOUND
        if url.path == "/git":
            return reply(git_check.behind(git_check.ROOT))
        return review.get(url.path, url.query) if review else NOT_FOUND

    def post(self) -> Reply:
        s, review, path = self.server, self.server.review, self.path
        # A JSON body: a page elsewhere can only send a form or plain text without asking.
        known = review or path in ("/open", "/pull") or path.startswith("/app/")
        if not self.ours() or not known or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return FORBIDDEN
        size = int(self.headers.get("Content-Length", 0))
        if not 0 <= size <= (CLUB_BODY if path == "/app/club" else MAX_BODY):
            return reply({"error": "body too large"}, 413)
        raw = self.rfile.read(size)
        if review and path == "/feedback":
            return review.feedback(raw)
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return reply({"error": "not json"}, 400)
        if path.startswith("/app/"):
            answer = network_route("POST", path, body, s.port) or app.handle("POST", path, "", body, lambda: match_list(s.out), **self.app_context()) or NOT_FOUND

            def then() -> None:
                network_restart(path, body, answer, s.lock)
                if path == "/app/update" and answer[2] == 200:
                    app.restart_after(s.lock)
                if path == "/app/quit" and answer[2] == 200:
                    app.stop_after(s.lock)

            return Reply(*answer[:3], then=then)
        if path == "/pull":
            return pulled(body, s.out)
        if path == "/open":
            return self.open(body)
        return review.post(path, body)

    def open(self, body: dict) -> Reply:
        """The review on the match `name`: this process started again on it (the match open already opens)."""
        s, review = self.server, self.server.review
        try:
            name = body["name"]
            command = reopening(name, s.out, s.theme, s.port, s.roster)
        except (LookupError, TypeError, ValueError):
            return reply({"error": "no such match"}, 400)
        if review and name == review.match.name:
            return reply({})
        # The match open goes on while it runs: only another waits.
        if review and review.progress:
            return reply({"error": "busy"}, 409)
        return reply({}, then=lambda: switch(command, s.lock or threading.Lock()))


def serve(out: Path, theme: str, port: int, browser: bool, roster: Path, review: Review | None = None) -> None:
    """The list of the matches of `out`, and `review`'s match when one is open, until the process stops."""
    # The footage shows real people: this machine only, unless the app opens it to the local network.
    server = Server(out, theme, port, roster, review)
    if review:
        review.start()
        presence.watch(review.may_stop, review.lock)
    else:
        threading.Thread(target=backing_all, args=(out.parent,), daemon=True).start()
        threading.Thread(target=feedback.watch, args=(out.parent,), daemon=True).start()
        presence.watch(lambda: not any(j["running"] for j in jobs.state(app.OUTPUTS)))
    url = f"http://127.0.0.1:{port}/{'review' if review else 'matches/'}"
    print(f"Review: {url} (Ctrl+C to stop)", flush=True)
    if browser:
        app.open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Review the doubtful player identities on the video, in the browser.")
    parser.add_argument("match", type=Path, nargs="?", help="The match's outputs directory (outputs/matches/VIDEO) or its name, as /current gives it. Default: the list of the matches")
    parser.add_argument("--outputs", type=Path, default=Path("outputs/matches"), help="Where the list of the matches looks")
    parser.add_argument("--video", type=Path, help="Default: the match's source.json")
    parser.add_argument("--court", type=Path, help="Court calibration JSON the match was run with. Default: the match's source.json")
    parser.add_argument("--squad", type=identity.parse_squad, help="Players per team, N or N1,N2")
    parser.add_argument("--theme", default=web.CLUB, help="Club theme of the pages (web.py): the app's by default")
    parser.add_argument("--roster", type=Path, default=ROSTER, help=f"The club's named players across matches (default: {ROSTER})")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the page in the browser")
    parser.add_argument("--with-window", action="store_true", help="Stop once the app's last window closes, no job running (`stats`)")
    args = parser.parse_args()
    applog.start(app.LOG)
    presence.ON = args.with_window
    if args.match is None:
        return serve(args.outputs, args.theme, args.port, not args.no_browser, args.roster)
    if not args.match.exists() and (args.outputs / args.match).is_dir():
        args.match = args.outputs / args.match
    source = args.match / files.SOURCE
    given = files.read_json(source, {})
    video, court = args.video or given.get("video"), args.court or given.get("court")
    if not video or not court:
        parser.error(f"--video and --court: {source} does not say them")
    squad = args.squad or (identity.parse_squad(given["squad"]) if given.get("squad") else None)
    files.write_source(args.match, video, court, squad)
    review = Review(args.match, Path(video), Path(court), squad, args.theme, args.port, args.roster)
    serve(args.match.parent, args.theme, args.port, not args.no_browser, args.roster, review)


if __name__ == "__main__":
    main()
