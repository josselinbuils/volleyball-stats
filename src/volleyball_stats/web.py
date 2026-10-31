"""The match page: a static site built from the pipeline's outputs, index.html + data.js + the video.

    uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court COURT_JSON [--club N] [--footage MODE] [--pictures] [--out DIR] [--copy-video] [--theme NAME]

The page (site/, built from web/ with `npm run build` and copied as is) reads the match from data.js,
a script rather than fetched JSON so it opens from the disk by double-clicking index.html, and the
players' positions over the whole video from players.js, which it loads once it has rendered. Every
path is relative: the site directory serves as plain static files. The page holds no footage by
default (`--footage none`): its moments replay on the top view of the court. `--footage full` adds
the video, `blur-opponents` the video with the team other than the `--club` one blurred (blur.py),
`blur-all` the video with both teams blurred. The cards show a silhouette, the `--club` team's
players (both teams' with `--club both`) their picture with `--pictures`. MATCH/page.json remembers these choices: a later build
without them keeps them, a flag changes only its own (`--no-pictures` takes the pictures off); the
blurred copy is kept beside the outputs and made again only when the player tracks change. The video is symlinked unless --copy-video, for hosting; a
poster frame stands in for it until it plays. Teams (names, colours,
sets, the match's date and title, the sets' final scores) come from teams.json, written by match.py
--players, with each player's identity for the whole match (identities.csv) and the score
(points.csv); a teams.json from before the date takes the video's recording date. --theme picks a
club theme from branding/NAME/brand.json (logo, colours), `none` for the neutral one.
"""

import argparse
import base64
import csv
import hashlib
import json
import shutil
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode, files
from volleyball_stats.actions import LEAD_S, UNDER_PX, player_under
from volleyball_stats.attribution import GAP_S, NO_PLAYER, box_at
from volleyball_stats.court import LENGTH, WIDTH, Calibration, zone
from volleyball_stats.identity import lookup, named, read_identities, read_names
from volleyball_stats.points import landing
from volleyball_stats.teams import parse_colour, parse_date, recording_date

TEMPLATE = Path(__file__).with_name("site")
BRANDING = Path("branding")
# Player positions are kept every STEP_S seconds over the whole video, to the centimetre.
STEP_S = 0.1
# A player is on the court with their feet within SERVE_M behind an end line (serving) and SIDE_M
# outside a sideline; the bench stands farther.
SERVE_M, SIDE_M = 3.0, 1.0
# The ball's place in the picture during the rallies, every BALL_STEP_S, for the video's zoom on it.
BALL_STEP_S = 0.08
POSTER_WIDTH = 800
# What the page shows of the video: nothing, all of it, or the video with some players blurred.
FOOTAGE = ("none", "full", "blur-opponents", "blur-all")
# Video files a previous build may have left in the site folder, by lowercase extension.
VIDEOS = (".mp4", ".mov", ".m4v")
# The club logo shows at most 64 px tall, the players' pictures about 240 px: kept at twice that for
# sharp high-density screens, never enlarged. The pictures are 3 wide for 4 tall, like a photo.
LOGO_PX, PHOTO_PX, PHOTO_RATIO = 128, 480, 0.75
# The cards' pictures: in the pieces of a player the review shows and the user left unmarked (sure
# to be them), PHOTO_SAMPLES moments each, alone, on the court (ON_COURT m around it at most: not
# walking past the camera) and with room around them for a centred picture (ROOM of their height
# each side); of those, the PHOTO_PICKS where they stand tallest, the closest to the camera,
# PHOTO_MORE more when none faces the camera (FACED or less), and in the player's kit: their top's
# colour within KIT (Lab) of its median over their KIT_SAMPLES tallest moments in play (a rally,
# IN_PLAY_S around it) inside the court's lines, not a hoodie put on during a break or on the bench. Scored on facing the camera (`looks`,
# weighing FACING), the whole body seen (its keypoints), sharpness (weighing SHARP) and size (SIZE)
# against the player's other moments, less CROWD per other person as large as OTHER of them in the
# picture; the scores kept in MATCH/PHOTO_SCORES, a 4K frame costing a seek.
PHOTO_SAMPLES, ON_COURT, ROOM, PHOTO_PICKS, PHOTO_MORE, FACED = 24, 1.0, 0.35, 24, 72, 0.3
IN_PLAY_S, KIT_SAMPLES, KIT = 3.0, 12, 40.0
# And looking like the pictures of them the user confirmed: their re-identification embeddings'
# median cosine to those within LIKE of the player's best moment (players' own ranges differ: on the
# first ASPOM match, 0.72-0.83 for one, 0.46-0.70 for another seen in a hoodie too); kept in
# MATCH/PHOTO_VECTORS.
LIKE, PHOTO_VECTORS = 0.08, "photo_vectors.npz"
# Each player's PHOTO_CHOICES best moments, the one shown first, kept in MATCH/PHOTO_CANDIDATES by
# team:identity for the review to offer; the one the user picked instead, by name, in
# MATCH/PHOTO_PICKED.
PHOTO_CHOICES, PHOTO_CANDIDATES, PHOTO_PICKED = 8, "photo_candidates.json", "photo_choices.json"
FACING, SHARP, CROWD, OTHER, SIZE, PHOTO_SCORES = 3.0, 2.0, 0.5, 0.3, 2.0, "photo_scores.json"
# The picture: from HEADROOM above the head (its box's top) down BUST of the body's height (the
# waist: a closer face lacks detail in 4K), centred on the shoulders' middle, at PHOTO_RATIO;
# keypoints under KEYPOINT confidence are not used.
BUST, HEADROOM, KEYPOINT = 0.55, 0.08, 0.5
# Then upscaled 4 times by Nomos (4xNomosWebPhoto_RealPLKSR, CC-BY-4.0, trained on degraded web
# photos: cleaner and firmer than the video's compressed pixels, no face made up), downloaded once
# into UPSCALER, and brought back to PHOTO_PX tall.
UPSCALER = Path("models/4xNomosWebPhoto_RealPLKSR.safetensors")
SMEARS, CLEAN = 120, 200
UPSCALER_URL = "https://huggingface.co/Phips/4xNomosWebPhoto_RealPLKSR/resolve/main/4xNomosWebPhoto_RealPLKSR.safetensors"
# Last, the gym's yellow cast taken off by WARMTH of a gray world balance, local contrast (CLAHE at
# CONTRAST), and, without the upscaler, sharpened by SHARPEN (unsharp mask).
WARMTH, CONTRAST, SHARPEN = 0.35, 1.5, 0.4
# A sponsor's picture on the 3D view's boards, in pixels tall.
SPONSOR_PX = 160


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path) as f:
        return list(csv.DictReader(f))


