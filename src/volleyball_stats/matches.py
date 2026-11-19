"""The list of the match pages of a site, for hosting several matches.

    uv run python -m volleyball_stats.matches SITE [--theme NAME]
    uv run python -m volleyball_stats.matches --all outputs/matches [--only MATCH ...] [--theme NAME]
    uv run python -m volleyball_stats.matches --export ZIP --match outputs/matches/MATCH [--match ...]

Each SITE/NAME/ holds a match page (web.py --out SITE/NAME), renamed after the match's date and teams
(SITE/2026-10-25-aspom-begles-vs-talence/) to make its address. SITE/index.html lists them newest
first from their data.js, each linking to its folder. The list is a page of its own (matches_site/, built
from web/ with `npm run build`), its matches in matches.js. `host` rebuilds a match's two hosted pages
and uploads the site, as the review does after each change when the match folder holds publish.json;
`host_all` (`--all`) rebuilds every match online (those named by `--only` when given), each carrying the code as built, and uploads them at once; those with a
newer copy on the server (`sync.behind`) stay as they are online. `export` (`--export`) zips the public pages and their
list instead, for a host of one's own.
"""

import argparse
import gzip
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import club_settings, files, jobs, points, tables, timeline, video_copies, web
from volleyball_stats.web import CLUB, club_page

TEMPLATE = Path(__file__).with_name("matches_site")
APP_JS = "app.js"
# The list's own folders, which no match folder may take.
RESERVED = ("assets", "club")
REDIRECTS = "redirects.json"
# Where a match folder says how to host it.
PUBLISH = "publish.json"
# The one password of every match's video, in the outputs folder: only this user may read it (`files.write_secret`) and the
# machines share it (`backup.SHARED`); the server and the viewers' cookie hold only its fingerprint. Before 19 Nov each match
# had its own, sealed by a master password, in the match's folder under the same name: removed once the password is set.
PASSWORD = "video_password.json"
PASSWORD_MIN, PASSWORD_MAX = 6, 200
KEY = re.compile(r"[0-9a-f]{64}")
# In a hosted match's folder, what its pages were built from (`made_from`): unchanged, an update only puts the page's code
# in (`web.renew_code`). Online with them: the mirror brings it back with the pages another machine built.
MADE = "made.json"
# What `made_from` leaves out of a match folder: what hosting, syncing and opening the review write without a change of the
# match, and the review page's copy of the page's code (its data counts, without its `v`); files from MADE_BIG bytes count
# by their size and time, not their content.
MADE_SKIP = (PASSWORD, "hosted.json", "hosted_page.json", ".sync.json", "review_timings.json", *tables.CACHES, "photos_stale", "site", "before-rerun", "backup-*", "*.tmp")
MADE_REVIEW = ("assets", "scene3d.js", "review-app.js", "index.html", "data.js")
MADE_BIG = 8 << 20
# The owner's server: the docker compose service whose nginx serves the site (docs/hosting.md); any other reloads nginx itself.
SERVICE = "volleyballstats"
VIDEO_SALT = "volleyball:"
# Text files from COMPRESS_FROM bytes get a gzip copy the host sends as it is (nginx gzip_static):
# compressing players.js (5.7 MB) per request cost the first match's host over a second of CPU.
COMPRESSED, COMPRESS_FROM = (".js", ".css", ".html", ".json", ".svg"), 1024


# A shared link's picture: the size messaging apps show large.
CARD_W, CARD_H = 1200, 630
PREVIEW = "preview.png"
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
# The clubs' Arial where the system has it: OpenCV's own font slashes its zeros, a score's "0" then reads "Ø".
CARD_FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
SHARED_TAGS = re.compile(r"[ \t]*<meta (?:property=\"og:|name=\"twitter:)[^>]*>\n?")
# Where a match page's list is, for its link back to it.
LIST_TAG = re.compile(r'[ \t]*<meta name="list"[^>]*>\n?')
# An update's stages (jobs.Stages) and their seconds before one is measured on this machine, kept in outputs/TIMINGS:
# the site read from the server, each match rebuilt ("match:NAME"), the site uploaded and checked.
TOOK = {"mirror": 10.0, "match": 15.0, "upload": 30.0}
TIMINGS = "hosting_timings.json"
# The site exported for a host of one's own (`export`): outputs/EXPORT, its folder inside the zip unless named in the
# page's language, its stages' durations.
EXPORT, EXPORT_FOLDER, EXPORT_TIMINGS = "export/site.zip", "matchs", "export_timings.json"
EXPORT_TOOK = {"match": 10.0, "zip": 5.0}


def update_stages(outputs: Path, names: list[str]) -> jobs.Stages:
    """The stages of an update of the matches `names`."""
    return jobs.Stages(outputs / TIMINGS, ["mirror", *(f"match:{n}" for n in names), "upload"], TOOK)


def page_of(folder: Path) -> dict:
    """The data.js of the match page in `folder`."""
    text = (folder / "data.js").read_text()
    return json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))


def listed(folder: Path) -> dict:
    """What the list shows of the match page in `folder`, from its data.js."""
    data = page_of(folder)
    return {
        "path": f"{folder.name}/",
        "name": data["name"],
        "date": data.get("date"),
        "title": data.get("title"),
        "teams": data.get("teams"),
        "scores": data.get("scores"),
        "sets": len({r["set"] for r in data["rallies"]}),
        "rallies": len(data["rallies"]),
        "v": data.get("v"),
    }


def slug(text: str) -> str:
    """Lowercase ASCII words joined by dashes: "ASPOM Bègles" -> "aspom-begles"."""
    return "-".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()))


def address(match: dict) -> str:
    """The folder of a listed match: its date (else its video's name) and its named teams."""
    return slug(" ".join([match["date"] or match["name"], " vs ".join(t["name"] for t in match["teams"] or [] if t["name"])]))


set_scores = points.set_scores


def french_date(date: str | None) -> str | None:
    """"2026-10-29" -> "29 octobre 2026"."""
    if not date:
        return None
    year, month, day = date.split("-")
    return f"{int(day)} {MONTHS[int(month) - 1]} {year}"


