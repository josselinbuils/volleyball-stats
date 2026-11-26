"""Matches online without a server of one's own: their public pages (no video, no pictures, as the export makes them) on a
free Netlify site of the user's account. The app signs in through OAuth's ticket flow (as Netlify's own CLI: no address to
register, no token to paste), makes the site, and deploys it through Netlify's API, sending only the files it lacks.

Everything sits in outputs/netlify/: the account (ACCOUNT: its token, the site), the site as last deployed (SITE), what each
match's deploy sent (PUBLISHED, PAGES: its page late or up to date, as the server's `hosted.py` says).
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from volleyball_stats import club_settings, files, hosted, jobs, matches, web

API = os.environ.get("VOLLEYBALL_STATS_NETLIFY_API", "https://api.netlify.com/api/v1")
AUTHORIZE = os.environ.get("VOLLEYBALL_STATS_NETLIFY_APP", "https://app.netlify.com") + "/authorize?response_type=ticket&ticket={ticket}"
# The app's OAuth application on Netlify (app.netlify.com/applications), public as the CLI's: no secret in the ticket flow.
# ponytail: empty until the owner registers it; the sign-in is not offered meanwhile.
CLIENT_ID = os.environ.get("VOLLEYBALL_STATS_NETLIFY_CLIENT", "")
FOLDER = "netlify"
ACCOUNT, SITE, PUBLISHED, PAGES = "account.json", "site", "published.json", "pages"
TIMINGS = "netlify_timings.json"
TOOK = {"match": 10.0, "deploy": 20.0}
# The free plan: 300 credits a month, 15 a production deploy (26 Nov 2026), its sites paused once spent. The card warns
# from WARN_FROM deploys in the last DEPLOYS_DAYS.
FREE_DEPLOYS, WARN_FROM, DEPLOYS_DAYS = 20, 15, 30
# Netlify's API: a request answered within 30 s, else `async`; a deploy ready within minutes.
TIMEOUT_S, READY_S, POLL_S, TRIES = 60, 600, 1.0, 3
# A deploy whose files Netlify has compared: `required` names those it lacks.
PREPARED = {"prepared", "uploading", "uploaded", "ready"}
AGENT = "volleyball-stats"


def folder(outputs: Path) -> Path:
    return outputs / FOLDER


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(path, text)


def account(outputs: Path) -> dict:
    return files.read_json(folder(outputs) / ACCOUNT, {})


def request(method: str, path: str, token: str | None = None, body: dict | None = None, data: bytes | None = None, timeout: float = TIMEOUT_S):
    """Netlify's API answer to `method` on `path` (JSON `body`, or raw `data`), None when empty; PermissionError("netlify")
    when the token is refused, RuntimeError with its reason else ("network" when it cannot be reached). Retried TRIES
    times on a timeout, a server's error or the rate limit."""
    headers = {"User-Agent": AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    for attempt in range(TRIES):
        last = attempt == TRIES - 1
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, data=data, method=method, headers=headers), timeout=timeout) as answer:
                text = answer.read()
            return json.loads(text) if text.strip() else None
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise PermissionError("netlify") from error
            if (error.code == 429 or error.code >= 500) and not last:
                reset = error.headers.get("X-RateLimit-Reset")
                time.sleep(min(60.0, max(1.0, float(reset) - time.time())) if error.code == 429 and reset and reset.isdigit() else 2.0**attempt)
                continue
            try:
                said = json.loads(error.read() or b"{}")
            except ValueError:
                said = {}
            raise RuntimeError(f"netlify {error.code}: {said.get('message') or error.reason}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if last:
                raise RuntimeError("network") from error
            time.sleep(2.0**attempt)
    raise AssertionError


def connect(outputs: Path) -> str:
    """A sign-in started: the ticket kept, the page Netlify asks the user's consent on returned. LookupError("netlify")
    while the app has no client id."""
    if not CLIENT_ID:
        raise LookupError("netlify")
    ticket = request("POST", f"/oauth/tickets?client_id={urllib.parse.quote(CLIENT_ID)}")
    write(folder(outputs) / ACCOUNT, json.dumps({"ticket": ticket["id"]}) + "\n")
    return AUTHORIZE.format(ticket=urllib.parse.quote(ticket["id"]))


def check(outputs: Path) -> dict:
    """The account, its waiting sign-in carried on: once the user consented, the token taken and the site made."""
    found = account(outputs)
    if not found.get("ticket") or found.get("token"):
        return found
    try:
        ticket = request("GET", f"/oauth/tickets/{urllib.parse.quote(found['ticket'])}")
    except RuntimeError as error:
        if not str(error).startswith("netlify 404"):
            raise
        # A ticket Netlify no longer knows: the sign-in starts again.
        (folder(outputs) / ACCOUNT).unlink(missing_ok=True)
        return {}
    if not ticket.get("authorized"):
        return found
    token = request("POST", f"/oauth/tickets/{urllib.parse.quote(found['ticket'])}/exchange")["access_token"]
    made = make_site(token, club_name(outputs))
    found = {"token": token, "site": made["id"], "url": (made.get("ssl_url") or made["url"]).rstrip("/") + "/", "name": made["name"]}
    write(folder(outputs) / ACCOUNT, json.dumps(found, indent=1) + "\n")
    return found


def club_name(outputs: Path) -> str | None:
    club = club_settings.read(outputs / "club")
    return club.get("name") if club else None


def site_names(club: str | None) -> list[str]:
    """The site's names to try, its address NAME.netlify.app: the club's, then with a few letters after it (a name taken)."""
    base = (matches.slug(club or "") or "volley")[:40].strip("-") + "-stats"
    return [base, *(f"{base}-{secrets.token_hex(2)}" for _ in range(3))]


def make_site(token: str, club: str | None) -> dict:
    """A new site of the user's account, named after the club when free."""
    for name in site_names(club):
        try:
            return request("POST", "/sites", token, {"name": name})
        except RuntimeError as error:
            # A name taken.
            if not str(error).startswith("netlify 422"):
                raise
    raise RuntimeError("netlify: no free name")


def disconnect(outputs: Path) -> None:
    """The account forgotten here, with what was deployed: a new sign-in makes a new site. The site stays on Netlify."""
    shutil.rmtree(folder(outputs), ignore_errors=True)


def published(outputs: Path) -> dict:
    return files.read_json(folder(outputs) / PUBLISHED, {"matches": {}, "deploys": []})


def recent_deploys(found: dict, now: datetime | None = None) -> int:
    since = (now or datetime.now()) - timedelta(days=DEPLOYS_DAYS)
    return sum(datetime.fromisoformat(at) >= since for at in found.get("deploys", []))


def record_of(found: dict, match: Path) -> tuple[str, dict] | None:
    """The match's last deploy, under its name or one it had (rename.py)."""
    return next(((n, found["matches"][n]) for n in (match.name, *files.aliases(match)) if n in found["matches"]), None)


def page_state(outputs: Path, match: Path, found: dict, url: str | None, code: dict | None) -> dict:
    """Where `match`'s page stands on the site: `new` before its first deploy, else when it went (`at`, `day` when not today),
    `behind` with what changed (`changes`), the site's code late making it late too; its address."""
    site = folder(outputs) / SITE
    record = record_of(found, match)
    if not record:
        return {"new": True, "at": None, "day": None, "behind": False, "changes": None, "url": None}
    name, saved = record
    state = hosted.hosted_state(saved, hosted.page_stamp(match), date.today())
    sent = folder(outputs) / PAGES / f"{name}.json"
    state["changes"] = hosted.page_changes(json.loads(sent.read_text(encoding="utf-8")), hosted.page_content(match)) if state["behind"] and sent.exists() else None
    # Its stamp changed, not what the page shows (`hosted.read_hosted`).
    if state["changes"] == []:
        state["behind"], state["changes"] = False, None
    if code and code["behind"]:
        state["behind"] = True
        state["changes"] = [*(state["changes"] or []), {**code["change"], "part": "siteCode"}]
    page = matches.hosted_folder(match, site)
    return {**{k: state[k] for k in ("at", "day", "behind", "changes")}, "new": False, "url": f"{url}{page.name}/" if url and page else None}


def ready(outputs: Path) -> list[tuple[Path, Path, Path, dict]]:
    """The matches that can go online (their pipeline ended, their files there, a real match), with their video, court and
    the list's item (`review_server.match_list`)."""
    from volleyball_stats import review_server

    found = []
    for m in review_server.match_list(outputs / "matches"):
        match = outputs / "matches" / m["path"]
        given = json.loads((match / files.SOURCE).read_text(encoding="utf-8"))
        if m["ready"] and not m.get("missing") and matches.imported(match, Path(given["video"])):
            found.append((match, Path(given["video"]), Path(given["court"]), m))
    return found


def state(outputs: Path) -> dict:
    """The Site tab's Netlify card: whether the sign-in is offered, waiting, done (the site's address), the matches and where
    each stands, how many deploys the last DEPLOYS_DAYS made."""
    found = check(outputs)
    if not found.get("token"):
        return {"available": bool(CLIENT_ID), "connecting": bool(found.get("ticket")), "url": None, "matches": [], "deploys": 0, "free": FREE_DEPLOYS, "warn": WARN_FROM}
    done = published(outputs)
    site = folder(outputs) / SITE
    code = hosted.site_code(site) if done["matches"] else None
    listed = []
    for match, _, _, m in ready(outputs):
        teams = m.get("teams")
        listed.append(
            {
                "name": match.name,
                "date": m.get("date"),
                "title": m.get("title"),
                "teams": [t.get("name") for t in teams] if teams else None,
                **page_state(outputs, match, done, found["url"], code),
            }
        )
    listed.sort(key=lambda m: (m["date"] or "", m["name"]), reverse=True)
    return {"available": True, "connecting": False, "url": found["url"], "matches": listed, "deploys": recent_deploys(done), "free": FREE_DEPLOYS, "warn": WARN_FROM}


def qr(text: str) -> bytes:
    """`text` as a QR code's PNG, its modules 8 px with the quiet zone around."""
    import cv2
    import numpy as np

    code = cv2.QRCodeEncoder.create().encode(text)
    code = np.pad(code, 4, constant_values=255) if code.min() == 0 else code
    return cv2.imencode(".png", cv2.resize(code, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST))[1].tobytes()


def manifest(site: Path) -> dict[str, Path]:
    """The site's files by their path online: not the gzip copies (`matches.compress`, for nginx), Netlify compresses itself."""
    return {"/" + p.relative_to(site).as_posix(): p for p in sorted(site.rglob("*")) if p.is_file() and p.suffix != ".gz"}


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def wait(token: str, deploy: str, states: set[str], timeout: float = READY_S) -> dict:
    """The deploy once in one of `states`; RuntimeError when it failed or took too long."""
    until = time.monotonic() + timeout
    while True:
        found = request("GET", f"/deploys/{deploy}", token)
        if found["state"] in states:
            return found
        if found["state"] == "error":
            raise RuntimeError(f"netlify: {found.get('error_message') or 'deploy failed'}")
        if time.monotonic() > until:
            raise RuntimeError(f"netlify: deploy still {found['state']}")
        time.sleep(POLL_S)


def deploy(token: str, site_id: str, site: Path, share: jobs.Share = jobs.quiet) -> dict:
    """`site` deployed as the whole site: every file named by its SHA1, those Netlify lacks sent (their bytes counted by
    `share`), then live once ready."""
    paths = manifest(site)
    digests = {path: sha1(file) for path, file in paths.items()}
    made = request("POST", f"/sites/{site_id}/deploys", token, {"files": digests, "async": True})
    if made.get("state") not in PREPARED:
        made = wait(token, made["id"], PREPARED)
    required = set(made.get("required") or [])
    # One file per content: Netlify asks each once.
    sending = {digest: path for path, digest in sorted(digests.items(), reverse=True) if digest in required}
    total = sum(paths[p].stat().st_size for p in sending.values()) or 1
    done = 0
    for path in sorted(sending.values()):
        body = paths[path].read_bytes()
        request("PUT", f"/deploys/{made['id']}/files{urllib.parse.quote(path)}", token, data=body, timeout=300)
        done += len(body)
        share(done / total)
    share(1.0)
    return wait(token, made["id"], {"ready"})


def build(outputs: Path, chosen: list[tuple[Path, Path, Path]], theme: str, url: str, told: jobs.Stages) -> list[str]:
    """The public pages of `chosen` (match, video, court) built again in the site, every other page given the code as built
    (the site runs one), then the list and the link previews at `url`; the files the code's retirement removed."""
    site = folder(outputs) / SITE
    site.mkdir(parents=True, exist_ok=True)
    done = set()
    for match, video, court in chosen:
        told.start(f"match:{match.name}")
        if not video.exists():
            raise RuntimeError(f"{match.name}: video not found: {video}")
        page = matches.hosted_folder(match, site) or site / match.name
        matches.ensure_review_page(match, video, court, theme)
        matches.make_voice(match)
        given = files.read_json(match / matches.PUBLISH, {})
        # No video, no pictures: a host without a password (CLAUDE.md).
        web.publish(match, video, court, theme, {"footage": "none", "club": given.get("club") or matches.club_team(match, theme), "pictures": False}, page, told.share_of_stage)
        shutil.rmtree(page / "video", ignore_errors=True)
        done.add(page)
    for data in site.glob("*/data.js"):
        if data.parent not in done and matches.page_format(data.parent) == web.FORMAT:
            web.renew_code(data.parent)
    retired: list[str] = []
    matches.build(site, theme, url, retired)
    matches.write_code(site)
    outside = matches.unguarded_videos(site) or sorted(site.rglob("*.mp4"))
    if outside:
        raise RuntimeError(f"videos in the site: {', '.join(p.name for p in outside)}: not deployed")
    return retired


def publish(outputs: Path, names: list[str], theme: str = matches.CLUB) -> None:
    """The matches `names` built again and the site deployed once, each match's deploy recorded (a change made while it ran
    left late); its stages told as it goes."""
    found = account(outputs)
    if not found.get("token"):
        raise LookupError("netlify")
    by_name = {m.name: (m, v, c) for m, v, c, _ in ready(outputs)}
    if not names or any(n not in by_name for n in names):
        raise LookupError(names)
    chosen = [by_name[n] for n in names]
    told = jobs.Stages(outputs / TIMINGS, [*(f"match:{n}" for n in names), "deploy"], TOOK)
    try:
        taken = {m: hosted.page_taken(m) for m, *_ in chosen if (m / "review" / "data.js").exists()}
        build(outputs, chosen, theme, found["url"], told)
        told.start("deploy")
        deploy(found["token"], found["site"], folder(outputs) / SITE, told.share_of_stage)
        record(outputs, taken)
    finally:
        told.stopped.set()
    told.start(None)


def record(outputs: Path, taken: dict[Path, tuple[dict, str]]) -> None:
    """The deploy just made: each match's page as it began (`hosted.page_taken`, `hosted.sent_page`), its time, and the deploy
    counted."""
    found = published(outputs)
    now = datetime.now()
    for match, page in taken.items():
        content, stamp = hosted.sent_page(match, page)
        for old in (match.name, *files.aliases(match)):
            found["matches"].pop(old, None)
            (folder(outputs) / PAGES / f"{old}.json").unlink(missing_ok=True)
        found["matches"][match.name] = {"at": now.isoformat(timespec="seconds"), "stamp": stamp, "code": hosted.code_version()}
        write(folder(outputs) / PAGES / f"{match.name}.json", json.dumps({"data": content["data"]}, ensure_ascii=False) + "\n")
    since = now - timedelta(days=DEPLOYS_DAYS * 2)
    found["deploys"] = [at for at in found["deploys"] if datetime.fromisoformat(at) >= since] + [now.isoformat(timespec="seconds")]
    write(folder(outputs) / PUBLISHED, json.dumps(found, indent=1) + "\n")


def restamp(match: Path, before: str | None) -> None:
    """`hosted.restamp` for the match's page on the site: rebuilt from the same answers by the code that deployed it, the
    page online is the rebuilt one."""
    outputs = files.root(match)
    found = published(outputs)
    record = record_of(found, match)
    if not record or before is None:
        return
    name, saved = record
    if saved["stamp"] != before or saved.get("code") != hosted.CODE or (stamp := hosted.page_stamp(match)) == before:
        return
    write(folder(outputs) / PAGES / f"{name}.json", json.dumps({"data": hosted.page_content(match)["data"]}, ensure_ascii=False) + "\n")
    found["matches"][name] = {**saved, "stamp": stamp}
    write(folder(outputs) / PUBLISHED, json.dumps(found, indent=1) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Put matches' public pages on the Netlify site the app signed in to.")
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument("--theme", default=matches.CLUB)
    parser.add_argument("match", nargs="+", help="A match's folder name (outputs/matches/MATCH), again for each")
    args = parser.parse_args()
    publish(args.outputs, args.match, args.theme)


if __name__ == "__main__":
    main()
