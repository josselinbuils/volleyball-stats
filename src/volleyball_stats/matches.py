"""The list of the match pages of a site, for hosting several matches.

    uv run python -m volleyball_stats.matches SITE [--theme NAME]
    uv run python -m volleyball_stats.matches --all outputs/matches [--theme NAME]

Each SITE/NAME/ holds a match page (web.py --out SITE/NAME), renamed after the match's date and teams
(SITE/2026-10-25-aspom-begles-vs-talence/) to make its address. SITE/index.html lists them newest
first from their data.js, each linking to its folder. The list is a page of its own (matches_site/, built
from web/ with `npm run build`), its matches in matches.js. `host` rebuilds a match's two hosted pages
and uploads the site, as the review does after each change when the match folder holds publish.json;
`host_all` (`--all`) rebuilds every match online, each carrying the code as built, and uploads them at once.
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
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import files, video_copies, web
from volleyball_stats.web import BRANDING, brand

TEMPLATE = Path(__file__).with_name("matches_site")
# The list's own folders, which no match folder may take.
RESERVED = ("assets", "brand")
REDIRECTS = "redirects.json"
# Where a match folder says how to host it, and where hosted pages send the viewers' reports.
PUBLISH, FEEDBACK = "publish.json", "/volleyball/feedback"
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


def set_scores(data: dict) -> list[tuple[int, int]]:
    """Each set's final points, team 1's first: as given, else from its last rally."""
    if data.get("scores"):
        return [(int(a), int(b)) for a, b in (score.split("-") for score in data["scores"])]
    last = {r["set"]: r["score"] for r in data["rallies"] if r.get("score")}
    return [tuple(last[number]) for number in sorted(last)]


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
    club = data.get("brand") or {}
    logo = folder / club["logo"] if club.get("logo") else None
    share(folder, url, title, description, match_card(data, logo), club.get("name"))


def build(site: Path, theme: str = "aspom", url: str | None = None) -> list[dict]:
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
    shutil.rmtree(site / "brand", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    (site / "matches.html").replace(site / "index.html")
    club = brand(theme, site)
    if club:
        club.pop("sponsors")
    text = json.dumps({"matches": matches, "brand": club}, separators=(",", ":"), ensure_ascii=False)
    # Loaded with its hash in its URL, as data.js: a CDN caching it by URL serves each list its own.
    v = hashlib.sha256(text.encode()).hexdigest()[:10]
    (site / "matches.js").write_text(f"window.MATCHES = {text};\n")
    index = site / "index.html"
    index.write_text(index.read_text().replace('src="matches.js"', f'src="matches.js?v={v}"'))
    if url:
        root = f"{url.rstrip('/')}/"
        for match in matches:
            share_match(site / match["path"], f"{root}{match['path']}")
        name = club["name"] if club else None
        logo = site / club["logo"] if club and club.get("logo") else None
        share(site, root, f"Matchs · {name}" if name else "Matchs", "Les matchs de volley et leurs statistiques.", list_card("Matchs", name, logo), name)
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


def _head(url: str, headers: dict | None = None):
    """`url`'s answer to a HEAD, redirects not followed. Named: Cloudflare refuses Python's own user agent."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "volleyball-stats", **(headers or {})})
    return urllib.request.build_opener(_Stay).open(request, timeout=20)


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
    """The team of the `theme` club: the first if both or neither are."""
    path = match / "teams.json"
    names = [team["name"] or "" for team in json.loads(path.read_text())["teams"]] if path.exists() else []
    return next((k for k, name in enumerate(names, 1) if slug(name).startswith(slug(theme))), 1)


