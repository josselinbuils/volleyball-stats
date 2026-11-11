"""The app's icon, a volleyball in the club's colours: two panels in its logo's two main colours (else its main colour and
a darker one, else the app's blue and yellow), the third white, dark seams and a white edge for dark backgrounds. Drawn
as SVG for the pages' favicon and with Pillow for the shortcuts."""

import math
from pathlib import Path
from urllib.parse import quote

import numpy as np
from PIL import Image, ImageDraw

from volleyball_stats import club_settings

DEFAULT = ("#1f6bc4", "#f5c518")
WHITE = "#ffffff"
C, RIM, HALO = 256, 232, 246
# A seam from the centre to past the rim, bending, and one beside it in the next panel; each three times, a third of a
# turn apart.
SEAM = [(256, 256), (256, 170), (205, 85), (95, 48)]
INNER = [(318, 206), (330, 150), (290, 70), (190, 10)]
SEAM_W, RIM_W = 18, 24
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def rotate(p: tuple[float, float], degrees: float) -> tuple[float, float]:
    a = math.radians(degrees)
    x, y = p[0] - C, p[1] - C
    return (C + x * math.cos(a) - y * math.sin(a), C + x * math.sin(a) + y * math.cos(a))


def bezier(points: list[tuple[float, float]], steps: int = 48) -> list[tuple[float, float]]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    out = []
    for k in range(steps + 1):
        t = k / steps
        u = 1 - t
        out.append((u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3, u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3))
    return out


def panel(k: int) -> tuple[list, list, list]:
    """Panel `k`'s outline: out along seam k, round far away, back along seam k + 1."""
    a = [rotate(p, 120 * k) for p in SEAM]
    b = [rotate(p, 120 * (k + 1)) for p in SEAM]
    far = [rotate((C, C - 600), 120 * k + d) for d in (-25, 35, 95)]
    return a, far, b


def colours(club: dict | None, folder: Path = club_settings.FOLDER) -> tuple[str, str]:
    """The two coloured panels' colours for `club` (club_settings.read's)."""
    if not club:
        return DEFAULT
    logo = folder / club["logo"] if club.get("logo") else None
    try:
        found = logo_colours(logo) if logo and logo.exists() else []
    except (OSError, ValueError):
        # A picture Pillow cannot read: the main colour.
        found = []
    if len(found) >= 2:
        pair = found[0], found[1]
    else:
        main = found[0] if found else club.get("accent") or DEFAULT[0]
        pair = main, club_settings.mix(main, "#000000", 0.45)
    # The darker on top.
    return tuple(sorted(pair, key=brightness))


def brightness(colour: str) -> int:
    return sum(int(colour[k : k + 2], 16) for k in (1, 3, 5))


def logo_colours(path: Path) -> list[str]:
    """The logo's main colours, most used first: neither white, black nor grey, each far from the ones before."""
    image = Image.open(path).convert("RGBA")
    image.thumbnail((200, 200))
    pixels = np.asarray(image).reshape(-1, 4)
    rgb = pixels[pixels[:, 3] > 200][:, :3].astype(int)
    high, low = rgb.max(1), rgb.min(1)
    rgb = rgb[(high > 50) & (high - low > 0.3 * high)]
    if not len(rgb):
        return []
    buckets, counts = np.unique(rgb // 32, axis=0, return_counts=True)
    found: list[np.ndarray] = []
    for bucket in buckets[np.argsort(-counts)]:
        colour = np.median(rgb[(rgb // 32 == bucket).all(1)], 0)
        if all(np.abs(colour - other).sum() > 150 for other in found):
            found.append(colour)
    return ["#" + "".join(f"{round(c):02x}" for c in colour) for colour in found]


def ink(pair: tuple[str, str]) -> str:
    """The seams' and rim's colour: the darker panel's, darker still."""
    darker = min(pair, key=brightness)
    return club_settings.mix(darker, "#000000", 0.65)


def svg(pair: tuple[str, str]) -> str:
    def f(p):
        return f"{p[0]:.0f} {p[1]:.0f}"

    def curve(points):
        return f"M{f(points[0])} C{f(points[1])} {f(points[2])} {f(points[3])}"

    dark = ink(pair)
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'><circle cx='{C}' cy='{C}' r='{HALO}' fill='{WHITE}'/>"]
    parts.append(f"<clipPath id='b'><circle cx='{C}' cy='{C}' r='{RIM}'/></clipPath><g clip-path='url(#b)'>")
    for k, fill in enumerate([*pair, WHITE]):
        a, far, b = panel(k)
        parts.append(f"<path fill='{fill}' d='{curve(a)} L{' L'.join(f(p) for p in far)} L{f(b[3])} C{f(b[2])} {f(b[1])} {f(b[0])}Z'/>")
    seams = " ".join(curve([rotate(p, 120 * k) for p in line]) for k in range(3) for line in (SEAM, INNER))
    parts.append(f"<path fill='none' stroke='{dark}' stroke-width='{SEAM_W}' stroke-linecap='round' d='{seams}'/></g>")
    parts.append(f"<circle cx='{C}' cy='{C}' r='{RIM}' fill='none' stroke='{dark}' stroke-width='{RIM_W}'/></svg>")
    return "".join(parts)


def favicon(pair: tuple[str, str]) -> str:
    """The icon as a data: URL, for a page's <link rel=icon>."""
    return "data:image/svg+xml," + quote(svg(pair), safe=" /:='()")


def render(pair: tuple[str, str], size: int = 1024) -> Image.Image:
    """The icon drawn `size` pixels wide, four times larger first for smooth edges."""
    scale = size * 4 / 512

    def at(points):
        return [(x * scale, y * scale) for x, y in points]

    def disc(draw, r, **style):
        draw.ellipse([(C - r) * scale, (C - r) * scale, (C + r) * scale, (C + r) * scale], **style)

    big = round(512 * scale)
    dark = ink(pair)
    ball = Image.new("RGBA", (big, big))
    draw = ImageDraw.Draw(ball)
    for k, fill in enumerate([*pair, WHITE]):
        a, far, b = panel(k)
        draw.polygon(at(bezier(a) + far + bezier(b)[::-1]), fill=fill)
    width = SEAM_W * scale
    for k in range(3):
        for line in (SEAM, INNER):
            points = at(bezier([rotate(p, 120 * k) for p in line]))
            draw.line(points, fill=dark, width=round(width), joint="curve")
            for x, y in (points[0], points[-1]):
                draw.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=dark)
    inside = Image.new("L", (big, big))
    disc(ImageDraw.Draw(inside), RIM, fill=255)
    out = Image.new("RGBA", (big, big))
    edge = ImageDraw.Draw(out)
    disc(edge, HALO, fill=WHITE)
    out.paste(ball, (0, 0), inside)
    disc(edge, RIM + RIM_W / 2, outline=dark, width=round(RIM_W * scale))
    return out.resize((size, size), Image.LANCZOS)


def write(pair: tuple[str, str], path: Path) -> Path:
    """The icon saved at `path`, its format by its suffix (.png, .ico, .icns)."""
    image = render(pair)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".png":
        image.resize((512, 512), Image.LANCZOS).save(path, optimize=True)
    elif path.suffix == ".ico":
        image.save(path, sizes=ICO_SIZES)
    else:
        image.save(path)
    return path
