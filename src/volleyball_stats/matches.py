"""The list of the match pages of a site, for hosting several matches.

    uv run python -m volleyball_stats.matches SITE [--theme NAME]

Each SITE/NAME/ holds a match page (web.py --out SITE/NAME), renamed after the match's date and teams
(SITE/2026-10-25-aspom-begles-vs-talence/) to make its address. SITE/index.html lists them newest
first from their data.js, each linking to its folder. The list is a page of its own (matches_site/, built
from web/ with `npm run build`), its matches in matches.js.
"""

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path

from volleyball_stats.web import BRANDING, brand

TEMPLATE = Path(__file__).with_name("matches_site")


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
    """SITE/index.html and matches.js listing SITE/*/'s match pages; returns them."""
    for data in sorted(site.glob("*/data.js")):
        named = site / address(listed(data.parent))
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
    return matches


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