def track_feet(track: int, frame: int, players: dict[int, list[dict]], gap: int) -> tuple[float, float] | None:
    """Court feet of `track` at `frame`, interpolated over a detection gap of up to `gap` frames on
    each side as attribution.py does; None when the track has no row that close."""
    feet = {f: (float(p["court_x"]), float(p["court_y"])) for f in range(frame - gap, frame + gap + 1) for p in players.get(f, []) if int(p["track"]) == track}
    return box_at(feet, frame, gap)


def spot(kind: str, ball: tuple[float, float], boxes: np.ndarray, feet: np.ndarray, calibration: Calibration, reach: float) -> tuple[float, float] | None:
    """Court position of a contact without an attributed player: the ball's floor projection for a
    floor contact, exact for a ball on the floor; otherwise the feet of the player under the ball,
    among the player boxes nearest to it horizontally (`reach` pixels at least) the one whose top
    is nearest to it. A far player behind the near one, or a block, can take the touch."""
    if kind == "floor":
        return tuple(calibration.to_court(np.array([ball], float))[0].tolist())
    if not len(boxes):
        return None
    gap = np.maximum(0, np.maximum(boxes[:, 0] - ball[0], ball[0] - boxes[:, 2]))
    return tuple(feet[player_under(ball, boxes, max(reach, gap.min()))].tolist())


def zone_cells() -> list[dict]:
    """The 12 zone rectangles of the court, numbered by `zone` at their center."""
    cells = []
    for x0, x1 in ((-9, -3), (-3, 0), (0, 3), (3, 9)):
        for y0 in (-4.5, -1.5, 1.5):
            cells.append({"zone": zone((x0 + x1) / 2, y0 + 1.5), "x": x0, "y": y0, "w": x1 - x0, "h": 3})
    return cells


def result(contact: dict, after: dict | None) -> str:
    """Outcome of a contact from the next one of its rally, the landing judged as the score's
    (`points.landing`): "point" when that is the ball landing in the court on the other side of the
    net, or at the foot of the net after a block (the attacker sent it there); "error" when it lands
    on the contact's side, out, at the foot of the net or in the net; "play" otherwise, and for the
    floor and net contacts themselves."""
    if contact["type"] in ("floor", "net") or after is None or after["type"] not in ("floor", "net"):
        return "play"
    where = landing(after["x"], after["y"]) if after["type"] == "floor" and after["x"] is not None else None
    if where == "net" and contact["type"] == "block":
        return "point"
    return "point" if where == "in" and after["side"] != contact["side"] else "error"


def settle(found: list[dict], winners: list[int | None]) -> None:
    """Each rally's last touch, in `found` (the page's contacts), a point when its team won the rally
    (`winners`, by rally), else a fault: the points step also weighs the next serve, where a landing
    alone leaves half the rallies of the first ASPOM match to nobody."""
    last = {c["rally"]: c for c in found if c["type"] not in ("floor", "net")}
    for rally, c in last.items():
        if winners[rally] is not None and c["team"] is not None:
            c["result"] = "point" if winners[rally] == c["team"] else "error"


# The player a (track, frame) shows on the page, None without a track; or the identity (team,
# number) said instead.
Who = Callable[..., int | None]


def contacts(typed: list[dict], windows: list[tuple[int, int]], players: dict[int, list[dict]], fps: float, calibration: Calibration, reach: float, who: Who = lambda track, *_: track, said: dict[int, tuple[int, int]] | None = None) -> list[dict]:
    """The page's contacts from the actions CSV rows: time, type, side, team (None without teams),
    rally index, court position, zone, result and the attributed track's player (`who`), or the
    identity the review `said` touched it (by frame); an ace
    also has the player who missed it (`receiver`). A contact with a track is placed at that
    player's feet, else by `spot`. `players` holds the player CSV rows by frame."""
    lead, gap = round(LEAD_S * fps), round(GAP_S * fps)
    out: list[dict] = []
    for row in typed:
        frame, kind = int(row["frame"]), row["type"]
        rally = next(i for i, (start, end) in enumerate(windows) if start - lead <= frame <= end)
        here = players.get(frame, [])
        boxes = np.array([[float(p[k]) for k in ("x1", "y1", "x2", "y2")] for p in here]).reshape(-1, 4)
        feet = np.array([[float(p["court_x"]), float(p["court_y"])] for p in here]).reshape(-1, 2)
        # A floor contact after the floor one is a dead ball's, anywhere in the air.
        dead = kind == "floor" and bool(out) and out[-1]["rally"] == rally and out[-1]["type"] == "floor"
        track = int(row["track"]) if row.get("track") else None
        xy = None
        if not dead:
            xy = track_feet(track, frame, players, gap) if track is not None else None
            xy = xy or spot(kind, (float(row["x"]), float(row["y"])), boxes, feet, calibration, reach)
        out.append({
            "t": round(frame / fps, 2),
            "type": kind,
            "side": row["side"],
            "team": int(row["team"]) if row.get("team") else None,
            "rally": rally,
            "x": None if xy is None else round(xy[0], 2),
            "y": None if xy is None else round(xy[1], 2),
            "zone": None if xy is None else zone(*xy),
            "person": who(track, frame, (said or {}).get(frame)),
        })
    for k, (contact, after) in enumerate(zip(out, out[1:] + [None])):
        contact["result"] = result(contact, after if after and after["rally"] == contact["rally"] else None)
        if contact["type"] == "serve" and contact["result"] == "point":
            frame = int(typed[k + 1]["frame"])
            contact["receiver"] = receiver(after, players.get(frame, []), lambda track: who(track, frame))
    return out


def receiver(landing: dict, here: list[dict], who: Callable[[int], int | None]) -> int | None:
    """The player who missed an ace: on the side it lands on, the nearest to where it lands.

    ponytail: the nearest player, not the one whose zone it was; None without a landing position.
    """
    if landing["x"] is None:
        return None
    mine = [p for p in here if (float(p["court_x"]) < 0) == (landing["x"] < 0)]
    if not mine:
        return None
    nearest = min(mine, key=lambda p: np.hypot(float(p["court_x"]) - landing["x"], float(p["court_y"]) - landing["y"]))
    return who(int(nearest["track"]))


