"""The list of the match pages of a site, for hosting several matches.

    uv run python -m volleyball_stats.matches SITE [--theme NAME]

Each SITE/NAME/ holds a match page (web.py --out SITE/NAME), renamed after the match's date and teams
(SITE/2026-10-25-aspom-begles-vs-talence/) to make its address. SITE/index.html lists them newest
first from their data.js, each linking to its folder. The list is a page of its own (matches_site/, built
from web/ with `npm run build`), its matches in matches.js. `host` rebuilds a match's two hosted pages
and uploads the site, as the review does after each change when the match folder holds publish.json.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

from volleyball_stats import web
from volleyball_stats.web import BRANDING, brand

TEMPLATE = Path(__file__).with_name("matches_site")
# The list's own folders, which no match folder may take.
RESERVED = ("assets", "brand")
# Where a match folder says how to host it, and where hosted pages send the viewers' reports.
PUBLISH, FEEDBACK = "publish.json", "/volleyball/feedback"
# Text files from COMPRESS_FROM bytes get a gzip copy the host sends as it is (nginx gzip_static):
# compressing players.js (5.7 MB) per request cost the first match's host over a second of CPU.
COMPRESSED, COMPRESS_FROM = (".js", ".css", ".html", ".json", ".svg"), 1024


def listed(folder: Path) -> dict:
    """What the list shows of the match page in `folder`, from its data.js."""
    text = (folder / "data.js").read_text()
    data = json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))
    return {
        "path": f"{folder.name}/",
        "name": data["name"],
        "date": data.get("date"),
        "title": data.get("title"),
        "teams": data.get("teams"),
        "scores": data.get("scores"),
        "sets": len({r["set"] for r in data["rallies"]}),
        "rallies": len(data["rallies"]),
    }


def slug(text: str) -> str:
    """Lowercase ASCII words joined by dashes: "ASPOM Bègles" -> "aspom-begles"."""
    return "-".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()))


def address(match: dict) -> str:
    """The folder of a listed match: its date (else its video's name) and its named teams."""
    return slug(" ".join([match["date"] or match["name"], " vs ".join(t["name"] for t in match["teams"] or [] if t["name"])]))


def build(site: Path, theme: str = "aspom") -> list[dict]:
    """SITE/index.html and matches.js listing SITE/*/'s match pages, the site's text files
    compressed (`compress`); returns them."""
    for data in sorted(site.glob("*/data.js")):
        found = address(listed(data.parent))
        # No address from its date and teams (a video named "_.mp4"), or a RESERVED one: it keeps its folder.
        named = site / found if found and found not in RESERVED else data.parent
        if named != data.parent:
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
    compress(site)
    return matches


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


def protected(url: str) -> bool:
    """Whether `url` refuses a visitor without the password: a redirect (to the page that asks
    it) or a refusal, rather than the page."""
    try:
        urllib.request.build_opener(_Stay).open(urllib.request.Request(url, method="HEAD"), timeout=20)
    except urllib.error.HTTPError as error:
        return error.code in (301, 302, 303, 307, 401, 403)
    return False


def host(match: Path, video: Path, court: Path, theme: str, config: dict) -> None:
    """The match's hosted pages rebuilt in `config`'s site folder (publish.json): the public one
    with no footage nor pictures, its copy with both in video/ (the `light` and `av1` copies),
    behind the host's password; the list; then the site uploaded by rsync to `upload` with the ssh
    `key`, once the copy at `url` turns a visitor without the password away. RuntimeError if not."""
    site = Path(config["site"]).expanduser()
    folder = next((p.parent for p in site.glob("*/data.js") if listed(p.parent)["name"] == match.name), site / match.name)
    path = lambda key: config.get(key) and str(Path(config[key]).expanduser())  # noqa: E731
    copy = {"footage": "full", "club": "both", "pictures": True, "copy": True, "light": path("light"), "av1": path("av1"), "feedback": FEEDBACK}
    web.publish(match, video, court, theme, copy, folder / "video")
    web.publish(match, video, court, theme, {"footage": "none", "club": config.get("club", 1), "pictures": False, "link": "video/", "feedback": FEEDBACK}, folder)
    named = {m["name"]: m["path"] for m in build(site, theme)}[match.name]
    if not protected(f"{config['url'].rstrip('/')}/{named}video/"):
        raise RuntimeError(f"{config['url']}{named}video/ opens without the password: not uploaded")
    subprocess.run(["rsync", "-rt", "--delete", "-e", f"ssh -i {Path(config['key']).expanduser()}", f"{site}/", config["upload"]], check=True, capture_output=True)


def main() -> None:
    themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
    parser = argparse.ArgumentParser(description="List the match pages of a site folder on its index page.")
    parser.add_argument("site", type=Path, help="Folder holding one match page per subfolder")
    parser.add_argument("--theme", default="aspom", help=f"Club theme from branding/NAME/brand.json: {', '.join(themes + ['none'])} (default: aspom)")
    args = parser.parse_args()
    matches = build(args.site, args.theme)
    print(f"{len(matches)} matches: {', '.join(m['path'] for m in matches)} -> {args.site / 'index.html'}")


if __name__ == "__main__":
    main()
