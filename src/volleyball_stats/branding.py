"""The club's branding, edited in the app: one per installation, in outputs/brand/ (out of the repository, like
branding/NAME/ with its logo and sponsors), the list, the review and the match pages all showing it. The themes of
branding/ are starting points.
"""

import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

from volleyball_stats import files

BRAND = Path("outputs/brand")
PRESETS = Path("branding")
EXAMPLE = PRESETS / "brand.example.json"
# A picture's data: URL, as the app sends it.
DATA_URL = re.compile(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
MAX_SPONSORS = 12
PICTURES = (".png", ".jpg", ".jpeg", ".webp")


def presets() -> list[dict]:
    return [{"id": p.parent.name, "name": json.loads(p.read_text())["name"]} for p in sorted(PRESETS.glob("*/brand.json"))]


def read(folder: Path = BRAND) -> dict | None:
    """The branding as the app edits it: name, url, accent and header colours, logo and sponsors (files in `folder`)."""
    path = folder / "brand.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    listed = folder / "sponsors" / "sponsors.json"
    sponsors = json.loads(listed.read_text()) if listed.exists() else []
    return {
        "name": data.get("name", ""),
        "url": data.get("url", ""),
        "accent": data["light"]["accent"],
        "header": data["light"]["header"],
        "logo": data.get("logo"),
        "sponsors": [{"name": s["name"], "background": s.get("background", "#ffffff"), "logo": s.get("logo")} for s in sponsors],
    }


def mix(colour: str, other: str, share: float) -> str:
    """`colour` moved `share` of the way to `other`."""
    a, b = (tuple(int(c[k : k + 2], 16) for k in (1, 3, 5)) for c in (colour, other))
    return "#" + "".join(f"{round(x + (y - x) * share):02x}" for x, y in zip(a, b))


def text_on(background: str) -> str:
    r, g, b = (int(background[k : k + 2], 16) for k in (1, 3, 5))
    return "#111111" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"


def colours(previous: dict | None, accent: str, header: str) -> tuple[dict, dict]:
    """The light and dark tokens: the previous ones kept, those following the accent and header made again when they
    changed (a preset's tuned values stay while its colours do)."""
    base = json.loads(EXAMPLE.read_text())
    light, dark = {**base["light"], **(previous or {}).get("light", {})}, {**base["dark"], **(previous or {}).get("dark", {})}
    if light["accent"].lower() != accent.lower():
        light.update(accent=accent, accentHover=mix(accent, "#000000", 0.18), accentText=mix(accent, "#000000", 0.18))
        dark.update(accent=accent, accentHover=mix(accent, "#ffffff", 0.2), accentText=mix(accent, "#ffffff", 0.4))
    if light["header"].lower() != header.lower():
        light["header"], dark["header"] = header, mix(header, "#000000", 0.5)
    return light, dark


def picture(value, folder: Path, stem: str, kept: set[str]) -> str | None:
    """The file of a picture the app sent: a new one (a data: URL) named `stem` and its content's hash, an old one kept
    by its name."""
    if not value:
        return None
    found = DATA_URL.fullmatch(value)
    if found:
        data = base64.b64decode(found[2])
        name = f"{stem}-{hashlib.sha256(data).hexdigest()[:8]}.{'jpg' if found[1] == 'jpeg' else found[1]}"
        files.write_bytes(folder / name, data)
        return name
    if value in kept:
        return value
    raise ValueError("picture")


def save(body: dict, folder: Path = BRAND) -> None:
    """The branding the app sent: name, url, accent, header, logo and sponsors, each picture new or kept."""
    name, url = str(body["name"]).strip(), str(body.get("url") or "").strip()
    accent, header = str(body["accent"]), str(body["header"])
    if not name or not HEX.fullmatch(accent) or not HEX.fullmatch(header) or (url and not re.match(r"https?://", url)):
        raise ValueError("brand")
    sponsors = body.get("sponsors") or []
    if len(sponsors) > MAX_SPONSORS:
        raise ValueError("sponsors")
    path = folder / "brand.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "sponsors").mkdir(exist_ok=True)
    kept = {p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PICTURES}
    kept_sponsors = {p.name for p in (folder / "sponsors").iterdir() if p.is_file() and p.suffix.lower() in PICTURES}
    light, dark = colours(previous, accent, header)
    logo = picture(body.get("logo"), folder, "logo", kept)
    listed = []
    for k, sponsor in enumerate(sponsors):
        background = str(sponsor.get("background") or "#ffffff")
        if not str(sponsor.get("name", "")).strip() or not HEX.fullmatch(background):
            raise ValueError("sponsor")
        file = picture(sponsor.get("logo"), folder / "sponsors", f"sponsor-{k}", kept_sponsors)
        listed.append({"name": sponsor["name"].strip(), "background": background, **({"logo": file} if file else {"text": text_on(background)})})
    data = {**(previous or {}), "name": name, "url": url, "light": light, "dark": dark}
    data.pop("logo", None)
    if logo:
        data["logo"] = logo
    files.write_text(folder / "sponsors" / "sponsors.json", json.dumps(listed, indent=2, ensure_ascii=False) + "\n")
    files.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    used = {logo, "brand.json"}
    for old in folder.iterdir():
        if old.is_file() and old.name not in used:
            old.unlink()
    used = {s.get("logo") for s in listed} | {"sponsors.json"}
    for old in (folder / "sponsors").iterdir():
        if old.is_file() and old.name not in used:
            old.unlink()


def use(preset: str, folder: Path = BRAND) -> None:
    """A theme of branding/ as the club's, its sponsors too; "none" for no branding."""
    if preset != "none" and preset not in {p["id"] for p in presets()}:
        raise LookupError(preset)
    shutil.rmtree(folder, ignore_errors=True)
    if preset != "none":
        shutil.copytree(PRESETS / preset, folder)


def file(rel: str, folder: Path = BRAND) -> Path | None:
    """A picture of the branding by its path in `folder`, for the app to show; None for anything else."""
    parts = Path(rel).parts
    if not parts or len(parts) > 2 or Path(rel).is_absolute() or any(p in ("", ".", "..") or p.startswith((".", "/", "\\")) for p in parts):
        return None
    path = folder.joinpath(*parts)
    return path if path.suffix.lower() in PICTURES and path.is_file() and path.resolve().is_relative_to(folder.resolve()) else None