def _bgr(colour: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    return (int(colour[5:7], 16), int(colour[3:5], 16), int(colour[1:3], 16)) if colour else fallback


def _write(card: np.ndarray, text: str, middle: int, baseline: int, size: int, weight: int, colour: tuple[int, int, int], widest: int) -> None:
    """`text` centred on `middle`, smaller if it would be wider than `widest`."""
    face = cv2.FontFace(str(CARD_FONT) if CARD_FONT.exists() else "sans")
    wide = lambda at: cv2.putText(np.zeros((1, 1, 3), np.uint8), text, (0, 0), (0, 0, 0), face, at, weight)[0][0]  # noqa: E731
    size = min(size, int(size * widest / max(wide(size), 1)))
    cv2.putText(card, text, (middle - wide(size) // 2, baseline), colour, face, size, weight)


def _logo(card: np.ndarray, logo: Path | None, middle: int, top: int, tall: int) -> None:
    """The club's logo over the card, its height `tall`."""
    picture = cv2.imread(str(logo), cv2.IMREAD_UNCHANGED) if logo and logo.exists() else None
    if picture is None:
        return
    picture = cv2.resize(picture, (round(picture.shape[1] * tall / picture.shape[0]), tall), interpolation=cv2.INTER_AREA)
    alpha = picture[:, :, 3:] / 255 if picture.shape[2] == 4 else np.ones((*picture.shape[:2], 1))
    left = middle - picture.shape[1] // 2
    under = card[top : top + tall, left : left + picture.shape[1]]
    under[:] = (picture[:, :, :3] * alpha + under * (1 - alpha)).astype(np.uint8)


def match_card(data: dict, logo: Path | None) -> np.ndarray:
    """The picture of a match's shared link: its teams' colours and names, sets won, sets' points and date. No footage, no player."""
    card = np.zeros((CARD_H, CARD_W, 3), np.uint8)
    teams = data.get("teams") or [{}, {}]
    scores = set_scores(data)
    middle = CARD_W // 2
    for k, team in enumerate(teams[:2]):
        colour = _bgr(team.get("colour"), (70, 70, 70))
        card[:, k * middle : (k + 1) * middle] = colour
        ink = (20, 20, 20) if 0.114 * colour[0] + 0.587 * colour[1] + 0.299 * colour[2] > 170 else (255, 255, 255)
        _write(card, team.get("name") or f"Équipe {k + 1}", middle // 2 + k * middle, 120, 64, 700, ink, 500)
        if scores:
            won = sum((a > b) == (k == 0) for a, b in scores)
            _write(card, str(won), middle // 2 + k * middle, 345, 190, 800, ink, 300)
    # The band of the sets' points.
    card[440:] = (card[440:] * 0.25).astype(np.uint8)
    _write(card, "   ".join(f"{a}-{b}" for a, b in scores), middle, 520, 52, 700, (255, 255, 255), 1100)
    if data.get("date"):
        _write(card, french_date(data["date"]), middle, 585, 34, 500, (215, 215, 215), 1100)
    if logo:
        cv2.circle(card, (middle, 270), 92, (18, 18, 18), -1, cv2.LINE_AA)
        _logo(card, logo, middle, 205, 130)
    return card


def list_card(heading: str, name: str | None, logo: Path | None) -> np.ndarray:
    """The picture of the list's shared link."""
    card = np.full((CARD_H, CARD_W, 3), 18, np.uint8)
    _logo(card, logo, CARD_W // 2, 110, 220)
    _write(card, heading, CARD_W // 2, 440, 84, 700, (255, 255, 255), 1100)
    if name:
        _write(card, name, CARD_W // 2, 515, 40, 500, (200, 200, 200), 1100)
    return card


def _save_if_changed(path: Path, content: bytes) -> None:
    """Keeps a file's date when its content stays: an upload skips it."""
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)


def link_list(folder: Path) -> None:
    """The match page in `folder`, and its video/ one, told where the list is: it links back to it."""
    for index, up in ((folder / "index.html", "../"), (folder / "video" / "index.html", "../../")):
        if index.exists():
            page = LIST_TAG.sub("", index.read_text())
            tag = f'    <meta name="list" content="{up}" />\n'
            _save_if_changed(index, re.sub(r"[ \t]*</head>", lambda _: tag + "  </head>", page, count=1).encode())


def share(folder: Path, url: str, title: str, description: str, card: np.ndarray, site_name: str | None) -> None:
    """`folder`'s page tagged for link previews at its `url`, with `card` as PREVIEW: messaging apps read these without running the page."""
    png = cv2.imencode(".png", card, [cv2.IMWRITE_PNG_COMPRESSION, 9])[1].tobytes()
    _save_if_changed(folder / PREVIEW, png)
    image = f"{url}{PREVIEW}?v={hashlib.sha256(png).hexdigest()[:10]}"
    tags = {"og:type": "website", "og:url": url, "og:title": title, "og:description": description, "og:image": image, "og:image:width": CARD_W, "og:image:height": CARD_H, "og:image:type": "image/png", "og:locale": "fr_FR"}
    if site_name:
        tags["og:site_name"] = site_name
    lines = [f'    <meta property="{key}" content="{html.escape(str(value))}" />\n' for key, value in tags.items()] + ['    <meta name="twitter:card" content="summary_large_image" />\n']
    index = folder / "index.html"
    page = SHARED_TAGS.sub("", index.read_text())
    page = re.sub(r"<title>.*?</title>", lambda _: f"<title>{html.escape(title, quote=False)}</title>", page, count=1)
    page = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + html.escape(description), page, count=1)
    _save_if_changed(index, re.sub(r"[ \t]*</head>", lambda _: "".join(lines) + "  </head>", page, count=1).encode())


def share_match(folder: Path, url: str) -> None:
    """Link previews for the match page in `folder`, whose address is `url`."""
    data = page_of(folder)
    names = [t["name"] for t in data.get("teams") or [] if t.get("name")]
    scores = set_scores(data)
    won = sum(a > b for a, b in scores), sum(b > a for a, b in scores)
    title = " - ".join(names) or data.get("title") or data["name"]
    title += f" · {won[0]}-{won[1]}" if scores else ""
    description = " · ".join(filter(None, [", ".join(f"{a}-{b}" for a, b in scores), french_date(data.get("date")), "Statistiques et replay du match"]))
    club = data.get("club") or {}
    logo = folder / club["logo"] if club.get("logo") else None
    share(folder, url, title, description, match_card(data, logo), club.get("name"))


def build(site: Path, theme: str = CLUB, url: str | None = None) -> list[dict]:
    """SITE/index.html and matches.js listing SITE/*/'s match pages, tagged for link previews at `url`, the
    list's address, when given (`share`), a page whose address changed still found at its old one (`write_redirects`), the site's
    text files compressed (`compress`); returns them."""
    path = site / REDIRECTS
    redirects = json.loads(path.read_text()) if path.exists() else {}
    for data in sorted(site.glob("*/data.js")):
        found = address(listed(data.parent))
        # No address from its date and teams (a video named "_.mp4"), or a RESERVED one: it keeps its folder.
        named = site / found if found and found not in RESERVED else data.parent
        if named != data.parent:
            # A folder named after its video has just been built: no link has its address yet.
            if listed(data.parent)["name"] != data.parent.name:
                redirects[data.parent.name] = named.name
            # ponytail: a new build replaces the folder of the same date and teams, two matches the
            # same day between the same teams would need a number after it.
            shutil.rmtree(named, ignore_errors=True)
            data.parent.rename(named)
    matches = sorted((listed(p.parent) for p in site.glob("*/data.js")), key=lambda m: (m["date"] or "", m["path"]), reverse=True)
    shutil.rmtree(site / "assets", ignore_errors=True)
    for folder in ("club", "brand"):
        shutil.rmtree(site / folder, ignore_errors=True)
    # The app's screens (app.js) are the review server's only.
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True, ignore=shutil.ignore_patterns(APP_JS))
    (site / "matches.html").replace(site / "index.html")
    club = club_page(theme, site)
    if club:
        club.pop("sponsors")
    text = json.dumps({"matches": matches, "club": club}, separators=(",", ":"), ensure_ascii=False)
    # Loaded with its hash in its URL, as data.js: a CDN caching it by URL serves each list its own.
    v = hashlib.sha256(text.encode()).hexdigest()[:10]
    (site / "matches.js").write_text(f"window.MATCHES = {text};\n")
    index = site / "index.html"
    index.write_text(index.read_text().replace('src="matches.js"', f'src="matches.js?v={v}"'))
    for match in matches:
        link_list(site / match["path"])
    if url:
        root = f"{url.rstrip('/')}/"
        for match in matches:
            share_match(site / match["path"], f"{root}{match['path']}")
        name = club["name"] if club else None
        logo = site / club["logo"] if club and club.get("logo") else None
        share(site, root, f"Statistiques · {name}" if name else "Statistiques", "Les matchs de volley et leurs statistiques.", list_card("Statistiques", name, logo), name)
    write_redirects(site, redirects)
    compress(site)
    return matches


def write_redirects(site: Path, redirects: dict[str, str]) -> None:
    """SITE/REDIRECTS and a page at each old address, and its video/, going on to the address's latest one with what the link carries
    (`?video=denied`, `#…`); an address a match uses again is no longer one."""
    latest = {}
    for old, new in redirects.items():
        seen = {old}
        while new in redirects and new not in seen:
            seen.add(new)
            new = redirects[new]
        if old != new and not (site / old / "data.js").exists() and (site / new / "data.js").exists():
            latest[old] = new
    for old, new in latest.items():
        page = (site / new / "index.html").read_text()
        tags = "".join(re.findall(r'<meta property="og:[^>]*>\s*', page))
        for folder, up in ((site / old, "../"), (site / old / "video", "../../")):
            folder.mkdir(parents=True, exist_ok=True)
            to = f"{up}{new}/{'video/' if up == '../../' else ''}"
            (folder / "index.html").write_text(
                f'''<!doctype html><html><head><meta charset="UTF-8" /><meta name="robots" content="noindex, nofollow, noarchive" />{tags}<meta http-equiv="refresh" content="0; url={to}" /><script>location.replace({json.dumps(to)} + location.search + location.hash);</script></head><body><a href="{to}">{html.escape(new)}</a></body></html>
'''
            )
    files.write_text(site / REDIRECTS, json.dumps(latest, indent=1) + "\n")


def compress(site: Path) -> None:
    """NAME.gz beside each text file of `site` from COMPRESS_FROM bytes, dated as it, rewritten when
    the file's date changes; the copies of files gone are removed."""
    for gz in site.rglob("*.gz"):
        if not gz.with_suffix("").exists():
            gz.unlink()
    for path in site.rglob("*"):
        if path.suffix not in COMPRESSED or not path.is_file() or path.stat().st_size < COMPRESS_FROM:
            continue
        gz, when = path.with_name(path.name + ".gz"), path.stat().st_mtime
        if gz.exists() and gz.stat().st_mtime == when:
            continue
        with open(path, "rb") as source, gzip.GzipFile(gz, "wb", compresslevel=9, mtime=0) as out:
            shutil.copyfileobj(source, out)
        os.utime(gz, (when, when))


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args) -> None:
        return None


HEAD_TRIES = 3


def _head(url: str, headers: dict | None = None, wait: float = 2.0):
    """`url`'s answer to a HEAD, redirects not followed. Named: Cloudflare refuses Python's own user agent. A network
    failure (a TLS handshake timing out) is tried again, then a RuntimeError saying so."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "volleyball-stats", **(headers or {})})
    for attempt in range(HEAD_TRIES):
        try:
            return urllib.request.build_opener(_Stay).open(request, timeout=20)
        except urllib.error.HTTPError:
            raise
        except OSError as error:
            if attempt == HEAD_TRIES - 1:
                reason = getattr(error, "reason", error)
                raise RuntimeError(f"{urllib.parse.urlsplit(url).netloc} did not answer ({reason}): nothing uploaded, try again") from error
            time.sleep(wait * (attempt + 1))


def protected(url: str) -> bool:
    """Whether `url` sends a visitor without the password back to the page that asks it (`?video=denied`).
    Any other refusal, a CDN's 403 among them, says nothing of the server's."""
    try:
        _head(url)
    except urllib.error.HTTPError as error:
        return error.code in (301, 302, 303, 307) and "video=denied" in (error.headers.get("Location") or "")
    return False


def unguarded_videos(site: Path) -> list[Path]:
    """The site's videos outside a match's video/ folder, the only one the password guards."""
    return [p for p in site.rglob("*.mp4") if "video" not in p.relative_to(site).parts[:-1]]


def imported(match: Path, video: Path) -> bool:
    """Whether this is a real match from import_match, data/matches/MATCH/MATCH.mp4, not a test clip."""
    return video.parent.name == video.stem == match.name


def club_team(match: Path, theme: str) -> int:
    """The team of the `theme` club: for the app's (CLUB) one of its teams, else its name's first word; the first if
    both or neither are."""
    path = match / "teams.json"
    names = [team["name"] or "" for team in json.loads(path.read_text())["teams"]] if path.exists() else []
    if theme == CLUB:
        club = club_settings.read()
        ours = [k for k, name in enumerate(names, 1) if name in ((club or {}).get("teams") or [])]
        if len(ours) == 1:
            return ours[0]
        theme = (club["name"].split() or [""])[0] if club else ""
    return next((k for k, name in enumerate(names, 1) if theme and slug(name).startswith(slug(theme))), 1)


def ensure_publish(match: Path, video: Path, theme: str) -> None:
    """Gives an imported match a publish.json, the hosting the server's (`sync.server`: the "Site" tab's, else another
    match's), for its upload and backups."""
    from volleyball_stats import sync

    target = match / PUBLISH
    hosting = sync.server(files.root(match)) or {}
    if target.exists() or not all(hosting.get(key) for key in sync.HOSTING) or not imported(match, video):
        return
    config = {**{key: hosting[key] for key in sync.HOSTING}, "club": club_team(match, theme)}
    files.write_text(target, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def fingerprint(password: str) -> str:
    """What the page's cookie holds for `password` (VideoChoice.tsx) and the server lists."""
    return hashlib.sha256(f"{VIDEO_SALT}{password}".encode()).hexdigest()


def update_publish(match: Path, **changes) -> dict:
    path = match / PUBLISH
    config = {**json.loads(path.read_text()), **changes}
    files.write_text(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    return config


def password(outputs: Path) -> str | None:
    """The videos' password, None before it is chosen."""
    text = files.read_secret(outputs / PASSWORD)
    return (json.loads(text).get("password") or None) if text else None


def video_key(outputs: Path) -> str | None:
    """The fingerprint of the videos' password, None before it is chosen."""
    found = password(outputs)
    return fingerprint(found) if found else None


def choose(match: Path, video: bool) -> dict:
    """The first upload's choice: with the video, behind the videos' password, or without it."""
    return update_publish(match, video=bool(video))


def set_password(outputs: Path, new: object) -> None:
    """`new` the password of every match's video from now on: on the server at once when a match is online with its video,
    then kept here, then checked on each. ValueError("password") for one too short or too long; RuntimeError when the server
    does not take it (nothing changes) or a page does not open with it after."""
    if not isinstance(new, str) or len(new.strip()) < PASSWORD_MIN or len(new) > PASSWORD_MAX:
        raise ValueError("password")
    key = fingerprint(new)
    shown = [config for _, _, _, config in online(outputs / "matches") if config["video"]]
    for config in {c["upload"]: c for c in shown}.values():
        try:
            install_key(config, key)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            # Never the command's words: they hold the fingerprint.
            reason = (getattr(error, "stderr", None) or b"").decode(errors="replace").strip()
            raise RuntimeError(reason.splitlines()[-1] if reason else "ssh") from None
    # Kept as the server now has it, then checked.
    files.write_secret(outputs / PASSWORD, json.dumps({"password": new}) + "\n")
    forget_former(outputs / "matches")
    for match, _, _, config in online(outputs / "matches"):
        folder = hosted_folder(match, Path(config["site"]).expanduser())
        if config["video"] and config.get("url") and folder is not None:
            page = f"{config['url'].rstrip('/')}/{folder.name}/video/"
            if not opens(page, key):
                raise RuntimeError(f"{page} does not open with its password")


def forget_former(folder: Path) -> None:
    """The passwords each match of `folder` had before 19 Nov removed, sealed one and fingerprint."""
    for path in folder.glob(f"*/{PASSWORD}"):
        path.unlink()
    for path in folder.glob(f"*/{PUBLISH}"):
        config = json.loads(path.read_text())
        if "videoKey" in config:
            del config["videoKey"]
            files.write_text(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def copies_gone(config: dict) -> list[str]:
    """The copies of the video not listed or not there."""
    return [key for key in video_copies.COPIES if not config.get(key) or not Path(config[key]).expanduser().exists()]


def copies_missing(config: dict) -> bool:
    """Whether a copy of the video is gone, or made at a former height: the match's upload makes it again."""
    return bool(copies_gone(config)) or not all(video_copies.current(key, Path(config[key]).expanduser()) for key in video_copies.COPIES)


def review_cut(match: Path) -> dict:
    """How the copies would be made from the review as it now stands (`timeline.cut`): its page's data, its ball."""
    data = match / "review" / "data.js"
    # ball.js: its name until 16 Nov, on a page not rebuilt since.
    path = next((p for p in (match / "review" / web.VIDEO_JS, match / "review" / "ball.js") if p.exists()), None)
    if not data.exists():
        return {"map": [], "camera": []}
    text = data.read_text()
    page = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
    samples = []
    if path is not None:
        text = path.read_text()
        samples = json.loads(text[text.index("{") : text.rindex("}") + 1]).get("samples", [])
    page.setdefault("lineCalls", web.line_calls(page))
    return timeline.cut(page, np.array(samples, dtype=float).reshape(-1, 3))


def copies_stale(match: Path, config: dict) -> bool:
    """Whether the copies of the video, all there, were made otherwise than the review would now (`review_cut`): a
    correction moved a rally or a touch since, or they were made before 16 Nov. They are made again only when the owner
    says so."""
    if not config.get("video") or copies_missing(config):
        return False
    return video_copies.recorded(match, Path(config["light"]).expanduser()) != review_cut(match)


def add_copies(match: Path, video: Path, share: jobs.Share = jobs.quiet, remake: bool = False) -> dict:
    """The video's copies made as the review now has them (`review_cut`), if one is missing or former, or with `remake`
    made otherwise, then listed (rename refuses a listed copy that is gone); a former one in the copies' folder removed. The
    share made told as it goes."""
    config = json.loads((match / PUBLISH).read_text())
    if not copies_missing(config) and not (remake and copies_stale(match, config)):
        return config
    listed = {key: Path(path).expanduser() for key in video_copies.COPIES if (path := config.get(key))}
    cut = review_cut(match)
    made = video_copies.make(video, cut, share)
    for key, path in listed.items():
        if path.resolve() != made[key].resolve() and path.parent.name == video_copies.FOLDER:
            path.unlink(missing_ok=True)
    video_copies.record(match, made["light"], cut)
    return update_publish(match, **{key: str(path.resolve()) for key, path in made.items()})


def key_command(service: Path, key: str) -> str:
    """The server's shell command making `key` the one that opens every match's video/ folder, then nginx reloaded: in the
    SERVICE container when the folder above `service` composes it, else on the server. The list is written in place, a
    container mounting it by its inode; nginx's map takes the line as a pattern of any folder."""
    keys, compose = service / "video_key.conf", shlex.quote(str(service.parent))
    line = shlex.quote(f'"~^[^:/]+:{key}$" 1;')
    reload = "nginx -t -q && nginx -s reload"
    composed = f"grep -qs '^  {SERVICE}:' docker-compose.yml docker-compose.yaml compose.yml compose.yaml"
    return f"cd {compose} && printf '%s\\n' {line} > {shlex.quote(str(keys))} && if {composed}; then docker compose exec -T {SERVICE} sh -c '{reload}'; else {reload}; fi"


def feedback_address(url: str | None) -> str | None:
    """Where the hosted pages send the viewers' reports: `feedback` beside the list at `url` (/volleyball/feedback for
    https://example.org/volleyball/); none without it."""
    return f"{urllib.parse.urlparse(url).path.rstrip('/')}/feedback" if url else None


def ssh_options(key: str) -> list[str]:
    """ssh's options for the server: its key, never a question (a server's host key is taken the first time, as after a
    move to a new server, and refused if it changes later)."""
    return ["-i", str(Path(key).expanduser()), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]


def ssh_shell(key: str) -> str:
    """The ssh command for rsync's -e."""
    return shlex.join(["ssh", *ssh_options(key)])


def install_key(config: dict, key: str) -> None:
    """`key` made the one opening the videos on `config`'s server (`key_command`)."""
    host_name, path = config["upload"].split(":", 1)
    ssh = ["ssh", *ssh_options(config["key"]), host_name]
    subprocess.run([*ssh, key_command(Path(path).parent, key)], check=True, capture_output=True, timeout=60)


def opens(url: str, key: str) -> bool:
    """Whether `url` opens to the cookie holding `key`."""
    try:
        return _head(url, {"Cookie": f"video_key={key}"}).status == 200
    except urllib.error.HTTPError:
        return False


def ensure_review_page(match: Path, video: Path, court: Path, theme: str) -> None:
    """MATCH/review/ built if missing, without new pictures: a match from the other machine comes without it (`backup.SKIP`),
    and the voice reads it."""
    if not (match / "review" / "data.js").exists():
        web.review_page(match, video, court, theme, pictures=False)


def make_voice(match: Path) -> None:
    """The commentary's missing audio (`voice.py`), which the build then takes; Kokoro is in the voice group only."""
    run = subprocess.run(["uv", "run", "--group", "voice", "python", "-m", "volleyball_stats.voice", str(match.resolve())], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(f"voice: {(run.stderr.strip().splitlines() or [f'exit {run.returncode}'])[-1]}")


def host(match: Path, video: Path, court: Path, theme: str, config: dict) -> None:
    """The match's hosted pages rebuilt in `config`'s site folder (publish.json) and the site uploaded by rsync to
    `upload` with the ssh `key`: the public page, no footage nor pictures. With `video`, also its copy with both in video/
    (the `light`, `av1` and `small` copies), once the copy at `url` turns a visitor without the password away, the
    password opening it after; the commentary's voice made first. RuntimeError if not, or with no `video` chosen."""
    host_all([(match, video, court, config)], theme)


# A line of rsync's --itemize-changes for a file sent or received.
SENT = re.compile(r"^[<>]f")


def files_to_send(itemized: str) -> int:
    """How many files a dry run of rsync (--itemize-changes) says it moves."""
    return sum(1 for line in itemized.splitlines() if SENT.match(line))


def counted(command: list[str], total: int | None, share: jobs.Share = jobs.quiet) -> None:
    """Runs an rsync `command`, its share told as it goes: the files it moved of `total` (the dry run's count; None: asks
    a dry run of the same command first). CalledProcessError, its stderr kept, when it fails."""
    # The options before the paths, as the Mac's openrsync wants them.
    if total is None:
        dry = subprocess.run([command[0], "--dry-run", "--itemize-changes", *command[1:]], check=True, capture_output=True, text=True)
        total = files_to_send(dry.stdout)
    process = subprocess.Popen([command[0], "--itemize-changes", *command[1:]], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    errors: list[str] = []
    # Read apart, else a full pipe of errors would stop rsync.
    reader = threading.Thread(target=lambda: errors.extend(process.stderr), daemon=True)
    reader.start()
    assert process.stdout is not None
    done = 0
    for line in process.stdout:
        if SENT.match(line):
            done += 1
            share(min(1.0, done / total) if total else 1.0)
    process.wait()
    reader.join()
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command, stderr="".join(errors))
    share(1.0)


def mirror(config: dict, share: jobs.Share = jobs.quiet) -> None:
    """The site folder made what the server holds, the video copies aside (the films come, a few MB each): the pages and
    films another machine put online come here, so that the upload (`host_all`) leaves them as they are. The files
    received counted, the share told as it goes."""
    site = Path(config["site"]).expanduser()
    site.mkdir(parents=True, exist_ok=True)
    counted(["rsync", "-rt", "--delete", "--include=*/video/films/*.mp4", "--exclude=*.mp4", "-e", ssh_shell(config["key"]), config["upload"], f"{site}/"], None, share)


def upload_command(config: dict, site: Path, rebuilt: list[str], dry: bool = False) -> list[str]:
    """The site's upload, new files put in place together; the video copies only those of the `rebuilt` folders."""
    return [
        "rsync", "-rt", "--delete", "--delay-updates", *(["--dry-run", "--itemize-changes"] if dry else []),
        *[f"--include=/{name}/**.mp4" for name in rebuilt], "--exclude=*.mp4",
        "-e", ssh_shell(config["key"]), f"{site}/", config["upload"],
    ]  # fmt: skip


def removed_pages(itemized: str, rebuilt: list[str]) -> list[str]:
    """The match folders, other than the `rebuilt` ones, whose page a dry run's output (--itemize-changes) deletes."""
    gone = [line.split(" ", 1)[1].strip() for line in itemized.splitlines() if line.startswith("*deleting ")]
    return sorted({path.split("/")[0] for path in gone if path.endswith("/data.js") and path.count("/") == 1} - set(rebuilt))


def made_from(match: Path, video: Path, court: Path, theme: str, config: dict) -> str:
    """What a match's hosted pages are built from, as one digest: the Python code, the match's folder (`MADE_SKIP` aside), the
    review's page data, its video and court, the copies and the settings of `config`, the club's theme."""
    digest = hashlib.sha256()

    def add(path: Path, name: str) -> None:
        size = path.stat().st_size
        digest.update(f"{name}\0{size}\0".encode())
        digest.update(str(path.stat().st_mtime_ns).encode() if size >= MADE_BIG else path.read_bytes())

    for path in sorted(Path(web.__file__).parent.glob("*.py")):
        add(path, path.name)
    for path in sorted(match.rglob("*")):
        parts = path.relative_to(match).parts
        # publish.json counts as `config`, without its password.
        if not path.is_file() or parts == (PUBLISH,) or any(Path(part).match(skip) for part in parts for skip in MADE_SKIP) or (parts[0] == "review" and parts[1] in MADE_REVIEW):
            continue
        add(path, "/".join(parts))
    from volleyball_stats.review import page_data

    data = page_data(match / "review") or {}
    data.pop("v", None)
    digest.update(json.dumps(data, sort_keys=True).encode())
    for path in [video, *(Path(config[key]).expanduser() for key in ("light", "av1", "small") if config.get(key))]:
        if path.exists():
            digest.update(f"{path}\0{path.stat().st_size}\0{path.stat().st_mtime_ns}".encode())
    if court.exists():
        add(court, "court")
    own = club_settings.FOLDER if theme == CLUB else club_settings.THEMES / theme
    for path in sorted(own.rglob("*")) if own.is_dir() else []:
        if path.is_file():
            add(path, f"club/{path.relative_to(own).as_posix()}")
    # The password reaches the server alone (`set_password`), never the pages; `videoKey`: a match's own until 19 Nov.
    kept = {k: v for k, v in config.items() if k != "videoKey"}
    digest.update(json.dumps({**kept, "theme": theme}, sort_keys=True).encode())
    return digest.hexdigest()[:16]


def made_as(folder: Path) -> str | None:
    """What the hosted pages in `folder` were built from (`made_from`), None if not said."""
    path = folder / MADE
    return json.loads(path.read_text()).get("from") if path.exists() else None


def adopt_films(match: Path, page: Path) -> int:
    """The films online in the hosted page folder `page` (mirrored) taken as `match`'s when this machine has none (made on
    the other machine, not pulled since): the next build keeps them online. How many."""
    films = match / "films"
    if films.exists() or not (page / "data.js").exists():
        return 0
    found = {}
    for name, address in (page_of(page).get("films") or {}).items():
        file, _, query = address.removeprefix("films/").partition("?")
        if (page / "films" / file).exists():
            found[name] = {"hash": query.removeprefix("v="), "file": file, "made": "online"}
    if found:
        films.mkdir()
        for e in found.values():
            shutil.copy2(page / "films" / e["file"], films / e["file"])
        files.write_text(films / "manifest.json", json.dumps(found, indent=1, ensure_ascii=False) + "\n")
    return len(found)


def removed_films(itemized: str, unmade: list[str]) -> list[str]:
    """The `unmade` match folders (no films on this machine) whose films a dry run's output (--itemize-changes) deletes."""
    gone = [line.split(" ", 1)[1].strip() for line in itemized.splitlines() if line.startswith("*deleting ")]
    return sorted({path.split("/")[0] for path in gone if path.endswith(".mp4") and "/films/" in path} & set(unmade))


def hosted_folder(match: Path, site: Path) -> Path | None:
    """The folder of `site` holding `match`'s page, under its name or one it had."""
    known = {match.name, *files.aliases(match)}
    return next((p.parent for p in site.glob("*/data.js") if listed(p.parent)["name"] in known), None)


def online(folder: Path) -> list[tuple[Path, Path, Path, dict]]:
    """The matches of `folder` whose page is online, with their video, court and publish.json."""
    found = []
    for path in sorted(folder.glob(f"*/{PUBLISH}")):
        match, config = path.parent, json.loads(path.read_text())
        if "video" in config and (match / files.SOURCE).exists() and hosted_folder(match, Path(config["site"]).expanduser()):
            given = json.loads((match / files.SOURCE).read_text())
            found.append((match, Path(given["video"]), Path(given["court"]), config))
    return found


def host_all(hosted: list[tuple[Path, Path, Path, dict]], theme: str, mirrored: bool = False, told: jobs.Stages | None = None) -> None:
    """Each match of `hosted` (match, video, court, publish.json) rebuilt as `host` says, in the site as the server holds
    it (`mirror`, unless already `mirrored`), then the site uploaded once, its new files put in place together at the end.
    Nothing goes up when one cannot be rebuilt; among several, the error names the match. Its stages `told` as it goes."""
    if not hosted:
        raise RuntimeError("no match online")
    told = told or update_stages(files.root(hosted[0][0]), [m.name for m, *_ in hosted])
    try:
        upload_all(hosted, theme, mirrored, told)
    finally:
        told.stopped.set()
    told.start(None)


def upload_all(hosted: list[tuple[Path, Path, Path, dict]], theme: str, mirrored: bool, told: jobs.Stages) -> None:
    """`host_all`'s work."""
    config = hosted[0][3]
    key = video_key(files.root(hosted[0][0]))
    if any((c["site"], c["upload"]) != (config["site"], config["upload"]) for *_, c in hosted):
        raise RuntimeError("the matches are hosted in different places")
    site = Path(config["site"]).expanduser()
    feedback = feedback_address(config.get("url"))
    named = lambda match: f"{match.name}: " if len(hosted) > 1 else ""  # noqa: E731
    # ponytail: a match whose video is gone stops the update of all; skip it, keeping its page, if that happens.
    for match, video, _, c in hosted:
        if "video" not in c:
            raise RuntimeError(f"{named(match)}with or without the video: not chosen")
        # Before the build, which removes the copies of the video it finds in the site folder. Without
        # them the build would take the source, tens of GB. A copy at a former height still plays (the review makes it
        # again before an upload).
        if c["video"] and (gone := copies_gone(c)):
            raise RuntimeError(f"{named(match)}video copies not found: {', '.join(gone)}")
        if c["video"] and not key:
            raise RuntimeError(f"{named(match)}the video has no password")
        if not video.exists():
            raise RuntimeError(f"{named(match)}video not found: {video}")
    if not mirrored:
        told.start("mirror")
        mirror(config, told.share_of_stage)
    # ponytail: one match at a time, ~23 s each rebuilt, under a second when only the page's code changed; rebuild them in
    # parallel if a season makes it long.
    renewed = []
    for match, video, court, c in hosted:
        told.start(f"match:{match.name}")
        folder = hosted_folder(match, site) or site / match.name
        ensure_review_page(match, video, court, theme)
        make_voice(match)
        made = made_from(match, video, court, theme, {**c, "feedback": feedback})
        pages = [folder, *([folder / "video"] if c["video"] else [])]
        if made_as(folder) == made and all((page / "data.js").exists() for page in pages):
            # Its data as online: the page's code alone changed. The video's copies stay online as they are.
            for page in pages:
                web.renew_code(page)
            renewed.append(match)
            continue
        # The data once for both pages, then each counts its own share; on the four matches (18 Nov) the data took ~5 s,
        # the page with the video ~16 s, the other ~3 s.
        part = jobs.parts(told.share_of_stage, {"data": 5.0, "video": 16.0 if c["video"] else 0.0, "page": 3.0})
        data = web.computed(match, video, court, part("data"))
        if c["video"]:
            adopt_films(match, folder / "video")
            path = lambda key: str(Path(c[key]).expanduser())  # noqa: E731
            web.publish(match, video, court, theme, {"footage": "full", "club": "both", "pictures": True, "copy": True, "light": path("light"), "av1": path("av1"), "small": path("small"), "feedback": feedback}, folder / "video", part("video"), data)
        else:
            shutil.rmtree(folder / "video", ignore_errors=True)
        public = {"footage": "none", "club": c.get("club", 1), "pictures": False, "feedback": feedback, **({"link": "video/"} if c["video"] else {})}
        web.publish(match, video, court, theme, public, folder, part("page"), data)
        files.write_text(folder / MADE, json.dumps({"from": made}) + "\n")
    told.start("upload")
    paths = {m["name"]: m["path"] for m in build(site, theme, config["url"])}
    guarded = []
    for match, _, _, c in hosted:
        if c["video"]:
            page = f"{config['url'].rstrip('/')}/{paths[match.name]}video/"
            if not protected(page):
                raise RuntimeError(f"{page} opens without the password: not uploaded")
            # The players' films, real footage, only behind the password.
            films = sorted((site / paths[match.name] / "video" / "films").glob("*.mp4"))
            if films and not protected(f"{page}films/{films[0].name}"):
                raise RuntimeError(f"{films[0].name} opens without the password: not uploaded")
            guarded.append(page)
    if guarded:
        install_key(config, key)
    # Real footage only behind the password.
    outside = unguarded_videos(site)
    if outside:
        raise RuntimeError(f"videos outside a password's folder: {', '.join(p.name for p in outside)}: not uploaded")
    rebuilt = [paths[match.name].rstrip("/") for match, *_ in hosted]
    # The video's copies of those built again only: a renewed page has none here (`mirror`), its online ones stay.
    copied = [paths[match.name].rstrip("/") for match, *_ in hosted if match not in renewed]
    # Pages another machine put online since the mirror (`mirror`) stay.
    dry = subprocess.run(upload_command(config, site, copied, dry=True), check=True, capture_output=True, text=True)
    missing = removed_pages(dry.stdout, rebuilt)
    if missing:
        raise RuntimeError(f"online but not here: {', '.join(missing)}: not uploaded")
    # Films made on another machine stay online (`adopt_films`); should one not come here, nothing goes up.
    unmade = [paths[match.name].rstrip("/") for match, *_ in hosted if not (match / "films").is_dir()]
    lost = removed_films(dry.stdout, unmade)
    if lost:
        raise RuntimeError(f"films online but not here: {', '.join(lost)}: not uploaded")
    # Room left on the server after it (it also runs the owner's websites): the video copies take gigabytes.
    from volleyball_stats import backup

    host, ssh = backup.connection(config)
    backup.room(backup.free_gb(host, ssh, config["upload"].split(":", 1)[1]), backup.sent_bytes(dry.stdout, lambda name: site / name))
    counted(upload_command(config, site, copied), files_to_send(dry.stdout), told.share_of_stage)
    for page in guarded:
        if not opens(page, key):
            raise RuntimeError(f"{page} does not open with its password")


def export(chosen: list[tuple[Path, Path, Path]], theme: str, out: Path, told: jobs.Stages | None = None, folder: str = EXPORT_FOLDER) -> None:
    """The public pages of `chosen` (match, video, court) and their list zipped in `out`, as `host` puts them online but
    without what needs its server: the video behind a password, the viewers' reports, the link previews' address. A site
    to open from disk or put on any host, in its `folder`. Its stages `told` as it goes."""
    if not re.fullmatch(r"[\w-]+", folder):
        raise ValueError(folder)
    told = told or jobs.Stages(files.root(chosen[0][0]) / EXPORT_TIMINGS, [*(f"match:{m.name}" for m, *_ in chosen), "zip"], EXPORT_TOOK)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
            site = Path(tmp) / folder
            for match, video, court in chosen:
                told.start(f"match:{match.name}")
                if not video.exists():
                    raise RuntimeError(f"{match.name}: video not found: {video}")
                ensure_review_page(match, video, court, theme)
                make_voice(match)
                given = json.loads((match / PUBLISH).read_text()) if (match / PUBLISH).exists() else {}
                web.publish(match, video, court, theme, {"footage": "none", "club": given.get("club") or club_team(match, theme), "pictures": False}, site / match.name, told.share_of_stage)
            told.start("zip")
            build(site, theme)
            # The gzip copies are for a server sending them as they are (nginx gzip_static): any host compresses by itself.
            made = Path(tmp) / out.name
            paths = [p for p in sorted(site.rglob("*")) if p.is_file() and p.suffix != ".gz"]
            total, done = sum(p.stat().st_size for p in paths) or 1, 0
            with zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as z:
                for path in paths:
                    z.write(path, path.relative_to(site.parent).as_posix())
                    done += path.stat().st_size
                    told.share_of_stage(done / total)
            made.replace(out)
    finally:
        told.stopped.set()
    told.start(None)


def main() -> None:
    themes = sorted(p.parent.name for p in club_settings.THEMES.glob(f"*/{club_settings.THEME_FILE}"))
    parser = argparse.ArgumentParser(description="List the match pages of a site folder on its index page.")
    parser.add_argument("site", type=Path, nargs="?", help="Folder holding one match page per subfolder")
    parser.add_argument("--host", type=Path, help="Build this match's hosted pages from its publish.json and upload them")
    parser.add_argument("--all", type=Path, help="Rebuild every match of this folder whose page is online (outputs/matches), then upload them at once")
    parser.add_argument("--only", action="append", default=[], metavar="MATCH", help="With --all, only this match online (its folder's name), again for each")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--court", type=Path)
    parser.add_argument("--theme", default=CLUB, help=f"Club theme: {CLUB} (the app's), one of branding/NAME/brand.json ({', '.join(themes)}) or none (default: {CLUB})")
    parser.add_argument("--url", help="The list's address, to tag the pages for link previews")
    parser.add_argument("--export", type=Path, metavar="ZIP", help="Zip the public pages of the --match folders and their list, to put on any host")
    parser.add_argument("--match", type=Path, action="append", default=[], help="A match folder to export (outputs/matches/MATCH), again for each")
    parser.add_argument("--folder", default=EXPORT_FOLDER, help=f"The folder inside the zip (default: {EXPORT_FOLDER})")
    args = parser.parse_args()
    from volleyball_stats import sync

    if args.export:
        if not args.match:
            parser.error("--export needs --match")
        chosen = []
        for match in args.match:
            given = json.loads((match / files.SOURCE).read_text())
            chosen.append((match, Path(given["video"]), Path(given["court"])))
        return export(chosen, args.theme, args.export, folder=args.folder)

    if args.host:
        # Never an older version online: the server has a newer copy of this match.
        newer = sync.behind([args.host])
        if newer:
            raise SystemExit(f"newer on the server, from {newer[args.host.name]}: not uploaded")
        return host(args.host, args.video, args.court, args.theme, json.loads((args.host / PUBLISH).read_text()))
    if args.all:
        given = [json.loads(p.read_text()) for p in sorted(args.all.glob(f"*/{PUBLISH}"))]
        config = next((c for c in given if c.get("upload") and c.get("site")), None)
        found = [h for h in online(args.all) if not args.only or h[0].name in args.only]
        told = update_stages(args.all.parent, [m.name for m, *_ in found])
        told.start("mirror")
        newer = sync.behind([m for m, *_ in found])
        found = [h for h in found if h[0].name not in newer]
        told.plan = ["mirror", *(f"match:{m.name}" for m, *_ in found), "upload"]
        for name, other in newer.items():
            print(f"{name}: newer on the server, from {other}: left as it is online")
        if not found:
            told.stopped.set()
            return None
        from volleyball_stats import review

        # Each page as the upload begins: a change made while it runs stays late.
        taken = {m: review.page_taken(m) for m, *_ in found if (m / "review" / "data.js").exists()}
        if config:
            mirror(config, told.share_of_stage)
        host_all(found, args.theme, mirrored=config is not None, told=told)
        for match, page in taken.items():
            review.record_hosted(match, page)
        return None
    if not args.site:
        parser.error("site or --host")
    matches = build(args.site, args.theme, args.url)
    print(f"{len(matches)} matches: {', '.join(m['path'] for m in matches)} -> {args.site / 'index.html'}")


if __name__ == "__main__":
    main()
