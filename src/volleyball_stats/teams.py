"""Teams: which team each player track plays for, and which side of the net each team is on, rally by
rally, so a team keeps its name when the teams change ends.

The torso of a track's boxes (the upper middle of the box, clear of the head, arms and shorts) is
sampled on a few frames spread over the track, and its median colour taken in Lab, where lightness
stays apart from hue. The tracks split into two colour groups by 2-means weighted by track length.
In each rally the group holding most of the left half's player frames (feet court x < 0) is on the
left. A track's team is then the team on its side of the net: players do not cross the net, while
a libero wears another colour than the team and would land in the wrong colour group. Team 1 is the
team on the left at the first rally. A new set starts when the teams change ends after a set break.

    uv run python -m volleyball_stats.teams VIDEO PLAYERS_CSV RALLIES_CSV [--out DIR]

`match.py --players` runs this step, names the teams and dates and titles the match (flags or a
prompt) and writes teams.json.
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.players import Row

SAMPLES = 8
# Height in pixels of the player crops of the naming sheet.
CROP_PX = 160
# Torso box as fractions of the player box: x from, x to, y from, y to.
TORSO = (0.3, 0.7, 0.2, 0.45)
# Frames to the next sampled frame beyond which the reader seeks instead of decoding through.
SEEK = 150
# Seconds between two rallies from which a change of ends is a set break; in a deciding set the
# teams change ends at 8 points within a minute.
SET_BREAK_S = 90.0
# Named jersey colours, English then French names; a detected colour snaps to one of them.
COLOURS = {
    "white": "#f4f4f4", "black": "#151515", "grey": "#8a8a8a", "red": "#d22630", "dark red": "#7a1426",
    "orange": "#f07f1a", "yellow": "#f5d000", "green": "#1e8a3c", "blue": "#1f5fbf", "navy": "#1b2a4a",
    "purple": "#6a3d9a", "pink": "#e86aa6",
}
FRENCH = {
    "blanc": "white", "noir": "black", "gris": "grey", "gray": "grey", "rouge": "red", "bordeaux": "dark red",
    "jaune": "yellow", "vert": "green", "bleu": "blue", "marine": "navy", "bleu marine": "navy", "violet": "purple",
    "rose": "pink",
}


@dataclass
class Teams:
    """Team (1 or 2) per track, the team on the left per rally, each team's detected jersey colour
    (#rrggbb) and a few player crops per team for naming."""

    tracks: dict[int, int]
    left: list[int | None]
    colours: dict[int, str]
    crops: dict[int, list[np.ndarray]]


def torso(image: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Pixels of the torso part of an xyxy box, N×3."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    return image[int(y1 + TORSO[2] * h) : int(y1 + TORSO[3] * h), int(x1 + TORSO[0] * w) : int(x1 + TORSO[1] * w)].reshape(-1, 3)


def by_track(rows: list[Row]) -> dict[int, list[Row]]:
    out: dict[int, list[Row]] = {}
    for r in sorted(rows, key=lambda r: r.frame):
        out.setdefault(r.track, []).append(r)
    return out


def sample(video: Path, rows: list[Row], samples: int = SAMPLES) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Median torso colour (OpenCV 8-bit Lab) of each track over `samples` of its boxes spread over
    the track, and the BGR crop of its tallest sampled box."""
    wanted: dict[int, list[Row]] = {}
    for track_rows in by_track(rows).values():
        for i in np.linspace(0, len(track_rows) - 1, min(samples, len(track_rows))).astype(int):
            wanted.setdefault(track_rows[i].frame, []).append(track_rows[i])
    colours: dict[int, list[np.ndarray]] = {}
    crops: dict[int, np.ndarray] = {}
    tallest: dict[int, int] = {}
    cap, position = cv2.VideoCapture(str(video)), 0
    for frame in sorted(wanted):
        if frame - position > SEEK:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
            position = frame
        while position < frame:
            cap.grab()
            position += 1
        ok, image = cap.read()
        position += 1
        if not ok:
            break
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        for r in wanted[frame]:
            pixels = torso(lab, r.box)
            if len(pixels):
                colours.setdefault(r.track, []).append(np.median(pixels, axis=0))
                x1, y1, x2, y2 = map(int, r.box)
                if y2 - y1 > tallest.get(r.track, 0):
                    # Kept at the naming sheet's height: a 4K match has thousands of tracks.
                    tallest[r.track] = y2 - y1
                    part = image[max(0, y1) : y2, max(0, x1) : x2]
                    crops[r.track] = cv2.resize(part, (max(1, round(part.shape[1] * CROP_PX / part.shape[0])), CROP_PX), interpolation=cv2.INTER_AREA) if part.size else part
    cap.release()
    return {track: np.median(c, axis=0) for track, c in colours.items()}, crops


def two_means(colours: dict[int, np.ndarray], weights: dict[int, float], rounds: int = 20) -> dict[int, int]:
    """Group (0 or 1) of each colour by 2-means weighted by `weights`, started from the darker and
    the lighter half by weight; group 0 is the darker.

    ponytail: two groups only, outliers (liberos, a referee kept by the tracker) join the nearer;
    the side of the net corrects them in `track_teams`.
    """
    tracks = sorted(colours, key=lambda t: colours[t][0])
    x = np.array([colours[t] for t in tracks], float)
    w = np.array([weights[t] for t in tracks], float)
    labels = (np.cumsum(w) > w.sum() / 2).astype(int)
    for _ in range(rounds):
        if labels.min() == labels.max():
            break
        centres = np.array([np.average(x[labels == k], axis=0, weights=w[labels == k]) for k in (0, 1)])
        labels = np.argmin(((x[:, None] - centres[None]) ** 2).sum(axis=2), axis=1)
    if labels.max() and x[labels == 0, 0].mean() > x[labels == 1, 0].mean():
        labels = 1 - labels
    return dict(zip(tracks, labels.tolist()))


def lefts(rows: list[Row], windows: list[tuple[int, int]], group: dict[int, int]) -> list[int | None]:
    """Per rally window, the group on the left: the one with the most frames of its tracks on the left
    half plus frames of the other group's on the right; None when no grouped track plays in it."""
    out: list[int | None] = []
    frames = np.array([r.frame for r in rows])
    left = np.array([r.court[0] < 0 for r in rows])
    groups = np.array([group.get(r.track, -1) for r in rows])
    for start, end in windows:
        inside = (frames >= start) & (frames <= end) & (groups >= 0)
        votes = [(groups[inside] == g) == left[inside] for g in (0, 1)]
        zero, one = int(votes[0].sum()), int(votes[1].sum())
        out.append(None if zero == one else 0 if zero > one else 1)
    return out


def side_group(frames: np.ndarray, xs: np.ndarray, known: list[tuple[tuple[int, int], int]]) -> int | None:
    """Group on the median side of the net of a player's `frames` (court x `xs`) in the rally of
    `known` ((window, group on the left)) it plays most frames of, else in the nearest one; None
    without any."""
    if not known:
        return None
    inside = [int(((frames >= s) & (frames <= e)).sum()) for (s, e), _ in known]
    middle = float(np.median(frames))
    k = int(np.argmax(inside)) if max(inside) else int(np.argmin([max(s - middle, middle - e, 0) for (s, e), _ in known]))
    return known[k][1] if float(np.median(xs)) < 0 else 1 - known[k][1]


def track_teams(rows: list[Row], windows: list[tuple[int, int]], left: list[int | None], group: dict[int, int]) -> dict[int, int]:
    """Group of each track: `side_group` in the rallies with a side known; its colour group without
    any."""
    known = [(w, g) for w, g in zip(windows, left) if g is not None]
    out = {}
    for track, track_rows in by_track(rows).items():
        found = side_group(np.array([r.frame for r in track_rows]), np.array([r.court[0] for r in track_rows]), known)
        out[track] = group.get(track, 0) if found is None else found
    return out


def assign(video: Path, rows: list[Row], windows: list[tuple[int, int]]) -> Teams:
    """Teams of a match's player tracks, numbered so that team 1 is on the left at the first rally
    with a known side."""
    colours, crops = sample(video, rows)
    lengths = {track: len(r) for track, r in by_track(rows).items()}
    group = two_means(colours, lengths) if colours else {}
    left = lefts(rows, windows, group)
    tracks = track_teams(rows, windows, left, group)
    first = next((g for g in left if g is not None), 0)
    # A rally without players keeps the previous rally's sides (the first ones: the first known).
    for k, g in enumerate(left):
        left[k] = (left[k - 1] if k else first) if g is None else g
    team = {first: 1, 1 - first: 2}
    members = {t: sorted((tr for tr, g in tracks.items() if team[g] == t and tr in colours), key=lambda tr: -lengths[tr]) for t in (1, 2)}
    return Teams(
        {tr: team[g] for tr, g in tracks.items()},
        [team[g] for g in left],
        {t: snap(np.median([colours[tr] for tr in members[t]], axis=0)) if members[t] else COLOURS["grey"] for t in (1, 2)},
        {t: [crops[tr] for tr in members[t][:6] if tr in crops] for t in (1, 2)},
    )


def contact_teams(typed: list[tuple], windows: list[tuple[int, int]], left: list[int | None], lead: int) -> list[int | None]:
    """Team of each typed contact (frame, x, y, type, side): the team on its side in its rally, a
    window started `lead` frames early as actions.classify's; None when the rally's sides are unknown."""
    out: list[int | None] = []
    for frame, *_, side in typed:
        k = next((i for i, (s, e) in enumerate(windows) if s - lead <= frame <= e), None)
        team = None if k is None else left[k]
        out.append(None if team is None else team if side == "left" else 3 - team)
    return out


def set_starts(windows: list[tuple[int, int]], left: list[int | None], fps: float) -> list[float]:
    """Start time (s) of each set: 0, then the middle of each break of SET_BREAK_S or more after
    which the teams changed ends. Rallies with unknown sides keep the previous rally's.

    ponytail: a side map wrong on one rally after a long break starts a set, and a set break with a
    rally the segmenter missed on each side of it is still seen; a set won without changing ends
    (the clip ends) is not.
    """
    starts, previous = [0.0], None
    for k, ((start, _), side) in enumerate(zip(windows, left)):
        if side is None:
            continue
        if previous is not None and side != previous[1] and (start - windows[previous[0]][1]) / fps >= SET_BREAK_S:
            starts.append(round((windows[previous[0]][1] + start) / 2 / fps))
        previous = (k, side)
    return starts


def set_numbers(windows: list[tuple[int, int]], starts: list[float], fps: float) -> list[int]:
    """Set (from 1) of each rally: the last set started at or before it."""
    return [max(1, sum(s <= start / fps for s in starts)) for start, _ in windows]


def clock(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def seconds(text: str | float) -> float:
    """Seconds of a time given as a number or as m:ss / h:mm:ss."""
    if isinstance(text, (int, float)):
        return float(text)
    total = 0.0
    for part in str(text).split(":"):
        total = total * 60 + float(part)
    return total


def lab_units(lab: np.ndarray) -> tuple[float, float, float]:
    """OpenCV 8-bit Lab to L* (0-100), a*, b*."""
    return float(lab[0]) * 100 / 255, float(lab[1]) - 128.0, float(lab[2]) - 128.0


def colour_name(lab: np.ndarray) -> str:
    """Name in COLOURS of an OpenCV 8-bit Lab colour. Gym footage greys and blues white jerseys and
    darkens navy ones nearly to black: chroma under 16 counts as white, grey or black, except a
    dark one with a blue cast (navy)."""
    lightness, a, b = lab_units(lab)
    chroma, hue = float(np.hypot(a, b)), float(np.degrees(np.arctan2(b, a)) % 360)
    if lightness < 25 and chroma >= 6 and 190 <= hue < 300:
        return "navy"
    if chroma < 16:
        return "white" if lightness >= 50 else "black" if lightness < 22 else "grey"
    if 190 <= hue < 300:
        return "navy" if lightness < 30 else "blue"
    if 105 <= hue < 190:
        return "green"
    if 70 <= hue < 105:
        return "yellow"
    if 40 <= hue < 70:
        return "orange"
    if 300 <= hue < 345:
        return "pink" if lightness > 65 else "purple"
    return "pink" if lightness > 65 else "dark red" if lightness < 35 else "red"


def snap(lab: np.ndarray) -> str:
    """The named colour of an OpenCV 8-bit Lab colour, as #rrggbb.

    ponytail: about a dozen named colours; --teams takes any #rrggbb.
    """
    return COLOURS[colour_name(lab)]


def parse_colour(text: str) -> str | None:
    """#rrggbb from #rrggbb, #rgb or a colour name in English or French; None when not a colour."""
    text = text.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return text
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return "#" + "".join(c * 2 for c in text[1:])
    return COLOURS.get(FRENCH.get(text, text))


def parse_teams(flag: str) -> list[tuple[str | None, str | None]]:
    """(name, colour) of each team from "Name 1:#1f4e9c,Name 2:rouge"; a part left out is None."""
    out = []
    for part in flag.split(",")[:2]:
        name, _, colour = part.partition(":")
        parsed = parse_colour(colour) if colour.strip() else None
        if colour.strip() and parsed is None:
            raise ValueError(f"Not a colour: {colour!r} (use #rrggbb or a name such as white, rouge, navy)")
        out.append((name.strip() or None, parsed))
    return out + [(None, None)] * (2 - len(out))


def default_name(team: int, french: bool = False) -> str:
    return f"{'Équipe' if french else 'Team'} {team}"


def recording_date(video: Path) -> str:
    """yyyy-mm-dd the video was recorded: its creation_time tag (UTC) in local time, else the file's
    modification date.

    ponytail: a camera writing its local time as UTC shifts the date by a day near midnight only.
    """
    command = ["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "default=nw=1:nk=1", str(video)]
    try:
        tag = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()
        return datetime.fromisoformat(tag).astimezone().date().isoformat()
    except (OSError, subprocess.CalledProcessError, ValueError):
        return datetime.fromtimestamp(video.stat().st_mtime).date().isoformat()


def parse_date(text: str) -> str | None:
    """yyyy-mm-dd of a date given as dd/mm/yyyy or yyyy-mm-dd; None when not a date."""
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def day_month_year(day: str) -> str:
    """dd/mm/yyyy of yyyy-mm-dd."""
    return datetime.strptime(day, "%Y-%m-%d").strftime("%d/%m/%Y")


def default_title(names: list[str]) -> str:
    """The title the page builds when the user typed none."""
    return f"Match {names[0]} vs {names[1]}"


def sheet(teams: Teams, height: int = CROP_PX) -> np.ndarray:
    """The player crops of each team side by side, one row per team, labelled with its number, jersey
    colour and starting side."""
    rows = []
    for team in (1, 2):
        crops = [cv2.resize(c, (max(1, round(c.shape[1] * height / max(1, c.shape[0]))), height)) for c in teams.crops[team] if c.size]
        strip = np.hstack(crops) if crops else np.zeros((height, height, 3), np.uint8)
        label = np.full((36, max(strip.shape[1], 420), 3), 255, np.uint8)
        text = f"Team {team}: {hex_name(teams.colours[team])}, {'left' if team == 1 else 'right'} at the start"
        cv2.putText(label, text, (6, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        strip = np.pad(strip, ((0, 0), (0, label.shape[1] - strip.shape[1]), (0, 0)), constant_values=255)
        rows.append(np.vstack([label, strip]))
    width = max(r.shape[1] for r in rows)
    return np.vstack([np.pad(r, ((0, 8), (0, width - r.shape[1]), (0, 0)), constant_values=255) for r in rows])


def hex_name(colour: str) -> str:
    """Name in COLOURS of a #rrggbb colour."""
    bgr = np.uint8([[[int(colour[i : i + 2], 16) for i in (5, 3, 1)]]])
    return colour_name(cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0, 0])


def ask(teams: Teams, image: Path) -> list[tuple[str | None, str | None]]:
    """Asks the name and colour of each team on the terminal, after writing the crops of each team to
    `image` and opening it in the system viewer; Enter keeps the default name and detected colour."""
    cv2.imwrite(str(image), sheet(teams))
    viewer = shutil.which("open") or shutil.which("xdg-open")
    if viewer:
        subprocess.Popen([viewer, str(image)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = []
    french_names = {english: french for french, english in FRENCH.items() if french != "gray"}
    for team in (1, 2):
        side = "à gauche" if team == 1 else "à droite"
        detected = french_names.get(hex_name(teams.colours[team]), hex_name(teams.colours[team]))
        name = input(f"Nom de l'équipe {team} ({side} au début, {detected}) [{default_name(team, french=True)}] : ").strip()
        while True:
            text = input(f"Couleur de l'équipe {team} [détectée : {detected}] : ").strip()
            colour = parse_colour(text) if text else None
            if not text or colour:
                break
            print("Saisir #rrggbb ou un nom de couleur : blanc, noir, rouge, marine, bleu, vert, jaune...")
        out.append((name or None, colour))
    return out


def ask_date(detected: str) -> str:
    """Asks the match's date on the terminal; Enter keeps `detected`."""
    while True:
        text = input(f"Date du match [détectée : {day_month_year(detected)}] : ").strip()
        day = parse_date(text) if text else detected
        if day:
            return day
        print("Format : jj/mm/aaaa ou aaaa-mm-jj")


def ask_title(names: list[str]) -> str | None:
    """Asks the match's title on the terminal; None for the default one (Enter), which the page
    translates."""
    default = default_title(names)
    title = input(f"Titre du match [{default}] : ").strip()
    return title if title and title != default else None


def parse_score(text: str) -> str | None:
    """"25-21" of a set score given as 25-21, 25–21 or 25:21, team 1 first; None when not a score."""
    found = re.fullmatch(r"\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*", text)
    return f"{int(found[1])}-{int(found[2])}" if found else None


def ask_sets(starts: list[str], names: list[str], ask_starts: bool = True, ask_scores: bool = True) -> tuple[list[str], list[str | None]]:
    """Asks on the terminal, set by set, to confirm or correct its start from set 2 (Enter keeps the
    detected one) and its final score (Enter leaves it unknown)."""
    print(f"Sets détectés : {len(starts)}. Les débuts de set se corrigent aussi dans teams.json.")
    out: list[str] = []
    scores: list[str | None] = []
    for k, start in enumerate(starts, 1):
        while ask_starts and k > 1:
            text = input(f"Début du set {k} [détecté : {start}] : ").strip()
            try:
                typed = seconds(text) if text else seconds(start)
            except ValueError:
                typed = -1.0
            if typed > seconds(out[-1]):
                start = clock(typed)
                break
            print(f"Format : m:ss ou h:mm:ss, après le début du set {k - 1} ({out[-1]})")
        out.append(start)
        score = None
        while ask_scores:
            text = input(f"Score final du set {k} ({names[0]} – {names[1]}) [vide si inconnu] : ").strip()
            score = parse_score(text) if text else None
            if not text or score:
                break
            print(f"Format : 25-21, les points de {names[0]} d'abord")
        scores.append(score)
    return out, scores


def settle(
    path: Path,
    teams: Teams,
    windows: list[tuple[int, int]],
    fps: float,
    flag: str | None,
    interactive: bool,
    recorded: str,
    day: str | None = None,
    title: str | None = None,
    sets: list[str] | None = None,
    scores: list[str] | None = None,
) -> dict:
    """teams.json's content: names and colours from `flag`, the match's date (yyyy-mm-dd) from `day`,
    its title from `title` ("" for the default one), the set starts (m:ss or h:mm:ss) from `sets` and
    the sets' final scores ("25-21", team 1 first, "" when unknown) from `scores`; else each from the
    existing file; else asked when `interactive` and the file is new; else the defaults: Team 1 and 2
    in the detected colours, `recorded` (the video's recording date), no title (the page builds it),
    the detected set starts and unknown scores. Jersey colours and starting sides always come from
    `teams`. Written back to `path`."""
    if sets is not None:
        try:
            sets = [clock(seconds(s)) for s in sets]
        except ValueError:
            raise ValueError(f"Not set starts: {','.join(sets)!r} (use m:ss or h:mm:ss, e.g. 0:00,24:10)") from None
    if scores is not None:
        parsed = [parse_score(s) if s.strip() else None for s in scores]
        bad = [s for s, p in zip(scores, parsed) if s.strip() and p is None]
        if bad:
            raise ValueError(f"Not a set score: {bad[0]!r} (use 25-21, team 1 first)")
        scores = parsed
    old = json.loads(path.read_text()) if path.exists() else {}
    prompt = interactive and not old
    given = parse_teams(flag) if flag else None
    if given is None and prompt:
        given = ask(teams, path.with_suffix(".jpg"))
    entries = []
    for team in (1, 2):
        before = old.get("teams", [{}, {}])[team - 1]
        name, colour = given[team - 1] if given else (before.get("name"), before.get("colour"))
        entries.append({"name": name, "colour": colour, "jersey": teams.colours[team], "start": "left" if team == 1 else "right"})
    if day is None:
        day = old.get("date") or (ask_date(recorded) if prompt else recorded)
    if title is not None:
        title = title.strip() or None
    elif old:
        title = old.get("title")
    elif prompt:
        title = ask_title([e["name"] or default_name(k, french=True) for k, e in enumerate(entries, 1)])
    starts = sets or old.get("sets") or [clock(s) for s in set_starts(windows, teams.left, fps)]
    known = scores if scores is not None else old.get("scores") or []
    if prompt and (sets is None or scores is None):
        names = [e["name"] or default_name(k, french=True) for k, e in enumerate(entries, 1)]
        starts, asked = ask_sets(starts, names, sets is None, scores is None)
        known = asked if scores is None else known
    if len(known) > len(starts):
        raise ValueError(f"{len(known)} set scores for {len(starts)} sets: give the set starts too")
    data = {"teams": entries, "date": day, "title": title, "sets": starts, "scores": [*known, *[None] * (len(starts) - len(known))]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Tell the two teams apart and follow their side of the net, rally by rally.")
    parser.add_argument("video", type=Path)
    parser.add_argument("players", type=Path, help="Player tracks CSV from players.py")
    parser.add_argument("rallies", type=Path, help="start_frame,end_frame CSV from rallies.py")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    from volleyball_stats.attribution import read_players

    with open(args.rallies) as f:
        windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]
    teams = assign(args.video, read_players(args.players), windows)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.video.stem}_tracks.csv"
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([["track", "team"], *sorted(teams.tracks.items())])
    print(f"Team 1 {teams.colours[1]}, Team 2 {teams.colours[2]}; left per rally: {' '.join(str(g or '?') for g in teams.left)} -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