def ensure_publish(match: Path, video: Path, theme: str) -> None:
    """Gives an imported match a publish.json, the hosting taken from another match's, for its upload and backups."""
    target = match / PUBLISH
    others = sorted(match.parent.glob(f"*/{PUBLISH}"))
    if target.exists() or not others or not imported(match, video):
        return
    other = json.loads(others[-1].read_text())
    config = {**{key: other[key] for key in ("site", "url", "upload", "key")}, "club": club_team(match, theme)}
    files.write_text(target, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def fingerprint(password: str) -> str:
    """What the page's cookie holds for `password` (VideoChoice.tsx) and the server lists."""
    return hashlib.sha256(f"{VIDEO_SALT}{password}".encode()).hexdigest()


def update_publish(match: Path, **changes) -> dict:
    path = match / PUBLISH
    config = {**json.loads(path.read_text()), **changes}
    files.write_text(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    return config


def choose(match: Path, video: bool, password: str | None = None) -> dict:
    """The first upload's choice: with the video behind `password`, of which only the fingerprint is
    kept, or without it. ValueError for the video without a password."""
    if not video:
        return update_publish(match, video=False)
    if not password or not password.strip():
        raise ValueError("the video needs a password")
    return update_publish(match, video=True, videoKey=fingerprint(password))


def copies_missing(config: dict) -> bool:
    return any(not config.get(key) or not Path(config[key]).expanduser().exists() for key in video_copies.COPIES)


def add_copies(match: Path, video: Path) -> dict:
    """The video's copies made if missing, then listed: rename refuses a listed copy that is gone."""
    return update_publish(match, **{key: str(path.resolve()) for key, path in video_copies.make(video).items()})


def key_command(service: Path, folder: str, key: str) -> str:
    """The server's shell command making `key` the one that opens the video of `folder`. The list is
    written in place, being mounted in the container by its inode."""
    keys, compose = service / "video_key.conf", shlex.quote(str(service.parent))
    listed = shlex.quote(f'"{folder}:')
    line = shlex.quote(f'"{folder}:{key}" 1;')
    return f"cd {compose} && conf={shlex.quote(str(keys))} && kept=$(grep -vF {listed} \"$conf\"); printf '%s\\n' \"$kept\" {line} | grep . > \"$conf.new\" && cat \"$conf.new\" > \"$conf\" && rm \"$conf.new\" && docker compose exec -T volleyballstats sh -c 'nginx -t -q && nginx -s reload'"


def install_key(config: dict, folder: str) -> None:
    host_name, path = config["upload"].split(":", 1)
    ssh = ["ssh", "-i", str(Path(config["key"]).expanduser()), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host_name]
    subprocess.run([*ssh, key_command(Path(path).parent, folder, config["videoKey"])], check=True, capture_output=True, timeout=60)


def opens(url: str, key: str) -> bool:
    """Whether `url` opens to the cookie holding `key`."""
    try:
        return _head(url, {"Cookie": f"video_key={key}"}).status == 200
    except urllib.error.URLError:
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


def mirror(config: dict) -> None:
    """The site folder made what the server holds, the video copies aside (the films come, a few MB each): the pages and
    films another machine put online come here, so that the upload (`host_all`) leaves them as they are."""
    site = Path(config["site"]).expanduser()
    site.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-rt", "--delete", "--include=*/video/films/*.mp4", "--exclude=*.mp4", "-e", f"ssh -i {Path(config['key']).expanduser()}", config["upload"], f"{site}/"], check=True, capture_output=True)


def upload_command(config: dict, site: Path, rebuilt: list[str], dry: bool = False) -> list[str]:
    """The site's upload, new files put in place together; the video copies only those of the `rebuilt` folders."""
    return [
        "rsync", "-rt", "--delete", "--delay-updates", *(["--dry-run", "--itemize-changes"] if dry else []),
        *[f"--include=/{name}/**.mp4" for name in rebuilt], "--exclude=*.mp4",
        "-e", f"ssh -i {Path(config['key']).expanduser()}", f"{site}/", config["upload"],
    ]  # fmt: skip


def removed_pages(itemized: str, rebuilt: list[str]) -> list[str]:
    """The match folders, other than the `rebuilt` ones, whose page a dry run's output (--itemize-changes) deletes."""
    gone = [line.split(" ", 1)[1].strip() for line in itemized.splitlines() if line.startswith("*deleting ")]
    return sorted({path.split("/")[0] for path in gone if path.endswith("/data.js") and path.count("/") == 1} - set(rebuilt))


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


def host_all(hosted: list[tuple[Path, Path, Path, dict]], theme: str, mirrored: bool = False) -> None:
    """Each match of `hosted` (match, video, court, publish.json) rebuilt as `host` says, in the site as the server holds
    it (`mirror`, unless already `mirrored`), then the site uploaded once, its new files put in place together at the end.
    Nothing goes up when one cannot be rebuilt; among several, the error names the match."""
    if not hosted:
        raise RuntimeError("no match online")
    config = hosted[0][3]
    if any((c["site"], c["upload"]) != (config["site"], config["upload"]) for *_, c in hosted):
        raise RuntimeError("the matches are hosted in different places")
    site = Path(config["site"]).expanduser()
    named = lambda match: f"{match.name}: " if len(hosted) > 1 else ""  # noqa: E731
    # ponytail: a match whose video is gone stops the update of all; skip it, keeping its page, if that happens.
    for match, video, _, c in hosted:
        if "video" not in c:
            raise RuntimeError(f"{named(match)}with or without the video: not chosen")
        # Before the build, which removes the copies of the video it finds in the site folder. Without
        # them the build would take the source, tens of GB.
        if c["video"] and copies_missing(c):
            raise RuntimeError(f"{named(match)}video copies not found: {', '.join(k for k in video_copies.COPIES if not c.get(k) or not Path(c[k]).expanduser().exists())}")
        if c["video"] and not c.get("videoKey"):
            raise RuntimeError(f"{named(match)}the video has no password")
        if not video.exists():
            raise RuntimeError(f"{named(match)}video not found: {video}")
    if not mirrored:
        mirror(config)
    # ponytail: one match at a time, ~13 s each (2 matches: 26 s); rebuild them in parallel if a season makes it long.
    for match, video, court, c in hosted:
        folder = hosted_folder(match, site) or site / match.name
        ensure_review_page(match, video, court, theme)
        make_voice(match)
        if c["video"]:
            adopt_films(match, folder / "video")
            path = lambda key: str(Path(c[key]).expanduser())  # noqa: E731
            web.publish(match, video, court, theme, {"footage": "full", "club": "both", "pictures": True, "copy": True, "light": path("light"), "av1": path("av1"), "small": path("small"), "feedback": FEEDBACK}, folder / "video")
        else:
            shutil.rmtree(folder / "video", ignore_errors=True)
        public = {"footage": "none", "club": c.get("club", 1), "pictures": False, "feedback": FEEDBACK, **({"link": "video/"} if c["video"] else {})}
        web.publish(match, video, court, theme, public, folder)
    paths = {m["name"]: m["path"] for m in build(site, theme, config["url"])}
    guarded = []
    for match, _, _, c in hosted:
        if c["video"]:
            page = f"{config['url'].rstrip('/')}/{paths[match.name]}video/"
            if not protected(page):
                raise RuntimeError(f"{page} opens without the password: not uploaded")
            install_key(c, paths[match.name].rstrip("/"))
            # The players' films, real footage, only behind the password.
            films = sorted((site / paths[match.name] / "video" / "films").glob("*.mp4"))
            if films and not protected(f"{page}films/{films[0].name}"):
                raise RuntimeError(f"{films[0].name} opens without the password: not uploaded")
            guarded.append((page, c["videoKey"]))
    # Real footage only behind the password.
    outside = unguarded_videos(site)
    if outside:
        raise RuntimeError(f"videos outside a password's folder: {', '.join(p.name for p in outside)}: not uploaded")
    rebuilt = [paths[match.name].rstrip("/") for match, *_ in hosted]
    # Pages another machine put online since the mirror (`mirror`) stay.
    dry = subprocess.run(upload_command(config, site, rebuilt, dry=True), check=True, capture_output=True, text=True)
    missing = removed_pages(dry.stdout, rebuilt)
    if missing:
        raise RuntimeError(f"online but not here: {', '.join(missing)}: not uploaded")
    # Films made on another machine stay online (`adopt_films`); should one not come here, nothing goes up.
    unmade = [paths[match.name].rstrip("/") for match, *_ in hosted if not (match / "films").is_dir()]
    lost = removed_films(dry.stdout, unmade)
    if lost:
        raise RuntimeError(f"films online but not here: {', '.join(lost)}: not uploaded")
    subprocess.run(upload_command(config, site, rebuilt), check=True, capture_output=True)
    for page, key in guarded:
        if not opens(page, key):
            raise RuntimeError(f"{page} does not open with its password")


def main() -> None:
    themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
    parser = argparse.ArgumentParser(description="List the match pages of a site folder on its index page.")
    parser.add_argument("site", type=Path, nargs="?", help="Folder holding one match page per subfolder")
    parser.add_argument("--host", type=Path, help="Build this match's hosted pages from its publish.json and upload them")
    parser.add_argument("--all", type=Path, help="Rebuild every match of this folder whose page is online (outputs/matches), then upload them at once")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--court", type=Path)
    parser.add_argument("--theme", default="aspom", help=f"Club theme from branding/NAME/brand.json: {', '.join(themes + ['none'])} (default: aspom)")
    parser.add_argument("--url", help="The list's address, to tag the pages for link previews")
    args = parser.parse_args()
    if args.host:
        return host(args.host, args.video, args.court, args.theme, json.loads((args.host / PUBLISH).read_text()))
    if args.all:
        given = [json.loads(p.read_text()) for p in sorted(args.all.glob(f"*/{PUBLISH}"))]
        config = next((c for c in given if c.get("upload") and c.get("site")), None)
        if config:
            mirror(config)
        return host_all(online(args.all), args.theme, mirrored=config is not None)
    if not args.site:
        parser.error("site or --host")
    matches = build(args.site, args.theme, args.url)
    print(f"{len(matches)} matches: {', '.join(m['path'] for m in matches)} -> {args.site / 'index.html'}")


if __name__ == "__main__":
    main()