def player_samples(rows: Iterable[dict], step: int, frame_count: int, who: Who = lambda track, _: track) -> list[list[float]]:
    """The players' court feet every `step` frames of the video, from frame 0, each sample a flat
    [player, x, y, ...] list rounded to the centimetre, `who` naming the player of a row's track."""
    samples: list[list[float]] = [[] for _ in range(-(-frame_count // step))]
    for row in rows:
        frame = int(row["frame"])
        if frame % step == 0 and frame // step < len(samples):
            samples[frame // step] += [who(int(row["track"]), frame), round(float(row["court_x"]), 2), round(float(row["court_y"]), 2)]
    return samples


def playing_time(samples: list[list[float]], step: int, windows: list[tuple[int, int]], sets: list[int], fps: float) -> dict[int, dict[str, float]]:
    """Seconds each player stood on the court during the rallies (`windows`, of `sets`), by set, from
    the samples every `step` frames (`player_samples`)."""
    out: dict[int, dict[str, float]] = {}
    for (start, end), number in zip(windows, sets):
        for k in range(-(-start // step), min(end // step + 1, len(samples))):
            sample = samples[k]
            for p, x, y in zip(sample[::3], sample[1::3], sample[2::3]):
                if p is not None and abs(x) <= LENGTH / 2 + SERVE_M and abs(y) <= WIDTH / 2 + SIDE_M:
                    by_set = out.setdefault(int(p), {})
                    by_set[str(number)] = by_set.get(str(number), 0.0) + step / fps
    return {p: {s: round(v, 1) for s, v in by_set.items()} for p, by_set in out.items()}


def people(track_team: dict[int, int], identities: list[tuple[int, int, int, int, int]], names: dict[tuple[int, int], dict] | None = None) -> tuple[Who, dict[int, dict]]:
    """The page's players, keyed 0, 1, ... as they are first asked for: one per identity
    (identities.csv's rows) with its team, number and the name and jersey number the user gave it
    (`names`, by (team, identity)), one per track without identity, with its team and no number;
    and `who`, the key of the player a track shows at a frame, or of the identity `said` instead."""
    names = names or {}
    by_track: dict[int, list] = {}
    for r in identities:
        by_track.setdefault(r[0], []).append(r)
    keys: dict[tuple, int] = {}
    table: dict[int, dict] = {}

    def who(track: int | None, frame: int, said: tuple[int, int] | None = None) -> int | None:
        if track is None and said is None:
            return None
        found = said or lookup(by_track.get(track, []), track, frame)
        name = ("identity", *found) if found else ("track", track)
        if name not in keys:
            keys[name] = len(keys)
            given = names.get(found, {}) if found else {}
            table[keys[name]] = {"team": found[0] if found else track_team.get(track, 1), "number": found[1] if found else None, "jersey": given.get("jersey"), "name": given.get("name")}
        return keys[name]

    return who, table


def hand_edited(parse: Callable[[str], str | None], text: str, kind: str) -> str:
    """A date or colour of teams.json, which the owner may edit by hand, as `parse` writes it;
    ValueError when `parse` cannot read it: the page would break on it."""
    found = parse(str(text))
    if found is None:
        raise ValueError(f"teams.json: {text!r} is not {kind}")
    return found


def read_teams(match: Path) -> dict | None:
    """teams.json of a match run with --players, None without it."""
    path = match / "teams.json"
    return json.loads(path.read_text()) if path.exists() else None


def brand(name: str, site: Path) -> dict | None:
    """The club theme branding/NAME/brand.json with its logo copied into the site, and its sponsors from
    branding/NAME/sponsors/sponsors.json (git-ignored: brands stay off the repository) with their
    pictures inlined (the 3D view paints them, which a file:// page cannot do from a file); None for `none`."""
    if name == "none":
        return None
    path = BRANDING / name / "brand.json"
    if not path.exists():
        themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
        raise SystemExit(f"Unknown theme {name!r}: available themes are {', '.join(themes + ['none'])}")
    data = json.loads(path.read_text())
    if data.get("logo"):
        (site / "brand").mkdir(parents=True, exist_ok=True)
        logo = cv2.imread(str(path.parent / data["logo"]), cv2.IMREAD_UNCHANGED)
        if logo.shape[0] > LOGO_PX:
            logo = cv2.resize(logo, (round(logo.shape[1] * LOGO_PX / logo.shape[0]), LOGO_PX), interpolation=cv2.INTER_AREA)
        target = site / "brand" / f"{Path(data['logo']).stem}.png"
        cv2.imwrite(str(target), logo)
        data["logo"] = f"brand/{target.name}"
    sponsors = path.parent / "sponsors"
    data["sponsors"] = json.loads((sponsors / "sponsors.json").read_text()) if (sponsors / "sponsors.json").exists() else []
    # A sponsor without a logo shows as text.
    for sponsor in (s for s in data["sponsors"] if s.get("logo")):
        picture = cv2.imread(str(sponsors / sponsor["logo"]), cv2.IMREAD_UNCHANGED)
        picture = cv2.resize(picture, (round(picture.shape[1] * SPONSOR_PX / picture.shape[0]), SPONSOR_PX), interpolation=cv2.INTER_AREA)
        sponsor["logo"] = "data:image/png;base64," + base64.b64encode(cv2.imencode(".png", picture)[1]).decode()
    return data


def poster(video: Path, frame: int, path: Path) -> bool:
    """Writes `frame` as a POSTER_WIDTH pixels wide WebP; False when the video has no such frame."""
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
    ok, image = cap.read()
    cap.release()
    if ok:
        height, width = image.shape[:2]
        image = cv2.resize(image, (POSTER_WIDTH, round(height * POSTER_WIDTH / width)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(path), image, [cv2.IMWRITE_WEBP_QUALITY, 65])
    return ok


def touched(match: Path, given: dict[tuple[int, int], dict]) -> dict[int, tuple[int, int] | None]:
    """The touches the review's answers settle, by frame: the player's (team, identity), found by
    the name `given` them (it outlives the identities' numbers), else by number; None for no touch."""
    path = match / "identity_answers.json"
    answers = json.loads(path.read_text()).get("touch", []) if path.exists() else []
    by_name = {(team, g["name"]): (team, number) for (team, number), g in given.items() if g.get("name")}
    return {t["frame"]: None if t["identity"] is None else by_name.get((t["team"], t.get("name")), (t["team"], t["identity"])) for t in answers}


def no_rallies(match: Path) -> set[int]:
    """Start frames of the rally windows the review's answers say are no rally (no play)."""
    path = match / "identity_answers.json"
    return {r["start"] for r in (json.loads(path.read_text()).get("rally", []) if path.exists() else []) if not r["play"]}


def drop_rallies(windows: list[tuple[int, int]], rows: list[dict], scores: list[dict], actions: list[dict], gone: set[int], lead: int) -> tuple[list, list, list, list]:
    """The rally windows, rallies.csv's and points.csv's rows and actions.csv's but the windows
    starting at a frame of `gone` and their contacts (from `lead` frames before them), each later
    score of their set less the points they gave."""
    kept: tuple[list, list, list] = ([], [], [])
    current, lost = None, [0, 0]
    for window, row, point in zip(windows, rows, scores):
        if row.get("set") != current:
            current, lost = row.get("set"), [0, 0]
        if window[0] in gone:
            if point.get("winner"):
                lost[int(point["winner"]) - 1] += 1
            continue
        if point.get("score_1"):
            point = {**point, "score_1": str(int(point["score_1"]) - lost[0]), "score_2": str(int(point["score_2"]) - lost[1])}
        for part, value in zip(kept, (window, row, point)):
            part.append(value)
    out = [(a, b) for a, b in windows if a in gone]
    return *kept, [r for r in actions if not any(a - lead <= int(r["frame"]) <= b for a, b in out)]


def match_data(match: Path, video: Path, calibration: Calibration) -> tuple[dict, dict | None]:
    """data.js's match and players.js's player positions, None without player tracks."""
    cap = cv2.VideoCapture(str(video))
    fps, frame_count, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()
    rally_rows = read_csv(match / "rallies.csv")
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rally_rows]
    actions = read_csv(match / "actions.csv")
    gap = round(GAP_S * fps)
    teams = read_teams(match)
    with_teams = bool(teams) and (match / "tracks.csv").exists()
    identities = read_identities(match / "identities.csv") if with_teams and (match / "identities.csv").exists() else []
    given = named(identities, read_names(match))
    # The touches the review says are none (the ball out of sight, taken for a touch) go.
    said = touched(match, given)
    actions = [r for r in actions if said.get(int(r["frame"]), ()) is not None]
    scores = read_csv(match / "points.csv") if with_teams and (match / "points.csv").exists() else [{}] * len(windows)
    # And the windows it says are no rally (warm-up, a ball thrown back).
    windows, rally_rows, scores, actions = drop_rallies(windows, rally_rows, scores, actions, no_rallies(match), round(LEAD_S * fps))
    # The player rows around the touches place them; all the rows feed the samples, read once.
    near = {f for row in actions for f in range(int(row["frame"]) - gap, int(row["frame"]) + gap + 1)}
    track_team = {int(r["track"]): int(r["team"]) for r in read_csv(match / "tracks.csv")} if with_teams else {}
    teams = teams if with_teams else None
    who, table = people(track_team, identities, given)
    by_frame: dict[int, list[dict]] = {}

    def rows() -> Iterator[dict]:
        with open(match / "players.csv") as f:
            for row in csv.DictReader(f):
                frame = int(row["frame"])
                if frame in near:
                    by_frame.setdefault(frame, []).append(row)
                if not with_teams:
                    # Without teams, tracks are grouped by their side of the net: 1 left, 2 right.
                    track_team.setdefault(int(row["track"]), 1 if row["team"] == "left" else 2)
                yield row

    step = max(1, round(STEP_S * fps))
    samples = player_samples(rows(), step, frame_count, who) if (match / "players.csv").exists() else []
    found = contacts(actions, windows, by_frame, fps, calibration, UNDER_PX * height / 720, who, said)
    rallies = []
    for (start, end), row, point in zip(windows, rally_rows, scores):
        rallies.append({
            "start": round(start / fps, 2),
            "end": round(end / fps, 2),
            "set": int(row.get("set") or 1),
            "left": int(row["left"]) if row.get("left") else None,
            "winner": int(point["winner"]) if point.get("winner") else None,
            "score": [int(point["score_1"]), int(point["score_2"])] if point.get("score_1") else None,
        })
    for contact in found:
        contact["set"] = rallies[contact["rally"]]["set"]
    settle(found, [r["winner"] for r in rallies])
    data = {
        "name": video.stem,
        "video": video.name,
        "fps": round(fps, 3),
        "duration": round(frame_count / fps, 2),
        "teams": teams and [{"name": t["name"], "colour": hand_edited(parse_colour, t["colour"], "a colour (#rrggbb or a name such as white, rouge, navy)") if t["colour"] else t["jersey"]} for t in teams["teams"]],
        "date": teams and (hand_edited(parse_date, teams["date"], "a date (dd/mm/yyyy or yyyy-mm-dd)") if teams.get("date") else recording_date(video)),
        "title": teams and teams.get("title"),
        "rallies": rallies,
        "contacts": found,
        "zones": zone_cells(),
        "scores": teams and teams.get("scores"),
    }
    for p, seconds in playing_time(samples, step, windows, [r["set"] for r in rallies], fps).items():
        if p in table:
            table[p]["seconds"] = seconds
    data["people"] = table
    return data, {"step": step, "samples": samples} if any(samples) else None


def ball_track(match: Path, size: tuple[int, int], fps: float) -> dict:
    """ball.js's content: the ball's place where it is seen in the rallies (their lead included),
    every BALL_STEP_S, as flat [frame, x, y, ...] samples, x and y fractions of the picture."""
    lead, step = round(LEAD_S * fps), max(1, round(BALL_STEP_S * fps))
    windows = [(int(r["start_frame"]) - lead, int(r["end_frame"])) for r in read_csv(match / "rallies.csv")]
    samples: list[float] = []
    with open(match / "ball.csv") as f:
        for row in csv.DictReader(f):
            frame = int(row["frame"])
            if row["visible"] == "1" and frame % step == 0 and any(a <= frame <= b for a, b in windows):
                samples += [frame, round(float(row["x"]) / size[0], 3), round(float(row["y"]) / size[1], 3)]
    return {"fps": fps, "samples": samples}


def write_site(data: dict, players: dict | None, video: Path | None, site: Path, copy: bool, av1: Path | None = None, ball: dict | None = None) -> None:
    """The page, data.js, players.js and, unless `video` is None, the video, its `av1` copy the page
    plays first where the browser can, its poster, a frame from the middle of the first rally, and
    the `ball`'s places in ball.js, which the page loads to zoom on it."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(site / "assets", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    # A previous build's footage goes, whatever the case of its name: the page may now hold none.
    for old in site.iterdir():
        if old.name == "poster.webp" or old.suffix.lower() in VIDEOS:
            old.unlink()
    first = data["rallies"][0] if data["rallies"] else {"start": 0, "end": 0}
    data = {**data, "video": video and video.name}
    if video and av1:
        data["av1"] = av1.name
    if video and poster(video, round((first["start"] + first["end"]) / 2 * data["fps"]), site / "poster.webp"):
        data["poster"] = "poster.webp"
    (site / "players.js").unlink(missing_ok=True)
    players_js = players and f"window.MATCH_PLAYERS = {json.dumps(players, separators=(',', ':'))};\n"
    if players_js:
        (site / "players.js").write_text(players_js)
    (site / "ball.js").unlink(missing_ok=True)
    ball_js = video and ball and f"window.MATCH_BALL = {json.dumps(ball, separators=(',', ':'))};\n"
    if ball_js:
        (site / "ball.js").write_text(ball_js)
    # The unhashed scripts load with the build's hash in their URL: a host or CDN caching them by URL
    # serves each build its own.
    built = json.dumps(data, sort_keys=True) + (players_js or "") + (ball_js or "") + (site / "scene3d.js").read_text()
    data["v"] = hashlib.sha256(built.encode()).hexdigest()[:10]
    (site / "data.js").write_text(f"window.MATCH = {json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n")
    index = site / "index.html"
    index.write_text(index.read_text().replace('src="data.js"', f'src="data.js?v={data["v"]}"'))
    # Copied with their dates: an upload skips the unchanged ones.
    for kept in filter(None, (video, video and av1)):
        if copy:
            shutil.copy2(kept, site / kept.name)
        else:
            (site / kept.name).symlink_to(kept.resolve())


def cut(image: np.ndarray, x: float, top: int, bottom: int, wide: int) -> tuple[np.ndarray, tuple[int, int, float]]:
    """Rows `top` to `bottom` of `image`, `wide` wide centred on `x` (the frame's edges mirrored past
    them: the player stays in the middle), no taller than PHOTO_PX (never enlarged); and its left, top
    and scale."""
    left = round(x - wide / 2)
    height, width = image.shape[:2]
    part = image[max(0, top) : min(height, bottom), max(0, left) : min(width, left + wide)]
    if part.size:
        part = cv2.copyMakeBorder(part, max(0, -top), max(0, bottom - height), max(0, -left), max(0, left + wide - width), cv2.BORDER_REFLECT_101)
    scale = min(1.0, PHOTO_PX / max(1, part.shape[0]))
    if part.size and scale < 1:
        part = cv2.resize(part, (max(1, round(part.shape[1] * scale)), PHOTO_PX), interpolation=cv2.INTER_AREA)
    return part, (left, top, scale)


def packed(vectors: dict[str, np.ndarray]) -> bytes:
    """`vectors` as the bytes of an .npz: their names, then the vectors in float16."""
    import io

    out = io.BytesIO()
    np.savez(out, names=np.array(list(vectors)), vectors=np.array(list(vectors.values()), np.float16))
    return out.getvalue()


def framed(image: np.ndarray, box: tuple[int, int, int, int]) -> tuple[np.ndarray, tuple[int, int, float]]:
    """A player's whole picture from their `box`: a little room above and below them, widened to
    PHOTO_RATIO; and its left, top and scale (`cut`)."""
    from volleyball_stats.review import CROP_MARGIN

    x1, y1, x2, y2 = box
    my = round((y2 - y1) * CROP_MARGIN)
    return cut(image, (x1 + x2) / 2, y1 - my, y2 + my, max(x2 - x1, round((y2 - y1 + 2 * my) * PHOTO_RATIO)))


def upscaler() -> tuple | None:
    """The cards' pictures' upscaler (UPSCALER) and its device, downloaded the first time; None when
    it cannot be had (offline): the pictures stay as cut."""
    import urllib.request

    try:
        if not UPSCALER.exists():
            UPSCALER.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(UPSCALER_URL) as response:
                files.write_bytes(UPSCALER, response.read())
    except OSError:
        return None
    from spandrel import ModelLoader

    from volleyball_stats.ball import default_device

    device = default_device()
    return ModelLoader().load_from_file(UPSCALER).to(device).eval(), device


def upscaled(upscaler: tuple, picture: np.ndarray) -> np.ndarray:
    """`picture` 4 times larger from `upscaler` (model, device), no taller than PHOTO_PX, touched up
    without sharpening; a small one blended with its plain enlargement, from none of the upscaler's
    at SMEARS px tall to all of it at CLEAN (it smears a face of a few pixels)."""
    import torch

    model, device = upscaler
    x = torch.from_numpy(cv2.cvtColor(picture, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(device)
    with torch.no_grad():
        big = cv2.cvtColor(model(x)[0].clamp(0, 1).mul(255).permute(1, 2, 0).byte().cpu().numpy(), cv2.COLOR_RGB2BGR)
    tall = min(big.shape[0], PHOTO_PX)
    size = (max(1, round(big.shape[1] * tall / big.shape[0])), tall)
    share = float(np.clip((picture.shape[0] - SMEARS) / (CLEAN - SMEARS), 0, 1))
    plain = cv2.resize(picture, size, interpolation=cv2.INTER_CUBIC)
    return touched_up(cv2.addWeighted(cv2.resize(big, size, interpolation=cv2.INTER_AREA), share, plain, 1 - share, 0), sharpen=0.0)


def touched_up(picture: np.ndarray, sharpen: float = SHARPEN) -> np.ndarray:
    """`picture` with WARMTH of its colour cast off, CONTRAST and `sharpen`."""
    means = picture.reshape(-1, 3).mean(0)
    out = np.clip(picture * (1 + WARMTH * (means.mean() / np.maximum(means, 1) - 1)), 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=CONTRAST, tileGridSize=(4, 4)).apply(lab[..., 0])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return cv2.addWeighted(out, 1 + sharpen, cv2.GaussianBlur(out, (0, 0), 1.0), -sharpen, 0)


def bust(box: tuple) -> tuple[int, int]:
    """The rows of a player's picture from their `box`: HEADROOM above the head down BUST of it."""
    span = BUST * (box[3] - box[1])
    return round(box[1] - HEADROOM * span), round(box[1] + span)


def face(image: np.ndarray, box: tuple, head: list[float] | None) -> np.ndarray:
    """A player's picture (`bust`), centred on their shoulders' middle (`head`: the nose's y, the
    shoulders' middle x and y), else on their box."""
    top, bottom = bust(box)
    return cut(image, head[1] if head else (box[0] + box[2]) / 2, top, bottom, round((bottom - top) * PHOTO_RATIO))[0]


def looks(pictures: list[tuple[np.ndarray, tuple]]) -> list[tuple[float, float, float, int, list | None, list]]:
    """(facing, whole, sharp, others, head) of each (picture, player's box in it), of the person the pose
    model finds best matching the box (0 for none): how much they face the camera (their eyes and
    nose seen, the nose midway between the eyes: off to a side in profile), its mean confidence in all
    the keypoints; the variance of the Laplacian (of the `bust`); the other people found as large as OTHER of the box; the
    nose's y and the shoulders' middle x and y, None unless all three are seen (KEYPOINT); the mean
    Lab colour of their top (the box's rows from a fifth to under half its height, its middle half)."""
    from ultralytics import YOLO

    from volleyball_stats.actions import POSE_MODEL

    model, out = YOLO(str(POSE_MODEL)), []
    for (picture, box), found in zip(pictures, model.predict([p for p, _ in pictures], imgsz=384, verbose=False, stream=True)):
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        x1, y1, x2, y2 = box
        h, w = y2 - y1, x2 - x1
        shirt = picture[max(0, y1 + h // 5) : y1 + 9 * h // 20, max(0, x1 + w // 4) : x2 - w // 4]
        kit = cv2.cvtColor(shirt, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(0).tolist() if shirt.size else [0.0, 0.0, 0.0]
        boxes, confidence = found.boxes.xyxy.cpu().numpy(), found.keypoints.conf
        if not len(boxes) or confidence is None:
            out.append((0.0, 0.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()), 0, None, kit))
            continue
        inter = np.clip(np.minimum(boxes[:, 2], x2) - np.maximum(boxes[:, 0], x1), 0, None) * np.clip(np.minimum(boxes[:, 3], y2) - np.maximum(boxes[:, 1], y1), 0, None)
        union = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]) + (x2 - x1) * (y2 - y1) - inter
        best = int(np.argmax(inter / np.maximum(union, 1)))
        seen = confidence.cpu().numpy()[best]
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        others = int((areas >= OTHER * (x2 - x1) * (y2 - y1)).sum()) - 1
        # COCO keypoints: 0 the nose, 5 and 6 the shoulders.
        points = found.keypoints.xy.cpu().numpy()[best]
        head = [float(points[0, 1]), float(points[5:7, 0].mean()), float(points[5:7, 1].mean())] if min(seen[0], seen[5], seen[6]) >= KEYPOINT and points[5:7, 1].mean() > points[0, 1] else None
        # Sharpness where the picture will be.
        top, bottom = bust(box)
        gray = gray[max(0, top) : bottom]
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0
        # COCO keypoints 1 and 2: the eyes.
        spread = abs(points[1, 0] - points[2, 0])
        middle = 1 - 2 * abs(points[0, 0] - (points[1, 0] + points[2, 0]) / 2) / spread if spread > 1 else 0.0
        facing = float(min(seen[0], seen[1], seen[2]) * max(0.0, middle))
        out.append((facing, float(seen.mean()), sharp, max(0, others), head, kit))
    return out


def photos(match: Path, video: Path, people: dict[int, dict], folder: Path, teams: set[int] = {1, 2}) -> dict[int, tuple]:
    """A picture of each numbered player of `teams` among `people` in `folder`, as their `photo`: their
    best moment (PHOTO_PICKS), framed; returns each pictured player's (frame, box, head)."""
    from volleyball_stats.identity import frames_at
    from volleyball_stats.review import ALONE, IDENTITY_CROPS, Questions, load_log, piece_key

    if not teams or not (match / "identity_candidates.json").exists():
        return {}
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    questions = Questions(match, fps)
    width, height = decode.size(video)
    marked = {piece_key(o) for e in load_log(match / "identity_answers.json") for o in e.get("odd", [])}

    def room(box: tuple) -> bool:
        x1, y1, x2, y2 = box
        side = ROOM * (y2 - y1)
        return (x1 + x2) / 2 - side >= 0 and (x1 + x2) / 2 + side <= width and y1 > 0 and y2 < height - 1

    with open(match / "rallies.csv") as f:
        rallies = [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]
    margin = IN_PLAY_S * fps

    def in_play(frame: int) -> bool:
        return any(start - margin <= frame <= end + margin for start, end in rallies)

    moments: dict[int, list[tuple[int, tuple]]] = {}
    spare: dict[int, list[tuple[int, tuple]]] = {}
    kits: dict[int, list[tuple[int, tuple]]] = {}
    confirmed: dict[int, list[tuple[int, tuple]]] = {}
    for key, person in people.items():
        if person["number"] and person["team"] in teams:
            team, number = person["team"], person["number"]
            pieces = questions.pieces(team, number)[:IDENTITY_CROPS]
            kept = [((track, start, end), p) for (track, start, end, _, _), p in zip(pieces, questions.faces(team, number)["pieces"]) if piece_key(p) not in marked and track in questions.rows]
            shown = [piece for piece, _ in kept]
            confirmed[key] = [(p["frame"], questions.box(p["track"], p["frame"])) for _, p in kept]
            found, playing_in = [], []
            for track, start, end in shown:
                rows = questions.track_rows(track, start, end)
                found += [
                    (int(questions.frame_of[r]), tuple(int(v) for v in questions.box_of[r]))
                    for r in rows[:: max(1, len(rows) // PHOTO_SAMPLES)]
                    if questions.covered(r) < ALONE and abs(questions.court_of[r][0]) <= LENGTH / 2 + ON_COURT and abs(questions.court_of[r][1]) <= WIDTH / 2 + ON_COURT
                ]
                # Inside the court's lines: playing, not waiting at its edge.
                playing_in += [
                    (int(questions.frame_of[r]), tuple(int(v) for v in questions.box_of[r]))
                    for r in rows[:: max(1, len(rows) // PHOTO_SAMPLES)]
                    if in_play(int(questions.frame_of[r])) and abs(questions.court_of[r][0]) <= LENGTH / 2 and abs(questions.court_of[r][1]) <= WIDTH / 2
                ]
            fitting = sorted((m for m in found if room(m[1])), key=lambda m: m[1][1] - m[1][3])
            if fitting or found:
                moments[key] = fitting[:PHOTO_PICKS] or sorted(found, key=lambda m: m[1][1] - m[1][3])[:1]
                spare[key] = fitting[PHOTO_PICKS : PHOTO_PICKS + PHOTO_MORE]
                kits[key] = sorted(playing_in, key=lambda m: m[1][1] - m[1][3])[:KIT_SAMPLES] or moments[key][:KIT_SAMPLES]
    path = match / PHOTO_SCORES
    scores = json.loads(path.read_text()) if path.exists() else {}
    name = lambda frame, box: f"{frame}:{','.join(map(str, box))}"  # noqa: E731

    vectors_path = match / PHOTO_VECTORS
    vectors: dict[str, np.ndarray] = {}
    if vectors_path.exists():
        with np.load(vectors_path) as found:
            vectors = dict(zip(found["names"].tolist(), found["vectors"].astype(np.float32)))
    reid: list = []

    def scored(moments: dict[int, list]) -> None:
        """`scores` holding every one of `moments` (`looks`) and `vectors` their appearance (the
        re-identification embedding of their box), read from the video where missing."""
        wanted: dict[int, list[tuple]] = {}
        for f, b in {m for found in moments.values() for m in found if len(scores.get(name(*m), ())) != 6 or name(*m) not in vectors}:
            wanted.setdefault(f, []).append(b)
        pictures: dict[str, tuple] = {}
        boxes: dict[str, np.ndarray] = {}
        for frame, image in frames_at(video, wanted):
            for box in wanted[frame]:
                part, (left, top, scale) = framed(image, box)
                pictures[name(frame, box)] = (part, tuple(round((v - o) * scale) for v, o in zip(box, (left, top, left, top))), (left, top, scale))
                x1, y1, x2, y2 = box
                boxes[name(frame, box)] = image[max(0, y1) : y2, max(0, x1) : x2]
        if boxes:
            if not reid:
                from volleyball_stats.ball import default_device
                from volleyball_stats.identity import describe, load_reid

                device = default_device()
                reid.extend([load_reid(device), device, describe])
            model, device, describe = reid
            vectors.update(zip(boxes, describe(list(boxes.values()), model, device)))
            files.write_bytes(vectors_path, packed(vectors))
        if pictures:
            for key, (facing, whole, sharp, others, head, kit) in zip(pictures, looks([(p, b) for p, b, _ in pictures.values()])):
                left, top, scale = pictures[key][2]
                # The head back in the frame's pixels.
                scores[key] = [facing, whole, sharp, others, head and [top + head[0] / scale, left + head[1] / scale, top + head[2] / scale], kit]
            files.write_text(path, json.dumps(scores))

    scored(moments)
    scored(kits)
    scored(confirmed)
    # Players facing the camera in none of their closest moments: their farther ones too.
    turned = {key: spare[key] for key, found in moments.items() if spare.get(key) and max(scores[name(*m)][0] for m in found) <= FACED}
    scored(turned)
    for key, more in turned.items():
        moments[key] = moments[key] + more
    # In their kit: a top like the one they play in, their moments in play among the candidates (all
    # the closest may be in a hoodie); and looking like the pictures the user confirmed (a piece's
    # track may switch to someone else).
    for key, found in moments.items():
        kit = np.median([scores[name(*m)][5] for m in kits[key]], axis=0)
        found = list(dict.fromkeys(found + [m for m in kits[key] if room(m[1])]))
        found = [m for m in found if np.linalg.norm(np.subtract(scores[name(*m)][5], kit)) <= KIT] or found
        seen = np.array([vectors[name(*m)] for m in confirmed[key]])
        likeness = {m: float(np.median(seen @ vectors[name(*m)])) for m in found}
        moments[key] = [m for m in found if likeness[m] >= max(likeness.values()) - LIKE]
    # The moments the user picked, by the player's name.
    path = match / PHOTO_PICKED
    taken = json.loads(path.read_text()) if path.exists() else {}
    own = {key: (taken[n]["frame"], tuple(taken[n]["box"])) for key in moments if (n := people[key].get("name")) in taken}
    scored({key: [m] for key, m in own.items()})
    chosen: dict[int, list] = {}
    picked: dict[int, tuple] = {}
    offered: dict[str, list] = {}
    for key, found in moments.items():
        top = [max(scores[name(f, b)][2] for f, b in found), max(b[3] - b[1] for _, b in found)]

        def score(moment: tuple[int, tuple]) -> float:
            facing, whole, sharp, others, _, _ = scores[name(*moment)]
            return FACING * facing + whole + SHARP * sharp / max(top[0], 1e-9) + SIZE * (moment[1][3] - moment[1][1]) / max(top[1], 1) - CROWD * others

        ranked = sorted(found, key=score, reverse=True)
        frame, box = own.get(key, ranked[0])
        offered[f"{people[key]['team']}:{people[key]['number']}"] = [{"frame": f, "box": list(b)} for f, b in dict.fromkeys([(frame, box), *ranked[: PHOTO_CHOICES - 1]])]
        chosen.setdefault(frame, []).append((key, box))
        picked[key] = (frame, box, scores[name(frame, box)][4])
    files.write_text(match / PHOTO_CANDIDATES, json.dumps(offered))
    folder.mkdir(parents=True, exist_ok=True)
    up = upscaler() if chosen else None
    for frame, image in frames_at(video, chosen):
        for key, box in chosen[frame]:
            part = face(image, box, scores[name(frame, box)][4])
            if part.size:
                cv2.imwrite(str(folder / f"{key}.webp"), upscaled(up, part) if up else touched_up(part), [cv2.IMWRITE_WEBP_QUALITY, 80])
                people[key]["photo"] = f"{folder.name}/{key}.webp"
    return picked


def footage_video(match: Path, video: Path, blurred: set[int]) -> Path:
    """The video to publish: `video` itself, or its copy with the `blurred` teams' players blurred,
    made again when the player tracks are newer."""
    if not blurred:
        return video
    from volleyball_stats import blur

    out = match / f"{video.stem}_blurred_{''.join(map(str, sorted(blurred)))}.mp4"
    tracks = max((match / name).stat().st_mtime for name in ("players.csv", "tracks.csv"))
    if not out.exists() or out.stat().st_mtime < tracks:
        blur.write(match, video, blurred, out)
    return out


def build(
    match: Path,
    video: Path,
    court: Path,
    site: Path,
    copy: bool = False,
    theme: str = "aspom",
    footage: str = "none",
    club: int | str | None = None,
    pictured: set[int] = frozenset(),
    light: Path | None = None,
    link: str | None = None,
    feedback: str | None = None,
    av1: Path | None = None,
) -> dict:
    """The match page in `site` with the `footage` FOOTAGE says (`club` the user's team) and the
    pictures of the `pictured` teams' players; `light` a lighter copy of `video` on its timeline for
    the page to play with the full footage, `av1` an AV1 copy played first where the browser can, and `link`, on a page without footage, where the same
    page with it is (behind a password); `feedback` where viewers report what is wrong in a moment
    (none: they are not asked); returns data.js's match. ValueError for `light` or `av1` with a
    footage to blur (blurring works on the tracked video)."""
    if (light or av1) and footage != "full":
        raise ValueError("--light-video and --av1-video go with --footage full")
    calibration = Calibration.load(court)
    calibration.check(decode.size(video))
    data, players = match_data(match, video, calibration)
    blurred = {3 - (club or 1)} if footage == "blur-opponents" else {"none": None, "full": set(), "blur-all": {1, 2}}[footage]
    shutil.rmtree(site / "players", ignore_errors=True)
    photos(match, video, data["people"], site / "players", pictured)
    shutil.rmtree(site / "brand", ignore_errors=True)
    data["brand"] = brand(theme, site)
    data["videoPage"] = link if blurred is None else None
    data["feedback"] = feedback
    ball = ball_track(match, decode.size(video), data["fps"]) if blurred is not None and (match / "ball.csv").exists() else None
    write_site(data, players, None if blurred is None else light or footage_video(match, video, blurred), site, copy, av1, ball)
    return data


def publish(match: Path, video: Path, court: Path, theme: str, given: dict, site: Path | None = None) -> tuple[dict, dict]:
    """The page to publish, MATCH/site/ built with page.json's choices, those `given` (not None)
    replacing theirs and saved back, or `site` (to host) with only those `given`: no footage nor
    pictures unless asked; returns data.js's match and the choices. ValueError for a choice needing a
    club without one, or a court calibrated on another video."""
    path = match / "page.json"
    saved = json.loads(path.read_text()) if path.exists() and site is None else {}
    settings = {"footage": "none", "club": None, "pictures": False, "copy": False, "light": None, "av1": None, "link": None, "feedback": None, **saved}
    settings.update({k: v for k, v in given.items() if v is not None})
    if settings["club"] is None and (settings["footage"] == "blur-opponents" or settings["pictures"]):
        raise ValueError("--footage blur-opponents and --pictures need --club 1, 2 or both")
    if settings["club"] == "both" and settings["footage"] == "blur-opponents":
        raise ValueError("--club both leaves no opponents to blur")
    if site is None:
        path.write_text(json.dumps(settings, indent=2) + "\n")
    pictured = ({1, 2} if settings["club"] == "both" else {settings["club"]}) if settings["pictures"] else set()
    light = Path(settings["light"]) if settings["light"] else None
    av1 = Path(settings["av1"]) if settings["av1"] else None
    data = build(match, video, court, site or match / "site", settings["copy"], theme, settings["footage"], settings["club"], pictured, light=light, link=settings["link"], feedback=settings["feedback"], av1=av1)
    return data, settings


def main() -> None:
    themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
    parser = argparse.ArgumentParser(description="Build the static match page from the pipeline's outputs.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--out", type=Path, help="Site directory (default: MATCH/site)")
    parser.add_argument("--footage", choices=FOOTAGE, help="What the page shows of the video (default: the previous build's, none with --out: the court's top view replays the moments)")
    parser.add_argument("--club", type=lambda v: v if v == "both" else int(v), choices=(1, 2, "both"), help="Your team, 1 or 2 (team 1 is on the left at the first rally), or both (two teams of your club)")
    parser.add_argument("--pictures", action=argparse.BooleanOptionalAction, help="Your team's players' pictures on their cards (needs --club)")
    parser.add_argument("--copy-video", action=argparse.BooleanOptionalAction, help="Copy the video instead of symlinking it, for hosting")
    parser.add_argument("--light-video", type=Path, help="A lighter copy of --video on its timeline (e.g. 1080p) for the page to play with --footage full; the data still come from --video")
    parser.add_argument("--av1-video", type=Path, help="An AV1 copy of --video on its timeline, 1080p 8-bit (level 4.0), that the page plays first where the browser can; the others play --light-video or --video")
    parser.add_argument("--feedback", help="Where viewers report what is wrong in a moment (e.g. /volleyball/feedback, the hosting's nginx keeps them); none asks nothing")
    parser.add_argument("--video-page", help="On a page without the video, a link to the same page with it, behind a password (e.g. video/)")
    parser.add_argument("--theme", default="aspom", help=f"Club theme from branding/NAME/brand.json: {', '.join(themes + ['none'])} (default: aspom)")
    args = parser.parse_args()
    try:
        data, settings = publish(args.match, args.video, args.court, args.theme, {"footage": args.footage, "club": args.club, "pictures": args.pictures, "copy": args.copy_video, "light": args.light_video and str(args.light_video), "av1": args.av1_video and str(args.av1_video), "link": args.video_page, "feedback": args.feedback}, args.out)
    except ValueError as error:
        parser.error(str(error))
    site = args.out or args.match / "site"
    sizes = ", ".join(f"{name} {(site / name).stat().st_size / 1e3:.0f} KB" for name in ("data.js", "players.js") if (site / name).exists())
    shown = {"none": "no video", "full": "video", "blur-opponents": "video, opponents blurred", "blur-all": "video, both teams blurred"}[settings["footage"]]
    print(f"{len(data['contacts'])} contacts, {len(data['rallies'])} rallies, {sizes}, {shown}{', pictures' if settings['pictures'] else ''} -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
