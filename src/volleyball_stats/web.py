"""The match page: a static site built from the pipeline's outputs, index.html + data.js + the video.

    uv run python -m volleyball_stats.web outputs/matches/VIDEO --video VIDEO --court COURT_JSON [--club N] [--footage MODE] [--pictures] [--out DIR] [--copy-video] [--theme NAME]

The page (site/, built from web/ with `npm run build` and copied as is) reads the match from data.js,
a script rather than fetched JSON so it opens from the disk by double-clicking index.html, and the
players' positions from a file per 5 minutes (positions/N.js), which it loads as the replay reaches them. Every
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
theme from branding/NAME/brand.json (logo, colours), `none` for the neutral one; by default the app's club.
"""

import argparse
import base64
from copy import deepcopy
import csv
import hashlib
import json
import os
import shutil
import struct
from collections.abc import Callable, Iterable, Iterator
from typing import BinaryIO
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import club_settings, decode, defense, files, framing, icon, jobs, jumps, likeness, tables, timeline, timeouts, video_copies
from volleyball_stats.ball3d import LOWEST_NET_M, court_off, fit_touches, measure, touch_places
from volleyball_stats.speech import voice_index
from volleyball_stats.actions import LEAD_S, UNDER_PX, player_under
from volleyball_stats.attribution import GAP_S, NO_PLAYER, box_at
from volleyball_stats.court import LENGTH, WIDTH, Calibration, zone
from volleyball_stats.identity import finder, leftovers, named, on_court, read_identities, read_names
from volleyball_stats.points import landing
from volleyball_stats.teams import match_end, parse_colour, parse_date, recording_date

TEMPLATE = Path(__file__).with_name("site")
# The shape of data.js the page's code reads: raised when a field goes or changes its type (`web/src/lib/dataFormat.test.ts` fails until it is), a
# page online built with another then keeps the code it was built with (`matches.share_code`); a new field needs none,
# the page reading it with a fallback. A page without it: 1.
FORMAT = 1
# What is drawn on the video, beside the page: the ball's places and the automatic zoom's camera.
VIDEO_JS = "video.js"
# The club, edited in the app (club_settings.py): the default theme.
CLUB = "club"
# Player positions are kept every STEP_S seconds over the whole video, to the centimetre.
STEP_S = 0.1
# A player is on the court with their feet within SERVE_M behind an end line (serving) and SIDE_M
# outside a sideline; the bench stands farther.
SERVE_M, SIDE_M = 3.0, 1.0
# The ball's place in the picture during the rallies, every BALL_STEP_S, for the video's zoom on it and its trail; a
# frame in between too where a straight line between those two would miss the ball by BALL_CORNER of the picture's
# width: a touch's corner (about half the ball; 0.003 to 0.006 add 15% to 7% of samples on the Avia match).
BALL_STEP_S = 0.08
BALL_CORNER = 0.004
POSTER_WIDTH = 800
# What the page shows of the video: nothing, all of it, or the video with some players blurred.
FOOTAGE = ("none", "full", "blur-opponents", "blur-all")
# Video files a previous build may have left in the site folder, by lowercase extension.
VIDEOS = (".mp4", ".mov", ".m4v")
# The club logo shows at most 64 px tall, the players' pictures about 240 px: kept at twice that for
# sharp high-density screens, never enlarged. The pictures are 3 wide for 4 tall, like a photo.
LOGO_PX, PHOTO_PX, PHOTO_RATIO = 128, 480, 0.75
LOGO_QUALITY = 90
# The seconds of players' positions in one file the page loads, and how long a player missing from a few samples
# stays where they were last seen (the page's `playersAt`).
POSITIONS_S, HOLD_S = 300, 0.5
# How the page's players move (`natural_motion`, `benchmarks/players/motion.py`): over OUTLIER_M from the median of OUTLIER_S
# either side is noise, a hole up to FILL_S at under FILL_M_S is filled while the team has under TEAM_ON_COURT, then a Gaussian of SMOOTH_S.
OUTLIER_M, OUTLIER_S, FILL_S, FILL_M_S, SMOOTH_S, TEAM_ON_COURT = 0.5, 0.5, 5.0, 7.0, 0.2, 6
# How finely the page's files place a player, fine enough for a walk to stay even between samples (`docs/history.md`).
POSITION_CM = 2
# The touches that lose a serve, an attack or a block coming at them: not a serve, nor an attack of their own; nor the
# ball they let fall (`missed`).
LOSING_TOUCHES = ("pass", "set", "relance", "block", "dig", "missed")
# What the review adds without a touch of the ball, a fault of its player each: a playing fault (net, centre line,
# rotation) and a ball they should have played, untouched (`missed`).
NO_BALL = ("fault", "missed")
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
# Where the review's card pictures were taken, by file (players/KEY.webp): the track and frame, for an
# apply to keep each picture on the player it shows until the new ones come (`kept_photos`).
PHOTO_SHOWN = "photo_shown.json"
# Raise it when what `photos` keeps of a moment's scores changes.
SCORES_FORMAT = 1
# The moments framed so far, by frame and box.
PHOTO_KEPT = "photo_moments"
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


def result(contact: dict, after: dict | None, played: bool = False) -> str:
    """Outcome of a contact from the next one of its rally, the landing judged as the score's
    (`points.landing`): "point" when that is the ball landing in the court on the other side of the
    net, or at the foot of the net after a block (the attacker sent it there); "error" when it lands
    on the contact's side, out, at the foot of the net or in the net; "play" otherwise, for the
    floor and net contacts themselves, and when a touch is `played` after that landing in the rally:
    no landing then (a serve brushing the net on its way over, a floor taken for a low touch)."""
    if contact["type"] in ("floor", "net") or after is None or after["type"] not in ("floor", "net") or played:
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
    identity the review `said` touched it (by frame). A contact with a track is placed at that
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
            xy = xy or (spot(kind, (float(row["x"]), float(row["y"])), boxes, feet, calibration, reach) if row["x"] != "" else None)
        out.append({
            "t": round(frame / fps, 2),
            # The exact frame: the answers name touches by it, which `t` may miss by one.
            "f": frame,
            "type": kind,
            "side": row["side"],
            "team": int(row["team"]) if row.get("team") else None,
            "rally": rally,
            "x": None if xy is None else round(xy[0], 2),
            "y": None if xy is None else round(xy[1], 2),
            "zone": None if xy is None else zone(*xy),
            "person": who(track, frame, (said or {}).get(frame)),
        })
    for k, contact in enumerate(out):
        rest = [c for c in out[k + 1 :] if c["rally"] == contact["rally"]]
        contact["result"] = result(contact, rest[0] if rest else None, any(c["type"] not in ("floor", "net") for c in rest[1:]))
    return out


def ended(windows: list[tuple[int, int]], ends: list[dict]) -> list[tuple[int, int]]:
    """`windows` ending where the review said (`ends`: their start and end frames)."""
    by_start = {e["start"]: e["end"] for e in ends}
    return [(start, by_start.get(start, end)) for start, end in windows]


def crossed(row: dict, said: tuple[int, int] | None) -> dict:
    """An actions CSV row the review gave a player of the other team (`said`): theirs, on the other
    side, without its track (one of the other team)."""
    if said is None or not row.get("team") or int(row["team"]) == said[0]:
        return row
    return {**row, "team": str(said[0]), "side": "right" if row["side"] == "left" else "left", "track": "", "identity": ""}


# How far from an added touch the ball's place is looked for.
ADDED_NEAR_S = 1.0
# How far from an added touch a contact the pipeline found is that touch: one of the same team, a
# floor or net contact (a touch near the floor). An attack and its block, 0.2 s apart, are two teams'.
ADDED_SAME_S, ADDED_FLOOR_S = 0.4, 0.2


def said_on(match: Path, kind: str, field: str) -> set[int]:
    """The rallies, by key, whose last answer of `kind` says `field`."""
    return {start for start, said in {a["start"]: a[field] for a in answers(match, kind)}.items() if said}


def said_players(match: Path) -> dict[int, str | int]:
    """The player the review's last `touch` answer named on each touch, by frame: their name, which
    a rerun keeps, else their identity; none for a touch it said is no touch."""
    last = {a["frame"]: a for a in answers(match, "touch")}
    return {frame: a.get("name") or a["identity"] for frame, a in last.items() if a["identity"] is not None}


def said_types(match: Path) -> dict[int, str]:
    """The type the review's last `action` answer giving one gave each touch, by frame."""
    return {a["frame"]: a["type"] for a in answers(match, "action") if "type" in a}


def said_teams(match: Path) -> dict[int, int]:
    """The team the review's last `touch` answer on each touch gave it, by frame."""
    return {a["frame"]: a["team"] for a in answers(match, "touch")}


def with_added(
    windows: list[tuple[int, int]], rows: list[dict], typed: list[dict], added: list[dict], ball: Path, near: int, same: int = 0, floor: int = 0, lead: int = 0, said: dict[int, int] | None = None, kinds: dict[int, str] | None = None, named: dict[int, str | int] | None = None
) -> tuple[list[tuple[int, int]], list[dict]]:
    """The rally windows and actions CSV rows `typed` with the touches the review added (`added`
    answers: the window's start, frame, team, type): a row each, at the ball's place seen nearest it
    under `near` frames (none when unseen), on its team's side of the rally (rallies.csv's `rows`);
    a window ending before a touch added to it lasts to it, one starting after it (a serve the rally
    missed) starts at it. One in a window gone or at a frame already found is left out; a row found
    within `same` frames of one, of its team, or within `floor` frames, a floor or net, is that touch
    found again (a rerun) and goes, the added touch taking its window (started `lead` frames early):
    a rerun moves the windows the answers named. A touch's team and type are those the review gave it
    (`said`, `kinds`, by frame), else its own. A playing fault or a ball let fall is no touch of the ball: none goes for it.
    A block and another touch are two: the same player may play the ball again right after their block.
    So are two touches the review names (`named`, by frame) different players of: a double block."""
    starts = {start: k for k, (start, _) in enumerate(windows)}
    known = {int(r["frame"]) for r in typed}
    # A touch added twice: the last answer's.
    added = list({a["frame"]: a for a in added}.values())
    # A row at a frame the review gave is that touch: an older answer near it does not take it.
    given = {a["frame"] for a in added}
    added = [a for a in added if a["start"] in starts and a["frame"] not in known]
    if not added:
        return windows, typed

    def same_touch(r: dict, a: dict) -> bool:
        apart = abs(int(r["frame"]) - a["frame"])
        if a["type"] in NO_BALL or int(r["frame"]) in given:
            return False
        if r["type"] in NO_PLAYER:
            return apart <= floor
        one, other = (named or {}).get(int(r["frame"])), (named or {}).get(a["frame"])
        if one is not None and other is not None and one != other:
            return False
        kind_of = (kinds or {}).get
        if (kind_of(int(r["frame"]), r["type"]) == "block") != (kind_of(a["frame"], a["type"]) == "block"):
            return False
        return str((said or {}).get(int(r["frame"]), r.get("team"))) == str(a["team"]) and apart <= same

    # Each added touch's window: the one its answer named when it opens it (in its lead) or holds the
    # row it replaces, else that of this row, else the one named.
    window = {}
    for a in added:
        named_window = starts[a["start"]]
        found = [int(r["frame"]) for r in typed if same_touch(r, a)]
        holding = [k for k, (start, end) in enumerate(windows) for f in found if start - lead <= f <= end]
        opens = a["start"] - lead <= a["frame"] < a["start"]
        window[a["frame"]] = holding[0] if holding and not opens and named_window not in holding else named_window
    typed = [r for r in typed if not any(same_touch(r, a) for a in added)]
    windows = list(windows)
    places = ball_near(ball, [a["frame"] for a in added], near)
    new = []
    for a in added:
        k = window[a["frame"]]
        windows[k] = (min(windows[k][0], a["frame"]), max(windows[k][1], a["frame"]))
        left = rows[k].get("left") or 1
        x, y = places.get(a["frame"], ("", ""))
        new.append({"frame": str(a["frame"]), "x": x, "y": y, "type": a["type"], "side": "left" if int(left) == a["team"] else "right", "track": "", "gap": "", "team": str(a["team"]), "identity": ""})
    return windows, sorted(typed + new, key=lambda r: int(r["frame"]))


def ball_near(path: Path, frames: list[int], near: int) -> dict[int, tuple[str, str]]:
    """The ball's place (x, y as in ball.csv) seen nearest each of `frames`, under `near` frames from it."""
    # A ball frame near two touches counts for both.
    wanted: dict[int, list[int]] = {}
    for f in frames:
        for d in range(-near, near + 1):
            wanted.setdefault(f + d, []).append(f)
    best: dict[int, tuple[int, str, str]] = {}
    if path.exists() and wanted:
        for frame, (x, y) in tables.seen(path, lambda at: np.isin(at, np.fromiter(wanted, np.int64, len(wanted)))).items():
            for want in wanted[frame]:
                if want not in best or abs(frame - want) < best[want][0]:
                    best[want] = (abs(frame - want), tables.text(x), tables.text(y))
    return {f: (x, y) for f, (_, x, y) in best.items()}


def receivers(found: list[dict], typed: list[dict], players: dict[int, list[dict]], who: Who = lambda track, *_: track, said: dict[int, tuple[int, int] | None] | None = None) -> None:
    """Each ace of `found` (the page's contacts, from actions CSV rows `typed`) gets the player who
    missed it (`receiver`): the identity the review `said` (by the serve's frame), None when it said
    no one; else the nearest to where it lands in its rally on the other side; unknown (no key)
    without such a landing or a player there, or when a reception touched it. A player said of the serve's own team means no serve:
    a window starting late took their touch for one; it becomes their missed reception. One the review says a player let
    fall (`missed`) is theirs: no receiver to add."""
    said = said or {}
    let_fall = {c["rally"] for c in found if c["type"] == "missed"}
    for k, (contact, after) in enumerate(zip(found, found[1:] + [None])):
        if contact["type"] != "serve" or contact["result"] != "point" or contact["rally"] in let_fall:
            continue
        frame = int(typed[k]["frame"])
        if frame in said and said[frame] is not None and said[frame][0] == contact["team"]:
            contact.update(type="pass", result="error", person=who(None, frame, said[frame]))
        elif frame in said:
            contact["receiver"] = None if said[frame] is None else who(None, frame, said[frame])
        # A reception touched and missed is a fault of its own: no receiver to add.
        elif after and after["rally"] == contact["rally"] and after["side"] != contact["side"] and after["type"] in ("floor", "net"):
            at = int(typed[k + 1]["frame"])
            found_by = receiver(after, players.get(at, []), lambda track: who(track, at))
            if found_by is not None:
                contact["receiver"] = found_by


def partnered(found: list[dict], typed: list[dict], said: dict[int, tuple[int, int] | None], who: Who) -> None:
    """The faults of `found` (from actions CSV rows `typed`) the review shares with a second player (`said`, the identity by
    the fault's frame, None for no one): `partner`, that player's key. The statistics count the fault for both, once for the
    team (the owner's rule, 18 Nov)."""
    for contact, row in zip(found, typed):
        frame = int(row["frame"])
        if said.get(frame) is not None and contact["result"] == "error" and contact["type"] not in NO_PLAYER:
            partner = who(None, frame, said[frame])
            if partner != contact.get("person"):
                contact["partner"] = partner


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


def player_samples(t: dict[str, np.ndarray], step: int, frame_count: int, who: Who = lambda track, _: track) -> list[list[float]]:
    """The players' court feet every `step` frames of the video, from frame 0, each sample a flat
    [player, x, y, ...] list rounded to the centimetre, `who` naming the player of a track at a frame (`t`: players.csv's
    columns, `tables`)."""
    samples: list[list[float]] = [[] for _ in range(-(-frame_count // step))]
    kept = (t["frame"] % step == 0) & (t["frame"] // step < len(samples))
    for frame, track, x, y in zip(*(t[k][kept].tolist() for k in ("frame", "track", "court_x", "court_y"))):
        samples[frame // step] += [who(track, frame), round(x, 2), round(y, 2)]
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


# A player on the court under BRIEF_S of rally time in a set is a tracking slip there (first ASPOM
# match: 0.1-13 s, against 85 s for the shortest substitution).
BRIEF_S = 30.0


def brief(found: list[dict], typed: list[dict], table: dict[int, dict], times: dict[int, dict[str, float]], said: dict, missed: dict) -> None:
    """The touches and missed aces of `found` (the page's contacts, from actions CSV rows `typed`)
    that a numbered player of `table` on the court under BRIEF_S of their set (`times`) took are
    nobody's known, marked `brief` for the review to ask, unless the review `said` the touch's player
    (by frame) or the ace's receiver (`missed`). Nothing without players' times."""
    if not times:
        return
    slip = lambda p, number: p is not None and table[p]["number"] is not None and times.get(p, {}).get(str(number), 0.0) < BRIEF_S  # noqa: E731
    for contact, row in zip(found, typed):
        frame = int(row["frame"])
        if frame not in said and slip(contact["person"], contact["set"]):
            contact.update(person=None, brief=True)
        if frame not in missed and slip(contact.get("receiver"), contact["set"]):
            del contact["receiver"]


def unjoined(table: dict[int, dict], scraps: set[tuple[int, int]]) -> None:
    """The players of `table` the review shows no card for (`scraps`, identity.leftovers) lose
    their number: tracks that are no identified player on the whole page, an earlier answer naming
    one too, so nothing on it names a player the review cannot show."""
    for person in table.values():
        if (person["team"], person["number"]) in scraps:
            person["number"] = None


def people(track_team: dict[int, int], identities: list[tuple[int, int, int, int, int]], names: dict[tuple[int, int], dict] | None = None) -> tuple[Who, dict[int, dict]]:
    """The page's players, keyed 0, 1, ... as they are first asked for: one per identity
    (identities.csv's rows) with its team, number and the name and jersey number the user gave it
    (`names`, by (team, identity)), one per track without identity, with its team and no number;
    and `who`, the key of the player a track shows at a frame, or of the identity `said` instead."""
    names = names or {}
    find = finder(identities)
    keys: dict[tuple, int] = {}
    table: dict[int, dict] = {}

    def who(track: int | None, frame: int, said: tuple[int, int] | None = None) -> int | None:
        if track is None and said is None:
            return None
        found = said or find(track, frame)
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
    return files.read_json(path)


def club_page(name: str, site: Path) -> dict | None:
    """The club as the pages show it: the app's (CLUB, none until it has one) or the theme branding/NAME/brand.json,
    with its icon in its colours (`favicon`), its logo copied into the site's club/, and its sponsors from sponsors/sponsors.json beside it (git-ignored under
    branding/: brands stay off the repository) with their pictures inlined (the 3D view paints them, which a file:// page
    cannot do from a file); None for `none`."""
    own = club_settings.FOLDER / club_settings.FILE
    if name == "none" or (name == CLUB and not own.exists()):
        return None
    path = own if name == CLUB else club_settings.THEMES / name / club_settings.THEME_FILE
    if not path.exists():
        themes = sorted(p.parent.name for p in club_settings.THEMES.glob(f"*/{club_settings.THEME_FILE}"))
        raise SystemExit(f"Unknown theme {name!r}: available themes are {', '.join([CLUB, *themes, 'none'])}")
    data = json.loads(path.read_text())
    data["favicon"] = icon.favicon(icon.colours({"logo": data.get("logo"), "accent": data.get("light", {}).get("accent")}, path.parent))
    if data.get("logo"):
        (site / "club").mkdir(parents=True, exist_ok=True)
        logo = cv2.imread(str(path.parent / data["logo"]), cv2.IMREAD_UNCHANGED)
        if logo.shape[0] > LOGO_PX:
            logo = cv2.resize(logo, (round(logo.shape[1] * LOGO_PX / logo.shape[0]), LOGO_PX), interpolation=cv2.INTER_AREA)
        target = site / "club" / f"{Path(data['logo']).stem}.webp"
        cv2.imwrite(str(target), logo, [cv2.IMWRITE_WEBP_QUALITY, LOGO_QUALITY])
        data["logo"] = f"club/{target.name}"
    sponsors = path.parent / "sponsors"
    data["sponsors"] = files.read_json(sponsors / "sponsors.json", [])
    # A sponsor without a logo shows as text.
    for sponsor in (s for s in data["sponsors"] if s.get("logo")):
        picture = cv2.imread(str(sponsors / sponsor["logo"]), cv2.IMREAD_UNCHANGED)
        picture = cv2.resize(picture, (round(picture.shape[1] * SPONSOR_PX / picture.shape[0]), SPONSOR_PX), interpolation=cv2.INTER_AREA)
        sponsor["logo"] = "data:image/webp;base64," + base64.b64encode(cv2.imencode(".webp", picture, [cv2.IMWRITE_WEBP_QUALITY, LOGO_QUALITY])[1]).decode()
    return data


def poster(video: Path, frame: int, path: Path) -> bool:
    """Writes `frame` as a POSTER_WIDTH pixels wide WebP; False when the video has no such frame."""
    from volleyball_stats.decode import frame_at

    image = frame_at(video, frame)
    if image is not None:
        height, width = image.shape[:2]
        image = cv2.resize(image, (POSTER_WIDTH, round(height * POSTER_WIDTH / width)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(path), image, [cv2.IMWRITE_WEBP_QUALITY, 65])
    return image is not None


def touched(match: Path, given: dict[tuple[int, int], dict], kind: str = "touch") -> dict[int, tuple[int, int] | None]:
    """The touches the review's answers settle, by frame: the player's (team, identity), found by
    the name `given` them (it outlives the identities' numbers), else by number; None for no touch.
    With `kind` "receiver", the aces' receivers by the serve's frame, None for no one; "partner", the second player a fault
    is shared with, by the fault's frame."""
    path = match / "identity_answers.json"
    answers = files.read_json(path, {}).get(kind, [])
    by_name = {(team, g["name"]): (team, number) for (team, number), g in given.items() if g.get("name")}
    return {t["frame"]: None if t["identity"] is None else by_name.get((t["team"], t.get("name")), (t["team"], t["identity"])) for t in answers}


def answers(match: Path, kind: str) -> list[dict]:
    """The review's answers of `kind` in identity_answers.json."""
    path = match / "identity_answers.json"
    return files.read_json(path, {}).get(kind, [])


# A next serve this soon after a rally ends follows it: no rally was missed in between. First ASPOM
# match, 1 Nov, the set scores' points off the given ones: 9 without the rule, 9 at 25 s
# (points.NEXT_S, the school clips'), 5 at 40 s, 7 from 50 s (a 48 s gap held a missed rally).
NEXT_SERVE_S = 40.0


def started(rallies: list[dict], found: list[dict]) -> None:
    """Each rally starting at its first touch in `found` (its serve, as the review left them: one removed moves it), never
    before the one before ends; one without a touch keeps its window's start."""
    first: dict[int, float] = {}
    for c in found:
        if c["type"] not in NO_PLAYER:
            first[c["rally"]] = min(first.get(c["rally"], c["t"]), c["t"])
    for k, rally in enumerate(rallies):
        if k in first:
            rally["start"] = round(max(first[k], rallies[k - 1]["end"] if k else 0.0), 2)


# A checked rally ends where its last action's ball lands, at most this long after the action. On the four matches
# (18 Nov) the first landing after it came 1.1 s after it at the median, 90% within 2.85 s, the later ones mostly
# bounces; the ends found ran up to 17 s past it. The editor's CLOSE_S.
CLOSE_S = 2.5


def closed(rallies: list[dict], found: list[dict], checked: set[int], within: float = CLOSE_S) -> None:
    """Each rally of `checked` (keys) ending with its last action: where its ball first lands after it, at most `within`
    later, at once after a playing fault; never later than it ended. One without an action keeps its end."""
    by: dict[int, list[dict]] = {}
    for c in found:
        by.setdefault(c["rally"], []).append(c)
    for k, rally in enumerate(rallies):
        touches = sorted(by.get(k, []), key=lambda c: c["t"])
        last = next((c for c in reversed(touches) if c["type"] not in NO_PLAYER), None)
        if rally["key"] not in checked or last is None:
            continue
        lands = next((c["t"] for c in touches if c["type"] in NO_PLAYER and c["t"] >= last["t"]), None)
        end = last["t"] if last["type"] == "fault" else min(lands if lands is not None else last["t"] + within, last["t"] + within)
        rally["end"] = round(min(rally["end"], max(end, last["t"])), 2)


def served_next(rallies: list[dict], found: list[dict], within: float = NEXT_SERVE_S) -> None:
    """Each rally won by the team serving the next one of its set (the sideout rule), when that
    serve (the page's `found` contacts, the review's added serves among them) comes under `within`
    seconds after it."""
    serves: dict[int, int] = {}
    for c in found:
        if c["type"] == "serve" and c.get("team") and c["rally"] not in serves:
            serves[c["rally"]] = c["team"]
    for k, (rally, after) in enumerate(zip(rallies, rallies[1:])):
        if after["set"] == rally["set"] and after["start"] - rally["end"] <= within and k + 1 in serves:
            rally["winner"] = serves[k + 1]


def rewon(rallies: list[dict], winners: dict[int, int]) -> None:
    """`rallies`' winners the review gave (`winners`, by their `key`), then each set's running score
    counted from its rallies' winners: the score the page shows adds up with the winners it shows
    (first ASPOM match, 1 Nov: 9 points off the given scores, against 11 for points.csv's, which
    adds the rallies it thinks were missed)."""
    for rally in rallies:
        if rally["key"] in winners:
            rally["winner"] = winners[rally["key"]]
    counted(rallies)


def followed(rallies: list[dict], found: list[dict], redo: frozenset[int] | set[int] = frozenset(), wrong: frozenset[int] | set[int] = frozenset()) -> None:
    """`rallies`' winners from their last touch in `found` (the page's contacts, the review's
    results included): a point for its team, a fault for the other's; one whose last touch is in
    play, or without a touch, keeps its own. The score follows the actions (the owner's rule, 1 Nov).
    A rally to replay (`redo`, by `key`) gives nobody a point: no winner, its touches in play. One the
    referee got wrong (`wrong`, by `key`) keeps the winner given, the team that got the point: its last
    touch says what really happened."""
    replayed = {k for k, rally in enumerate(rallies) if rally.get("key") in redo}
    for c in found:
        # A playing fault or a ball let fall is a fault, whatever the rally's winner said.
        if c["type"] in NO_BALL:
            c["result"] = "error"
        elif c["rally"] in replayed and c["type"] not in NO_PLAYER:
            c["result"] = "play"
    for k in replayed:
        rallies[k].update(winner=None, redo=True)
    called = {k for k, rally in enumerate(rallies) if rally.get("key") in wrong and k not in replayed and rally["winner"]}
    for k in called:
        rallies[k]["wrongCall"] = True
    last = {c["rally"]: c for c in found if c["type"] not in NO_PLAYER and c.get("team") and c["rally"] not in replayed | called}
    for k, c in last.items():
        if c["result"] in ("point", "error"):
            rallies[k]["winner"] = c["team"] if c["result"] == "point" else 3 - c["team"]
    counted(rallies)


def counted(rallies: list[dict]) -> None:
    """Each set's running score after each of `rallies`, from their winners; none without any."""
    # Without teams, no winner and no score.
    if not any(rally["winner"] for rally in rallies):
        return
    score: dict[int, list[int]] = {}
    for rally in rallies:
        running = score.setdefault(rally["set"], [0, 0])
        if rally["winner"]:
            running[rally["winner"] - 1] += 1
        rally["score"] = list(running)


def wrong_measures(said: list[dict]) -> set[tuple[str, int]]:
    """The readings the review said wrong (`wrong` answers: a record's report answered "Fausse", `review_questions.records`), as
    (the contact's key, its frame)."""
    return {(w["key"], int(w["frame"])) for w in said}


def unmeasured(found: list[dict], wrong: set[tuple[str, int]], fps: float) -> None:
    """The `wrong` readings (key, frame) taken off the contacts of `found`: no trophy, card or film shows them."""
    for c in found:
        frame = c.get("f", round(c["t"] * fps))
        for key in [key for key, at in wrong if at == frame]:
            c.pop(key, None)


# A reading far from its player's own (from OWN_FROM of them) or from everyone's is left out: the owner's rule (15 Nov),
# a trophy or a card never shows one. Far: over FAR_OWN, or FAR_ALL, times the readings' spread (1.4826 times their
# median distance to their median), that spread at least the measure's own noise (MEASURES' floor; a reach's contact
# frame +-2 moves it 0.12 m). On the three matches: 1 serve speed of 322, 7 attack speeds of 312, 8 jumps of 340,
# 10 reaches of 381.
MEASURES = {"speed": ("serve", 3.0), "attackSpeed": ("attack", 5.0), "jump": ("attack", 0.06), "reach": ("attack", 0.2)}
OWN_FROM, FAR_OWN, FAR_ALL = 5, 3.0, 4.5


def unlikely(found: list[dict]) -> None:
    """The readings of `found` far from their player's others or from everyone's taken off (MEASURES)."""

    def spread(values: np.ndarray, floor: float) -> float:
        return max(1.4826 * float(np.median(np.abs(values - np.median(values)))), floor)

    for key, (kind, floor) in MEASURES.items():
        read = [c for c in found if c["type"] == kind and c.get(key) is not None and c.get("person") is not None]
        if not read:
            continue
        everyone = np.array([c[key] for c in read], float)
        middle, wide = float(np.median(everyone)), spread(everyone, floor)
        by: dict[int, list[float]] = {}
        for c in read:
            by.setdefault(c["person"], []).append(c[key])
        own = {p: (float(np.median(v)), spread(np.array(v, float), floor)) for p, v in by.items() if len(v) >= OWN_FROM}
        for c in read:
            mine = own.get(c["person"])
            if abs(c[key] - middle) > FAR_ALL * wide or (mine and abs(c[key] - mine[0]) > FAR_OWN * mine[1]):
                c.pop(key)


def settled_scores(given: list[str | None], rallies: list[dict], checked: set[int]) -> list[str | None]:
    """Each set's final score ("25-21", team 1 first): as given, else its running score once every rally of it is
    checked in the review; None for the rest."""
    sets = sorted({rally["set"] for rally in rallies})
    out = list(given) + [None] * (max(sets, default=0) - len(given))
    for number in sets:
        played = [rally for rally in rallies if rally["set"] == number]
        if not out[number - 1] and played[-1].get("score") and all(rally["key"] in checked for rally in played):
            out[number - 1] = "-".join(map(str, played[-1]["score"]))
    return out


def acted(found: list[dict], typed: list[dict], fixes: dict[int, dict]) -> None:
    """The touches of `found` (from actions CSV rows `typed`) given the type and result the review
    gave (`fixes`, by frame)."""
    for contact, row in zip(found, typed):
        contact.update(fixes.get(int(row["frame"]), {}))


def credited(found: list[dict], typed: list[dict]) -> None:
    """The statistics' reading of a rally's end, over labels that stay what happened (the owner's rule, 4 Nov): a serve, attack or
    block in play the other team's next touch, the rally's last, loses counts as a point, and an attack blocked for a point as a
    fault. `result` is that reading, `label` what such a touch keeps for the review (`labelled`)."""
    touches = [(c, int(row["frame"])) for c, row in zip(found, typed) if c["type"] not in ("floor", "net")]
    last = {c["rally"]: id(c) for c, _ in touches}
    for (a, _), (b, _) in zip(touches, touches[1:]):
        if a["result"] != "play" or b["rally"] != a["rally"] or last[b["rally"]] != id(b) or b["team"] in (None, a["team"]):
            continue
        if a["type"] in ("serve", "attack", "block") and b["type"] in LOSING_TOUCHES and b["result"] == "error":
            a.update(result="point", label="play")
        elif a["type"] == "attack" and b["type"] == "block" and b["result"] == "point":
            a.update(result="error", label="play")


def blamed(found: list[dict], typed: list[dict], causes: dict[int, int | None]) -> None:
    """The faults the review puts on a teammate (`causes`: the fault's frame to the frame of that teammate's earlier touch
    in the rally, None for nobody else): `cause` on the fault, that touch's frame. The statistics count the fault for
    that touch's player and no longer for the one who made it (the owner's rule, 13 Nov); the labels stay what happened."""
    at = {int(row["frame"]): c for c, row in zip(found, typed)}
    for frame, c in at.items():
        on = at.get(causes.get(frame))
        if (
            on is not None and c["result"] == "error" and labelled(c) == "error" and c["type"] not in NO_PLAYER
            and on["rally"] == c["rally"] and on["t"] < c["t"] and on["type"] not in (*NO_PLAYER, *NO_BALL) and on.get("team") and on["team"] == c.get("team")
        ):
            c["cause"] = causes[frame]


def labelled(contact: dict) -> str | None:
    """What a page's touch holds for the review, before the statistics' reading (`credited`)."""
    return contact.get("label", contact.get("result"))


def split_at(windows: list[tuple[int, int]], frames: list[int]) -> list[tuple[int, int, int | None]]:
    """`windows` (start, end) with a rally starting at each of `frames` (the review's `split`
    answers), each with the index of the window it comes from: one inside a window ends it the
    frame before; one between two is a rally the pipeline missed (None), ending there until the
    touches added to it carry it on (`with_added`)."""
    out: list[tuple[int, int, int | None]] = [(a, b, k) for k, (a, b) in enumerate(windows)]
    for f in sorted(set(frames)):
        k = next((n for n, (a, b, _) in enumerate(out) if a <= f <= b), None)
        if k is None:
            out.insert(sum(a < f for a, _, _ in out), (f, f, None))
        elif out[k][0] < f:
            a, b, origin = out[k]
            out[k : k + 1] = [(a, f - 1, origin), (f, b, origin)]
    return out


def split_rallies(rows: list[dict], scores: list[dict], frames: list[int]) -> tuple[list[dict], list[dict]]:
    """rallies.csv's and points.csv's rows split by the review's `split` answers (`split_at`): a
    rally cut in two keeps its point on its second part; a missed rally takes the set and sides of
    the one before it (else after) and no point (`served_next` and the review give its winner)."""
    pieces = split_at([(int(r["start_frame"]), int(r["end_frame"])) for r in rows], frames)
    out_rows, out_scores = [], []
    for n, (a, b, origin) in enumerate(pieces):
        near = origin if origin is not None else next((o for _, _, o in reversed(pieces[:n]) if o is not None), None)
        near = near if near is not None else next((o for _, _, o in pieces[n:] if o is not None), None)
        out_rows.append({**(rows[near] if near is not None else {}), "start_frame": str(a), "end_frame": str(b)})
        last = origin is not None and (n + 1 == len(pieces) or pieces[n + 1][2] != origin)
        out_scores.append(scores[origin] if last else {})
    return out_rows, out_scores


def rally_table(match: Path) -> tuple[list[dict], list[dict]]:
    """rallies.csv's and points.csv's rows ({} each without it), split by the review's answers."""
    rows = read_csv(match / "rallies.csv")
    scores = read_csv(match / "points.csv") if (match / "points.csv").exists() else [{}] * len(rows)
    return split_rallies(rows, scores, [a["frame"] for a in answers(match, "split")])


def no_rallies(match: Path, fps: float) -> set[int]:
    """Start frames of the rally windows the review's answers say are no rally (no play), and of
    those after the end of the match."""
    path = match / "identity_answers.json"
    said = {r["start"] for r in (files.read_json(path, {}).get("rally", [])) if not r["play"]}
    end = match_end(match)
    return said if end is None else said | {int(r["start_frame"]) for r in read_csv(match / "rallies.csv") if int(r["start_frame"]) >= end * fps}


def merge_rallies(windows: list[tuple[int, int]], rows: list[dict], scores: list[dict], merged: set[int]) -> tuple[list, list, list]:
    """The rally windows, rallies.csv's and points.csv's rows with each rally of `merged` (by its
    start in rallies.csv) joined to the next one of its set: its start and row, the next's end and
    point; each later score of the set less the point the first gave."""
    out: tuple[list, list, list] = ([], [], [])
    current, lost, join = None, [0, 0], False
    for window, row, point in zip(windows, rows, scores):
        if row.get("set") != current:
            current, lost, join = row.get("set"), [0, 0], False
        if point.get("score_1"):
            point = {**point, "score_1": str(int(point["score_1"]) - lost[0]), "score_2": str(int(point["score_2"]) - lost[1])}
        if join:
            out[0][-1], out[2][-1] = (out[0][-1][0], max(out[0][-1][1], window[1])), point
        else:
            for part, value in zip(out, (window, row, point)):
                part.append(value)
        join = int(row["start_frame"]) in merged
        if join and point.get("winner"):
            lost[int(point["winner"]) - 1] += 1
    return out


def drop_rallies(windows: list[tuple[int, int]], rows: list[dict], scores: list[dict], actions: list[dict], gone: set[int], lead: int) -> tuple[list, list, list, list]:
    """The rally windows, rallies.csv's and points.csv's rows and actions.csv's but the rallies of
    `gone` (by their start in rallies.csv) and their contacts (from `lead` frames before them), each
    later score of their set less the points they gave."""
    kept: tuple[list, list, list] = ([], [], [])
    current, lost, out = None, [0, 0], []
    for window, row, point in zip(windows, rows, scores):
        if row.get("set") != current:
            current, lost = row.get("set"), [0, 0]
        if int(row["start_frame"]) in gone:
            out.append(window)
            if point.get("winner"):
                lost[int(point["winner"]) - 1] += 1
            continue
        if point.get("score_1"):
            point = {**point, "score_1": str(int(point["score_1"]) - lost[0]), "score_2": str(int(point["score_2"]) - lost[1])}
        for part, value in zip(kept, (window, row, point)):
            part.append(value)
    return *kept, [r for r in actions if not any(a - lead <= int(r["frame"]) <= b for a, b in out)]


def match_data(match: Path, video: Path, calibration: Calibration, share: jobs.Share = jobs.quiet) -> tuple[dict, dict | None]:
    """data.js's match and the player positions, None without player tracks; the share of players.csv read told as it
    goes."""
    cap = cv2.VideoCapture(str(video))
    fps, frame_count, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()
    rally_rows, scores = rally_table(match)
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rally_rows]
    # A rally the review split in two: its first part, whose winner was the whole's.
    ends = {r["start_frame"]: r["end_frame"] for r in read_csv(match / "rallies.csv")}
    cut = {int(r["start_frame"]) for r in rally_rows if ends.get(r["start_frame"], r["end_frame"]) != r["end_frame"]}
    actions = read_csv(match / "actions.csv")
    gap = round(GAP_S * fps)
    teams = read_teams(match)
    with_teams = bool(teams) and (match / "tracks.csv").exists()
    identities = read_identities(match / "identities.csv") if with_teams and (match / "identities.csv").exists() else []
    given = named(identities, read_names(match))
    # The touches the review added come in; those it says are none (the ball out of sight, taken
    # for a touch) go, those it gives the other team change sides.
    # The rallies end where the review says; touches past an end go.
    lead = round(LEAD_S * fps)
    # A rally checked in the review is locked: its touches come back (a rerun may lose one) and no
    # other comes in but those the review adds. One the review split in two is not.
    locks = {a["start"]: a["touches"] for a in answers(match, "locked") if a["start"] not in cut}
    added = answers(match, "added")
    kept = [{"start": start, **t} for start, touches in locks.items() if touches for t in touches]
    windows, actions = with_added(
        ended(windows, answers(match, "end")), rally_rows, actions, kept + added, match / "ball.csv", round(ADDED_NEAR_S * fps), round(ADDED_SAME_S * fps), round(ADDED_FLOOR_S * fps), lead, said_teams(match), said_types(match), said_players(match)
    )
    allowed = {t["frame"] for t in kept} | {a["frame"] for a in added}
    shut = [(a - lead, b) for (a, b), row in zip(windows, rally_rows) if locks.get(int(row["start_frame"]))]
    # The ball's floor and net contacts stay: the lock holds the players' touches.
    actions = [r for r in actions if r["type"] in NO_PLAYER or int(r["frame"]) in allowed or not any(a <= int(r["frame"]) <= b for a, b in shut)]
    scores = scores if with_teams else [{}] * len(windows)
    # Two windows it says are one rally become one.
    windows, rally_rows, scores = merge_rallies(windows, rally_rows, scores, {a["start"] for a in answers(match, "join")})
    said = touched(match, given)
    actions = [crossed(r, said.get(int(r["frame"]))) for r in actions if said.get(int(r["frame"]), ()) is not None and any(a - lead <= int(r["frame"]) <= b for a, b in windows)]
    # And the windows it says are no rally (warm-up, a ball thrown back).
    windows, rally_rows, scores, actions = drop_rallies(windows, rally_rows, scores, actions, no_rallies(match, fps), round(LEAD_S * fps))
    # The player rows around the touches place them.
    near = {f for row in actions for f in range(int(row["frame"]) - gap, int(row["frame"]) + gap + 1)}
    track_team = {int(r["track"]): int(r["team"]) for r in read_csv(match / "tracks.csv")} if with_teams else {}
    teams = teams if with_teams else None
    who, table = people(track_team, identities, given)
    by_frame: dict[int, list[dict]] = {}

    step = max(1, round(STEP_S * fps))

    samples = []
    if (match / "players.csv").exists():
        t = tables.players(match / "players.csv", share)
        at = np.flatnonzero(np.isin(t["frame"], np.fromiter(near, dtype=np.int64, count=len(near))))
        # The rows around the touches place them.
        for values in zip(*(t[k][at].tolist() for k in tables.PLAYERS)):
            by_frame.setdefault(values[0], []).append(dict(zip(tables.PLAYERS, values)))
        if not with_teams:
            # Without teams, tracks are grouped by their side of the net: 1 left, 2 right.
            tracks, first = np.unique(t["track"], return_index=True)
            for k in np.argsort(first, kind="stable").tolist():
                track_team.setdefault(int(tracks[k]), 1 if t["team"][first[k]] == "left" else 2)
        samples = player_samples(t, step, frame_count, who)
    found = contacts(actions, windows, by_frame, fps, calibration, UNDER_PX * height / 720, who, said)
    rallies = []
    for (start, end), row, point in zip(windows, rally_rows, scores):
        rallies.append({
            # What the review's answers name it by: its start in rallies.csv, which an added serve moves.
            "key": int(row["start_frame"]),
            "start": round(start / fps, 2),
            # Where its window starts, which names its automatic reports: `started` moves its start.
            "window": round(start / fps, 2),
            "end": round(end / fps, 2),
            "set": int(row.get("set") or 1),
            "left": int(row["left"]) if row.get("left") else None,
            "winner": int(point["winner"]) if point.get("winner") else None,
            "score": [int(point["score_1"]), int(point["score_2"])] if point.get("score_1") else None,
        })
    for contact in found:
        contact["set"] = rallies[contact["rally"]]["set"]
    from volleyball_stats.review_answers import checked

    started(rallies, found)
    if teams:
        served_next(rallies, found)
    # After the sideout rule, which reads the ends found.
    closed(rallies, found, set(checked(answers(match, "log"))))
    # A rally checked in the review keeps the winner it showed then; one the review gives wins.
    pins = {a["start"]: a["winner"] for a in answers(match, "pinned") if a["start"] not in cut}
    rewon(rallies, {**pins, **{a["start"]: a["winner"] for a in answers(match, "winner")}})
    wrong = said_on(match, "referee", "wrong")
    # The referee got it wrong: the last touch is what really happened, the other team won it.
    settle(found, [3 - r["winner"] if r["winner"] and r["key"] in wrong else r["winner"] for r in rallies])
    said_actions = answers(match, "action")
    # An answer about a fault's cause alone leaves the touch's type and result as said before.
    acted(found, actions, {a["frame"]: {k: a[k] for k in ("type", "result") if k in a} for a in said_actions if "type" in a or "result" in a})
    credited(found, actions)
    blamed(found, actions, {a["frame"]: a["cause"] for a in said_actions if "cause" in a})
    followed(rallies, found, said_on(match, "redo", "redo"), wrong)
    missed = touched(match, given, "receiver")
    receivers(found, actions, by_frame, who, missed)
    partnered(found, actions, touched(match, given, "partner"), who)
    times = playing_time(samples, step, windows, [r["set"] for r in rallies], fps)
    unjoined(table, leftovers(on_court(identities, fps), given))
    brief(found, actions, table, times, said, missed)
    if with_teams:
        jumped(found, table, finder(identities), by_frame, match, video, calibration, fps)
    stop = match_end(match)
    data = {
        "name": video.stem,
        "aliases": files.aliases(match),
        "video": video.name,
        "fps": round(fps, 3),
        "duration": round(frame_count / fps, 2),
        "end": match_end(match),
        "teams": teams and [{"name": t["name"], "colour": hand_edited(parse_colour, t["colour"], "a colour (#rrggbb or a name such as white, rouge, navy)") if t["colour"] else t["jersey"]} for t in teams["teams"]],
        "date": teams and (hand_edited(parse_date, teams["date"], "a date (dd/mm/yyyy or yyyy-mm-dd)") if teams.get("date") else recording_date(video)),
        "title": teams and teams.get("title"),
        "rallies": rallies,
        "contacts": found,
        "zones": zone_cells(),
        "scores": teams and settled_scores(teams.get("scores") or [], rallies, set(checked(answers(match, "log")))),
        # The timeouts found or given, in seconds, those past the end given left out; sets come with teams.
        "timeouts": [
            {"start": round(t["start"] / fps, 2), "end": round(t["end"] / fps, 2), "team": t["team"]}
            for t in (timeouts.shown(match, fps) if teams else [])
            if stop is None or t["start"] / fps < stop
        ],
    }
    for p, seconds in times.items():
        if p in table:
            table[p]["seconds"] = {n: v for n, v in seconds.items() if v >= BRIEF_S}
    data["people"] = table
    fitted = fit_touches(found, match / "ball.csv", calibration, fps)
    net = (teams or {}).get("net") or LOWEST_NET_M
    if court_off(fitted, fps, net):
        # ponytail: left out without a word; the app telling the court is to place again, and placing it on a match already
        # run, is the upgrade.
        fitted = fitted._replace(rallies=[])
        for c in found:
            for k in ("jump", "drift"):
                c.pop(k, None)
    data["ball3d"] = touch_places(fitted)
    measure(fitted, fps, net)
    unmeasured(found, wrong_measures(answers(match, "wrong")), fps)
    unlikely(found)
    return data, {"step": step, "samples": samples} if any(samples) else None


# A close call: half the court's length and width to the lines' outer edges (the lines are in), the ball's radius (a ball
# touching the line is in), how near a line a landing is close.
HALF_X, HALF_Y, BALL_R, NEAR_M = 9.0, 4.5, 0.105, 0.4
TOUCHES = {"serve", "pass", "set", "attack", "relance", "block", "dig"}


def outside(x: float, y: float) -> tuple[float, str]:
    """How far a ball centred on (x, y) lands outside the court (negative inside), and the line it is told against
    ("end" or "side"): the one it is past, else the nearest."""
    dx, dy = abs(x) - HALF_X, abs(y) - HALF_Y
    if dx > 0 or dy > 0:
        return float(np.hypot(max(0.0, dx), max(0.0, dy))), "end" if dx >= dy else "side"
    return (dx, "end") if dx >= dy else (dy, "side")


def line_calls(data: dict) -> list[dict]:
    """The rallies of `data` ending on a ball landing near a line on the other side from its last touch, by time; with a
    wrong call, any such landing. In or out from who won the point (the other team on a wrong call), the measured mark
    kept where it says the same; a close landing where it does not is left out. The page shows them on the video, whose
    camera zooms on their bounce (`framing.camera`)."""
    by_rally: dict[int, list[dict]] = {}
    for c in data["contacts"]:
        if c["type"] not in NO_BALL:
            by_rally.setdefault(c["rally"], []).append(c)
    out = []
    for k, rally in enumerate(data["rallies"]):
        played = by_rally.get(k, [])
        hits = [c for c in played if c["type"] in TOUCHES]
        if not rally.get("winner") or rally.get("redo") or not played or not hits:
            continue
        land, hit = played[-1], hits[-1]
        if land["type"] != "floor" or None in (land["x"], land["y"], hit["x"]) or np.sign(land["x"]) == np.sign(hit["x"]):
            continue
        group = (data.get("teams") and hit.get("team")) or (1 if hit["side"] == "left" else 2)
        won = 3 - rally["winner"] if rally.get("wrongCall") else rally["winner"]
        is_in = won == group
        by, line = outside(land["x"], land["y"])
        agrees = (by <= BALL_R) == is_in
        if rally.get("wrongCall") or (agrees and abs(by) <= NEAR_M):
            out.append({"rally": k, "t": land["t"], "in": is_in, "wrongCall": bool(rally.get("wrongCall")), "mark": {"x": land["x"], "y": land["y"], "line": line} if agrees else None})
    return sorted(out, key=lambda c: c["t"])


def ball_track(match: Path, size: tuple[int, int], fps: float, times: np.ndarray | None = None) -> dict:
    """video.js's ball: the ball's place where it is seen in the rallies (their lead included), every BALL_STEP_S and
    at the corners between (BALL_CORNER), as flat [seconds, x, y, ...] samples, x and y fractions of the picture. The
    seconds are each frame's real ones (`times`, film.frame_times), which the video plays it at: a frame's number drifts
    from them by a few frames over a match, and the trail drawn on the video would leave the ball; without them, the
    frame's number over `fps`."""
    lead, step = round(LEAD_S * fps), max(1, round(BALL_STEP_S * fps))
    rows, _ = rally_table(match)
    windows = ended([(int(r["start_frame"]), int(r["end_frame"])) for r in rows], answers(match, "end"))
    windows = [(start - lead, end) for start, end in merge_rallies(windows, rows, [{}] * len(rows), {a["start"] for a in answers(match, "join")})[0]]
    def inside(at: np.ndarray) -> np.ndarray:
        found = np.zeros(len(at), dtype=bool)
        for a, b in windows:
            found |= (at >= a) & (at <= b)
        return found

    seen = {frame: (x / size[0], y / size[1]) for frame, (x, y) in tables.seen(match / "ball.csv", inside).items()}

    def kept(frame: int) -> bool:
        before = frame - frame % step
        if before == frame:
            return True
        a, b = seen.get(before), seen.get(before + step)
        if a is None or b is None:
            return False
        share = (frame - before) / step
        off = [a[k] + (b[k] - a[k]) * share - seen[frame][k] for k in (0, 1)]
        return float(np.hypot(off[0], off[1] * size[1] / size[0])) > BALL_CORNER

    samples: list[float] = []
    for frame in sorted(seen):
        if kept(frame):
            seconds = float(times[frame]) if times is not None and frame < len(times) else frame / fps
            samples += [round(seconds, 3), round(seen[frame][0], 3), round(seen[frame][1], 3)]
    return {"samples": samples}


def natural_motion(samples: list[list[float]], seconds: float, teams: dict[int, int]) -> list[list[float]]:
    """The samples the page moves players with, `seconds` apart, each person's places as `player_samples` gives them without
    the tracker's noise: far off those around them (a box cut short, the feet of a jump), then filled across a short
    hole they could have walked while their team (`teams`, by person) has under TEAM_ON_COURT there, the players seen longest
    first, else another track holds that body and it would show twice; then smoothed, looking both ways so nothing lags."""
    tracks: dict[int, dict[int, tuple[float, float]]] = {}
    for k, flat in enumerate(samples):
        for person, x, y in zip(flat[0::3], flat[1::3], flat[2::3]):
            tracks.setdefault(person, {})[k] = (x, y)
    half = round(OUTLIER_S / seconds)
    reach = round(3 * SMOOTH_S / seconds)
    weights = np.exp(-0.5 * (np.arange(-reach, reach + 1) * seconds / SMOOTH_S) ** 2)
    spans: dict[int, tuple[int, np.ndarray]] = {}
    standing: dict[int, np.ndarray] = {team: np.zeros(len(samples), int) for team in set(teams.values())}
    for person, places in tracks.items():
        first = min(places)
        span = np.full((max(places) - first + 1, 2), np.nan)
        for k, place in places.items():
            span[k - first] = place
        known = np.flatnonzero(np.isfinite(span[:, 0]))
        padded = np.pad(span, ((half, half), (0, 0)), constant_values=np.nan)
        around = [np.lib.stride_tricks.sliding_window_view(padded[:, axis], 2 * half + 1) for axis in (0, 1)]
        off = np.maximum(*(np.abs(span[known, axis] - np.nanmedian(around[axis][known], axis=1)) for axis in (0, 1))) > OUTLIER_M
        span[known[off]] = np.nan
        spans[person] = first, span
        if person in teams:
            standing[teams[person]][first + np.flatnonzero(np.isfinite(span[:, 0]))] += 1
    for person in sorted(spans, key=lambda person: -len(tracks[person])):
        first, span = spans[person]
        count = standing.get(teams.get(person))
        known = np.flatnonzero(np.isfinite(span[:, 0]))
        for a, b in zip(known, known[1:]):
            hole = (b - a) * seconds
            if b - a < 2 or hole > FILL_S or np.hypot(*(span[b] - span[a])) / hole > FILL_M_S:
                continue
            if count is not None:
                if (count[first + a + 1 : first + b] >= TEAM_ON_COURT).any():
                    continue
                count[first + a + 1 : first + b] += 1
            span[a + 1 : b] = span[a] + (span[b] - span[a]) * ((np.arange(a + 1, b) - a)[:, None] / (b - a))
    out: list[list[float]] = [[] for _ in samples]
    for person, (first, span) in spans.items():
        there = np.isfinite(span[:, 0])
        spread = lambda values: np.convolve(values, weights)[reach : reach + len(span)]  # noqa: E731
        share = spread(there.astype(float))
        smooth = np.stack([spread(np.nan_to_num(span[:, axis])) / np.maximum(share, 1e-9) for axis in (0, 1)], 1)
        for k in np.flatnonzero(there):
            out[first + k] += [person, round(float(smooth[k, 0]), 2), round(float(smooth[k, 1]), 2)]
    return out


def position_files(players: dict, fps: float) -> list[str]:
    """`positions/N.js`'s contents, each POSITIONS_S of the players' positions the page loads as it plays them
    (`unpackFile`): its samples' count, then per person the runs of samples they are away and there, in turn, and their
    moves since their last position in the file, in POSITION_CM."""
    every = round(POSITIONS_S * fps / players["step"])
    samples = players["samples"]
    files = []
    for n, start in enumerate(range(0, len(samples), every)):
        chunk = samples[start : start + every]
        by_person: dict[int, dict[int, tuple[float, float]]] = {}
        for k, flat in enumerate(chunk):
            for person, x, y in zip(flat[0::3], flat[1::3], flat[2::3]):
                by_person.setdefault(person, {})[k] = (x, y)
        columns = []
        for person, places in sorted(by_person.items()):
            runs, xs, ys = [], [], []
            there, run = False, 0
            was_x, was_y = 0, 0
            for k in range(len(chunk)):
                if (k in places) != there:
                    runs.append(run)
                    there, run = not there, 0
                run += 1
                if k in places:
                    x, y = round(places[k][0] * 100 / POSITION_CM), round(places[k][1] * 100 / POSITION_CM)
                    xs.append(x - was_x)
                    ys.append(y - was_y)
                    was_x, was_y = x, y
            columns.append([person, [*runs, run] if there else runs, xs, ys])
        files.append(f"window.MATCH_POSITIONS({n},{json.dumps([len(chunk), columns], separators=(',', ':'))});\n")
    return files


def places_at(players: dict, t: float, fps: float, back: int) -> dict[int, tuple[float, float]]:
    """Each player's place at `t`, or their last one up to `back` samples before."""
    at = round(t * fps / players["step"])
    seen: dict[int, tuple[float, float]] = {}
    for flat in reversed(players["samples"][max(0, at - back) : at + 1]) if at < len(players["samples"]) else ():
        for person, x, y in zip(flat[0::3], flat[1::3], flat[2::3]):
            seen.setdefault(person, (x, y))
    return seen


def with_landings(contacts: list[dict], players: dict, fps: float) -> list[dict]:
    """`contacts` with, on each ball landing in after a point, the players' positions then in `around`: the
    stats' balls dropped between two players read them, without the positions' files. As the page's `playersAt`,
    a player missing from a few samples stays where they were last seen for up to HOLD_S."""
    back = round(HOLD_S * fps / players["step"])
    out = []
    for k, c in enumerate(contacts):
        before = contacts[k - 1] if k else None
        if c["type"] != "floor" or c.get("x") is None or c.get("y") is None or not before or before["rally"] != c["rally"] or before["result"] != "point":
            out.append(c)
            continue
        seen = places_at(players, c["t"], fps, back)
        out.append({**c, "around": [v for person, (x, y) in seen.items() for v in (person, x, y)]})
    return out


def jumped(found: list[dict], table: dict[int, dict], find: Callable, by_frame: dict[int, list[dict]], match: Path, video: Path, calibration: Calibration, fps: float) -> None:
    """Writes on each attack its player's jump where `jumps.measure` finds one: `late`, the ms from the flight's top to
    the hit, `air` its takeoff and landing in seconds from the touch, `jump` its height (from the flight time) and `drift`
    how far it carried towards the net, in metres. The attacker's track is the one showing their identity at the contact; the
    poses stay in jumps.json, the tracks' rows around each attack in jumps_rows.npz."""
    attacks = []
    for c in found:
        person = table.get(c["person"]) if c["type"] == "attack" and c["person"] is not None else None
        if person is None or person["number"] is None:
            continue
        track = next((int(r["track"]) for r in by_frame.get(c["f"], []) if find(int(r["track"]), c["f"]) == (person["team"], person["number"])), None)
        if track is not None:
            attacks.append((c, track))
    if not attacks:
        return
    pairs = [(c["f"], t) for c, t in attacks]
    rows = jumps.attack_rows(match / "players.csv", pairs, fps, match / "jumps_rows.npz")
    poses = jumps.pose_all(video, pairs, rows, fps, match / "jumps.json")
    ball = jumps.read_ball(match / "ball.csv", {f for c, _ in attacks for f in jumps.window(c["f"], fps)}) if (match / "ball.csv").exists() else {}
    for c, t in attacks:
        got = jumps.measure(c["f"], rows[(c["f"], t)], poses[f"{c['f']}:{t}"], calibration, fps, ball)
        if got is None:
            continue
        c["late"] = got["late"]
        # The 3D figure jumps around the touch: a flight not holding it (the touch's frame off the hit) keeps the default.
        if got["takeoff"] < c["f"] < got["landing"]:
            c["air"] = [round((got["takeoff"] - c["f"]) / fps, 2), round((got["landing"] - c["f"]) / fps, 2)]
        c["jump"] = got["height"]
        if got["drift_m"] is not None:
            c["drift"] = got["drift_m"]


def other_half(c: dict, rallies: list[dict], players: dict, fps: float, people: dict, back: int) -> dict[int, tuple[float, float]] | None:
    """The players of the team across the net from touch `c` in their half then, (depth, across) in their frame: metres
    from the net and toward their right as they face it; None without teams."""
    left = rallies[c["rally"]]["left"]
    if not left:
        return None
    # They face the net from the other half: on the right half their right is the far sideline.
    sign = 1 if c["side"] == "left" else -1
    team = 3 - left if sign > 0 else left
    seen = places_at(players, c["t"], fps, back)
    return {person: (sign * x, -sign * y) for person, (x, y) in seen.items() if (people.get(person) or people.get(str(person)) or {}).get("team") == team and sign * x > 0}


def defended(contacts: list[dict], rallies: list[dict], players: dict, fps: float, people: dict) -> list[dict]:
    """`contacts` with, on each attack, where it was hit in `hit` [depth, across], its `block` (1 or 2
    blockers, `defense.doubled`) and the other half's defenders then in `defense`, flat [person, depth, across, position,
    ...], in metres from the net and toward the defenders' right: the positions the perimeter's (`defense.assign`), the
    owner's system, which the page keeps in every system; a defender left over has none. The players held as in
    `with_landings`."""
    back = round(HOLD_S * fps / players["step"])
    out = []
    for k, c in enumerate(contacts):
        here = other_half(c, rallies, players, fps, people, back) if c["type"] == "attack" and c.get("x") is not None and c.get("y") is not None else None
        if here is None:
            out.append(c)
            continue
        start, _, _ = defense.flight(contacts, k)
        double = defense.doubled(here)
        found = defense.assign(defense.layout("perimeter", start[1], double), here)
        flat = [round(v, 1) for person, (_, _, p) in found.items() for v in (person, *here[person], p)]
        out.append({**c, "hit": [round(v, 1) for v in start], "block": 2 if double else 1, **({"defense": flat} if found else {})})
    return out


def received(contacts: list[dict], rallies: list[dict], players: dict, fps: float, people: dict) -> list[dict]:
    """`contacts` with, on each serve, the receiving team's players at the hit in `receive`, flat [person, depth, across,
    ...] in their frame as `defended`'s. The players held as in `with_landings`."""
    back = round(HOLD_S * fps / players["step"])
    out = []
    for c in contacts:
        here = other_half(c, rallies, players, fps, people, back) if c["type"] == "serve" else None
        out.append({**c, "receive": [round(v, 1) for person, place in here.items() for v in (person, *place)]} if here else c)
    return out


def linked(source: Path, target: Path) -> None:
    """`target` the same file as `source`, taking no room (a hard link), else a copy keeping its date."""
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


# film.HIGHLIGHTS: the match's film among the players'.
FILM_HIGHLIGHTS = "*"


def copy_films(films: Path | None, site: Path, names: set[str] = frozenset()) -> dict[str, str]:
    """The films of the folder `films`, the match's and those of the players `names`, in SITE/films/, unchanged ones left there,
    by name their addresses. A film of a name no longer on the page (a renamed player's) is deleted from `films` too."""
    target = site / "films"
    manifest = films / "manifest.json" if films else None
    made = json.loads(manifest.read_text()) if manifest and manifest.exists() else {}
    kept = {name: e for name, e in made.items() if name in names or name == FILM_HIGHLIGHTS}
    if kept != made:
        for e in made.values():
            if e["file"] not in {k["file"] for k in kept.values()}:
                (films / e["file"]).unlink(missing_ok=True)
        files.write_text(manifest, json.dumps(kept, indent=1, ensure_ascii=False) + "\n")
    made = {name: e for name, e in kept.items() if (films / e["file"]).exists()}
    if not made:
        shutil.rmtree(target, ignore_errors=True)
        return {}
    target.mkdir(exist_ok=True)
    for path in target.iterdir():
        if path.name not in {e["file"] for e in made.values()}:
            path.unlink()
    for e in made.values():
        source, copied = films / e["file"], target / e["file"]
        if not copied.exists() or copied.stat().st_mtime != source.stat().st_mtime or copied.stat().st_size != source.stat().st_size:
            linked(source, copied)
    return {name: f"films/{e['file']}?v={e['hash']}" for name, e in made.items()}


# One point of a video's byte index every this many seconds of it.
INDEX_S = 10.0


def mp4_boxes(f: BinaryIO, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """The boxes of the open MP4 file `f` between `start` and `end`: their kind, where their content starts and ends."""
    at = start
    while at + 8 <= end:
        f.seek(at)
        size, kind = struct.unpack(">I4s", f.read(8))
        head = 8
        if size == 1:
            size, head = struct.unpack(">Q", f.read(8))[0], 16
        elif size == 0:
            size = end - at
        if size < head:
            return
        yield kind, at + head, at + size
        at += size


def frames_index(path: Path) -> list[list[float]] | None:
    """Where the MP4 file at `path` holds its video: [time (s), share of the file] every INDEX_S, from its first chunk to
    its last; None without a video track. Chromium places what it loaded of a video at that byte's share of the file in
    its timeline: the page reads it back through this."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        def child(kind: bytes, start: int, end: int) -> tuple[int, int] | None:
            return next(((a, b) for k, a, b in mp4_boxes(f, start, end) if k == kind), None)

        def table(box: tuple[int, int], skip: int, dtype: str, width: int) -> np.ndarray:
            f.seek(box[0] + 4)
            count = struct.unpack(">I", f.read(4))[0]
            f.seek(box[0] + 8 + skip)
            return np.frombuffer(f.read(count * width * np.dtype(dtype).itemsize), dtype).reshape(count, width).astype(np.int64)

        moov = child(b"moov", 0, size)
        for kind, a, b in mp4_boxes(f, *moov) if moov else []:
            mdia = child(b"mdia", a, b) if kind == b"trak" else None
            hdlr = mdia and child(b"hdlr", *mdia)
            if not hdlr:
                continue
            f.seek(hdlr[0] + 8)
            if f.read(4) != b"vide":
                continue
            mdhd = child(b"mdhd", *mdia)
            f.seek(mdhd[0])
            f.seek(mdhd[0] + (20 if f.read(1)[0] else 12))
            timescale = struct.unpack(">I", f.read(4))[0]
            stbl = child(b"stbl", *child(b"minf", *mdia))
            deltas = table(child(b"stts", *stbl), 0, ">u4", 2)
            to_chunk = table(child(b"stsc", *stbl), 0, ">u4", 3)
            stco, co64 = child(b"stco", *stbl), child(b"co64", *stbl)
            offsets = table(stco, 0, ">u4", 1)[:, 0] if stco else table(co64, 0, ">u8", 1)[:, 0]
            times = np.concatenate([[0], np.cumsum(np.repeat(deltas[:, 1], deltas[:, 0]))]) / timescale
            # Samples in each chunk, from the runs of chunks sharing a count.
            per_chunk = np.zeros(len(offsets), np.int64)
            for (first, count, _), following in zip(to_chunk, [*to_chunk[1:, 0], len(offsets) + 1]):
                per_chunk[first - 1 : following - 1] = count
            starts = times[np.minimum(np.cumsum(per_chunk) - per_chunk, len(times) - 1)]
            kept = sorted({*np.unique(np.floor(starts / INDEX_S), return_index=True)[1].tolist(), len(starts) - 1})
            return [[round(float(starts[k]), 2), round(float(offsets[k]) / size, 8)] for k in kept]
    return None


def write_site(data: dict, players: dict | None, video: Path | None, site: Path, copy: bool, av1: Path | None = None, ball: dict | None = None, small: Path | None = None, voice: dict | None = None, films: Path | None = None, pieces: list[list[float]] | None = None) -> None:
    """The page, data.js, the positions' files, the touches' 3D places in ball3d.js, which the 3D view loads, the commentary's `voice` (`speech.voice_index`) and, unless `video` is None, the video, its `av1` copy the page
    plays first where the browser can, its `small` copy it plays in a small player, its poster, a frame from the middle of the first rally, and
    `ball`: the ball's places and the automatic zoom's camera in video.js, which the page loads to draw on the video and
    zoom it (the source; the copies come cut by it). With `pieces` (`timeline.py`) the video plays the match shorter: the
    data, the ball and the positions on its time, `voice` already so."""
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
    if video and small:
        data["small"] = small.name
    index = {p.name: points for p in filter(None, (video, video and av1, video and small)) if (points := frames_index(p))}
    if index:
        data["index"] = index
    middle = (first["start"] + first["end"]) / 2
    if pieces:
        middle = float(timeline.to_copy(pieces, np.array([middle]))[0])
    if video and poster(video, int(np.searchsorted(decode.timestamps(video), middle)), site / "poster.webp"):
        data["poster"] = versioned(site / "poster.webp")
    (site / "players.js").unlink(missing_ok=True)
    shutil.rmtree(site / "positions", ignore_errors=True)
    if players and "natural" not in players:
        # Kept in `players` for the next page built from them (`build`'s `made`): the same teams, the same motion.
        players["natural"] = natural_motion(players["samples"], players["step"] / data["fps"], {int(person): q["team"] for person, q in (data.get("people") or {}).items()})
    moving = players and {**{k: v for k, v in players.items() if k != "natural"}, "samples": players["natural"]}
    # On the shorter video's time, a sample of the match for each of its own.
    positions = position_files(timeline.retimed_positions(moving, data["fps"], pieces) if pieces else moving, data["fps"]) if moving else []
    if positions:
        (site / "positions").mkdir()
        for n, content in enumerate(positions):
            (site / "positions" / f"{n}.js").write_text(content)
        data["positions"] = {"step": players["step"], "every": round(POSITIONS_S * data["fps"] / players["step"]), "files": len(positions), "cm": POSITION_CM}
        data["contacts"] = with_landings(data.get("contacts", []), players, data["fps"])
        if data.get("teams"):
            data["contacts"] = defended(data["contacts"], data["rallies"], moving, data["fps"], data.get("people") or {})
            data["contacts"] = received(data["contacts"], data["rallies"], moving, data["fps"], data.get("people") or {})
            data["defense"] = {"modes": list(defense.MODES), **defense.table()}
    if pieces:
        data = timeline.retimed(data, pieces)
        if ball:
            seen = timeline.retimed_ball(np.array(ball["samples"], dtype=float).reshape(-1, 3), pieces)
            ball = {**ball, "samples": [round(float(v), 3) for v in seen.ravel()]}
    # ball.js: its name until 16 Nov.
    for old in ("ball.js", VIDEO_JS):
        (site / old).unlink(missing_ok=True)
    video_js = video and ball and f"window.MATCH_VIDEO = {json.dumps(ball, separators=(',', ':'))};\n"
    if video_js:
        (site / VIDEO_JS).write_text(video_js)
    (site / "ball3d.js").unlink(missing_ok=True)
    places = data.pop("ball3d", None)
    places_js = f"window.MATCH_BALL3D = {json.dumps(places, separators=(',', ':'))};\n" if places else ""
    if places_js:
        (site / "ball3d.js").write_text(places_js)
    if places_js:
        data["ball3d"] = True
    shutil.rmtree(site / "voice", ignore_errors=True)
    voice_js = ""
    if voice:
        (site / "voice").mkdir()
        for clip in {row[1] for row in voice["lines"]} | set(voice["replay"].values()):
            shutil.copy2(voice["folder"] / clip, site / "voice" / clip)
        voice_js = f"window.MATCH_VOICE = {json.dumps({'lines': voice['lines'], 'replay': voice['replay']}, separators=(',', ':'), ensure_ascii=False)};\n"
        (site / "voice" / "index.js").write_text(voice_js)
        data["voice"] = True
    # Real footage: only beside a page that has the video, which the hosted one keeps behind its password.
    shown_films = copy_films(films if video else None, site, {q["name"] for q in data.get("people", {}).values() if q.get("name")})
    if shown_films:
        data["films"] = shown_films
    data["format"] = FORMAT
    write_data(site, data)
    # Copied with their dates: an upload skips the unchanged ones.
    for kept in filter(None, (video, video and av1, video and small)):
        if copy:
            linked(kept, site / kept.name)
        else:
            (site / kept.name).symlink_to(kept.resolve())


def version(site: Path, data: dict) -> str:
    """data.js's `v` for `data` (without it): its content and the files the page at `site` loads by it. The unhashed scripts
    load with it in their URL: a host or CDN caching them by URL serves each build its own. Not the code: online it is named
    by its content (`matches.share_code`), the review's server has the browser ask for it each time."""
    loaded = [site / "positions" / f"{n}.js" for n in range((data.get("positions") or {}).get("files", 0))]
    loaded += [site / VIDEO_JS, site / "ball3d.js", site / "voice" / "index.js"]
    # As read back from data.js: renew_code finds the same.
    text = json.dumps(json.loads(json.dumps(data)), sort_keys=True) + "".join(p.read_text() for p in loaded if p.exists())
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def write_data(site: Path, data: dict) -> None:
    """data.js holding `data` with its `v`, and the page loading it under that address."""
    data["v"] = version(site, data)
    text = f"window.MATCH = {json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n"
    # Its date kept when it stays: an upload skips it.
    if not (site / "data.js").exists() or (site / "data.js").read_text() != text:
        (site / "data.js").write_text(text)
    index = site / "index.html"
    index.write_text((TEMPLATE / "index.html").read_text().replace('src="data.js"', f'src="data.js?v={data["v"]}"'))


def page_data(site: Path) -> dict | None:
    """The data.js of the page at `site`, None without one."""
    path = site / "data.js"
    if not path.exists():
        return None
    text = path.read_text()
    return json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))


def renew_code(site: Path) -> None:
    """The hosted page at `site` with the page's code as built now (TEMPLATE), its data as it is: a change of the page's
    code alone reaches it without building its data again (`matches.upload_all`), its data.js as it was."""
    data = page_data(site)
    data.pop("v", None)
    shutil.rmtree(site / "assets", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    write_data(site, data)
    (site / "review-app.js").unlink(missing_ok=True)


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


# Player pictures scored together (`photos`): their crops held in memory meanwhile.
SCORE_BATCH = 64


def framed(image: np.ndarray, box: tuple[int, int, int, int]) -> tuple[np.ndarray, tuple[int, int, float]]:
    """A player's whole picture from their `box`: a little room above and below them, widened to
    PHOTO_RATIO; and its left, top and scale (`cut`)."""
    from volleyball_stats.review import CROP_MARGIN

    x1, y1, x2, y2 = box
    my = round((y2 - y1) * CROP_MARGIN)
    return cut(image, (x1 + x2) / 2, y1 - my, y2 + my, max(x2 - x1, round((y2 - y1 + 2 * my) * PHOTO_RATIO)))


# The upscaler once loaded: a picture picked in the review takes a second, not its load again.
LOADED_UPSCALER: list = []


def upscaler() -> tuple | None:
    """The cards' pictures' upscaler (UPSCALER) and its device, downloaded the first time; None when
    it cannot be had (offline): the pictures stay as cut."""
    import urllib.request

    if LOADED_UPSCALER:
        return LOADED_UPSCALER[0]

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
    LOADED_UPSCALER.append((ModelLoader().load_from_file(UPSCALER).to(device).eval(), device))
    return LOADED_UPSCALER[0]


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


def scores_stamp(video: Path) -> str:
    """What the pictures' scores and appearances depend on: the video, the dependencies, the two
    models and the code computing them, not the rest of this module: a new score costs minutes.
    SCORES_FORMAT stands for `scored`, inside `photos`."""
    from volleyball_stats.actions import POSE_MODEL
    from volleyball_stats.identity import REID, describe, load_reid
    from volleyball_stats.review_questions import CROP_MARGIN

    return files.cache_stamp(video, [POSE_MODEL, REID], f"{SCORES_FORMAT}:{CROP_MARGIN}:" + files.code_text(looks, framed, describe, load_reid))


# The re-identification model, its device and `describe`, once loaded: the review makes pictures after each apply.
LOADED_REID: list = []


class Stopped(Exception):
    """The pictures given up (`photos`' `stop`): the review opened another match."""


def photos(match: Path, video: Path, people: dict[int, dict], folder: Path, teams: set[int] = {1, 2}, record: Path | None = None, stop: Callable[[], bool] = lambda: False) -> dict[int, tuple]:
    """A picture of each numbered player of `teams` among `people` in `folder`, as their `photo`: their
    best moment (PHOTO_PICKS), framed, and their `look` for the 3D figures from it (`likeness.dress`); returns each
    pictured player's (frame, box, head). `record` (PHOTO_SHOWN) gets where each picture was taken. Stopped once `stop`
    says so, between two frames read."""
    from volleyball_stats.decode import frames_apart
    from volleyball_stats.review_answers import load_log, piece_key
    from volleyball_stats.review_questions import ALONE, IDENTITY_CROPS, Questions

    if not teams or not (match / "identity_candidates.json").exists():
        return {}
    fps = decode.fps(video)
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
    # The scores and the appearances are kept under what makes them; another stamp's start again.
    # The appearances are written first, so scores under a stamp mean appearances under it too.
    stamp = scores_stamp(video)
    path = match / PHOTO_SCORES
    saved = files.read_json(path, {})
    current = saved.get("stamp") == stamp
    scores = saved["scores"] if current else {}
    name = lambda frame, box: f"{frame}:{','.join(map(str, box))}"  # noqa: E731

    vectors_path = match / PHOTO_VECTORS
    vectors: dict[str, np.ndarray] = {}
    if current and vectors_path.exists():
        with np.load(vectors_path) as found:
            vectors = dict(zip(found["names"].tolist(), found["vectors"].astype(np.float32)))
    reid = LOADED_REID

    def scored(moments: dict[int, list]) -> None:
        """`scores` holding every one of `moments` (`looks`) and `vectors` their appearance (the
        re-identification embedding of their box), read from the video where missing, SCORE_BATCH
        pictures at a time: a long match's cut all at once took the machine's memory (13 Nov)."""
        wanted: dict[int, list[tuple]] = {}
        for f, b in {m for found in moments.values() for m in found if len(scores.get(name(*m), ())) != 6 or name(*m) not in vectors}:
            wanted.setdefault(f, []).append(b)
        pictures: dict[str, tuple] = {}
        boxes: dict[str, np.ndarray] = {}

        def flush() -> None:
            if boxes:
                if not reid:
                    from volleyball_stats.ball import default_device
                    from volleyball_stats.identity import describe, load_reid

                    device = default_device()
                    reid.extend([load_reid(device), device, describe])
                model, device, describe = reid
                vectors.update(zip(boxes, describe(list(boxes.values()), model, device)))
            if pictures:
                for key, (facing, whole, sharp, others, head, kit) in zip(pictures, looks([(p, b) for p, b, _ in pictures.values()])):
                    left, top, scale = pictures[key][2]
                    # The head back in the frame's pixels.
                    scores[key] = [facing, whole, sharp, others, head and [top + head[0] / scale, left + head[1] / scale, top + head[2] / scale], kit]
            pictures.clear()
            boxes.clear()

        scored_any = False
        for frame, image in frames_apart(video, wanted):
            if stop():
                raise Stopped
            for box in wanted[frame]:
                part, (left, top, scale) = framed(image, box)
                # Copies: a view would keep the whole 4K frame alive.
                pictures[name(frame, box)] = (part.copy(), tuple(round((v - o) * scale) for v, o in zip(box, (left, top, left, top))), (left, top, scale))
                x1, y1, x2, y2 = box
                boxes[name(frame, box)] = image[max(0, y1) : y2, max(0, x1) : x2].copy()
                scored_any = True
            if len(boxes) >= SCORE_BATCH:
                flush()
        flush()
        if scored_any:
            files.write_bytes(vectors_path, packed(vectors))
            files.write_text(path, json.dumps({"stamp": stamp, "scores": scores}))

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
    facing_card: dict[int, list] = {}
    for key, found in moments.items():
        kit = np.median([scores[name(*m)][5] for m in kits[key]], axis=0)
        found = list(dict.fromkeys(found + [m for m in kits[key] if room(m[1])]))
        found = [m for m in found if np.linalg.norm(np.subtract(scores[name(*m)][5], kit)) <= KIT] or found
        seen = np.array([vectors[name(*m)] for m in confirmed[key]])
        alike = {m: float(np.median(seen @ vectors[name(*m)])) for m in found}
        moments[key] = [m for m in found if alike[m] >= max(alike.values()) - LIKE]
        # The card's own pictures facing the camera, offered first: the closest moments are often from behind.
        facing_card[key] = sorted({m for m in confirmed[key] if scores[name(*m)][0] > FACED}, key=lambda m: -scores[name(*m)][0])
        fitting_card = [m for m in facing_card[key] if room(m[1]) and np.linalg.norm(np.subtract(scores[name(*m)][5], kit)) <= KIT]
        moments[key] = list(dict.fromkeys(moments[key] + fitting_card))
    # The moments the user picked, by the player's name, else on their card while it still holds that moment.
    path = match / PHOTO_PICKED
    taken = files.read_json(path, {})

    def pick_of(person: dict) -> dict | None:
        if person.get("name") in taken:
            return taken[person["name"]]
        found = taken.get(f"{person['team']}:{person['number']}")
        return found if found and any(a <= found["frame"] <= b for _, a, b, _, _ in questions.pieces(person["team"], person["number"])) else None

    own = {key: (found["frame"], tuple(found["box"])) for key in moments if (found := pick_of(people[key]))}
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
        offered[f"{people[key]['team']}:{people[key]['number']}"] = [{"frame": f, "box": list(b)} for f, b in list(dict.fromkeys([(frame, box), *facing_card[key], *ranked]))[:PHOTO_CHOICES]]
        chosen.setdefault(frame, []).append((key, box))
        picked[key] = (frame, box, scores[name(frame, box)][4])
    files.write_text(match / PHOTO_CANDIDATES, json.dumps(offered))
    folder.mkdir(parents=True, exist_ok=True)
    # A moment already framed and upscaled is not decoded again: most stay from one apply to the next.
    # They are kept under what makes them, by frame, box and head; any other stamp's go.
    stamp = files.cache_stamp(video, [Path(__file__)])
    kept = match / PHOTO_KEPT / stamp
    for old in (match / PHOTO_KEPT).glob("*"):
        if old != kept:
            shutil.rmtree(old, ignore_errors=True)
    kept.mkdir(parents=True, exist_ok=True)

    def kept_at(frame: int, box: tuple) -> Path:
        return moment_file(kept, frame, box, scores[name(frame, box)][4])

    missing = {frame: pairs for frame, pairs in chosen.items() if any(not kept_at(frame, box).exists() for _, box in pairs)}
    up = upscaler() if missing else None
    for frame, image in frames_apart(video, missing):
        for _, box in missing[frame]:
            part = face(image, box, scores[name(frame, box)][4])
            if part.size:
                cv2.imwrite(str(kept_at(frame, box)), upscaled(up, part) if up else touched_up(part), [cv2.IMWRITE_WEBP_QUALITY, 80])
    taken_at = {}
    for frame, pairs in chosen.items():
        for key, box in pairs:
            if kept_at(frame, box).exists():
                shutil.copyfile(kept_at(frame, box), folder / f"{key}.webp")
                people[key]["photo"] = versioned(folder / f"{key}.webp", folder.name)
                taken_at[f"{folder.name}/{key}.webp"] = {"track": questions.track_at(frame, box), "frame": frame}
    if record:
        files.write_text(record, json.dumps(taken_at))
    likeness.dress(match, people, {key: folder / f"{key}.webp" for key in picked if (folder / f"{key}.webp").exists()})
    return picked


def moment_file(kept: Path, frame: int, box: tuple, head: list | None) -> Path:
    """Where the picture framed at `frame` in `box` around `head` is kept, in PHOTO_KEPT's folder `kept`."""
    digest = hashlib.sha256(json.dumps(head).encode()).hexdigest()[:8]
    return kept / f"{frame}_{'_'.join(str(v) for v in box)}_{digest}.webp"


def swap_photo(match: Path, video: Path, site: Path, team: int, number: int, frame: int, box: list[int], track_at: Callable[[int, tuple], int | None]) -> dict | None:
    """The page at `site` with the card picture of identity `number` of `team` the one taken at `frame` in `box` (PHOTO_PICKED
    has it), its look from it; PHOTO_SHOWN and PHOTO_CANDIDATES following, and the page MATCH/site too when it shows the
    player's picture. Only that picture is cut (a second, against a whole page's build). Returns the player's `photo` and
    `look`; None when the moment was not scored (`photos` scores every one it offers) or the page has no such player: the
    pages are to be built again."""
    people = (page_data(site) or {}).get("people") or {}
    key = next((k for k, p in people.items() if (p["team"], p["number"]) == (team, number)), None)
    path = match / PHOTO_SCORES
    saved = files.read_json(path, {})
    box = tuple(int(v) for v in box)
    scored = saved.get("scores", {}).get(f"{frame}:{','.join(map(str, box))}") if saved.get("stamp") == scores_stamp(video) else None
    if key is None or not scored or len(scored) != 6:
        return None
    kept = match / PHOTO_KEPT / files.cache_stamp(video, [Path(__file__)])
    picture = moment_file(kept, frame, box, scored[4])
    if not picture.exists():
        image = decode.frame_at(video, frame)
        part = face(image, box, scored[4]) if image is not None else np.empty(0)
        if not part.size:
            return None
        up = upscaler()
        kept.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(picture), upscaled(up, part) if up else touched_up(part), [cv2.IMWRITE_WEBP_QUALITY, 80])
    folder = site / "players"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(picture, folder / f"{key}.webp")
    person = people[key]
    person["photo"] = versioned(folder / f"{key}.webp", folder.name)
    likeness.dress(match, {key: person}, {key: folder / f"{key}.webp"})
    patch_people(site, people)
    shown = match / PHOTO_SHOWN
    taken = files.read_json(shown, {})
    taken[f"{folder.name}/{key}.webp"] = {"track": track_at(frame, box), "frame": frame}
    files.write_text(shown, json.dumps(taken))
    offered = match / PHOTO_CANDIDATES
    if offered.exists():
        found = json.loads(offered.read_text())
        mine = found.get(f"{team}:{number}", [])
        found[f"{team}:{number}"] = [{"frame": frame, "box": list(box)}, *(m for m in mine if (m["frame"], tuple(m["box"])) != (frame, box))]
        files.write_text(offered, json.dumps(found))
    # The page to publish, with its own pictures when it has them: the same player's swapped too.
    published = page_data(match / "site") if (match / "page.json").exists() else None
    other = next((p for p in (published or {}).get("people", {}).values() if (p["team"], p["number"]) == (team, number) and p.get("photo")), None)
    if other:
        found_at = match / "site" / other["photo"].split("?")[0]
        shutil.copyfile(picture, found_at)
        other["photo"] = versioned(found_at, found_at.parent.name)
        patch_people(match / "site", published["people"])
    return {"photo": person["photo"], "look": person.get("look")}


def versioned(path: Path, folder: str = "") -> str:
    """`path`'s address beside the page with its content's hash: the host lets browsers keep it for
    good, a new picture getting a new address."""
    v = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    return f"{folder}/{path.name}?v={v}" if folder else f"{path.name}?v={v}"


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
    theme: str = CLUB,
    footage: str = "none",
    club: int | str | None = None,
    pictured: set[int] = frozenset(),
    pictures: bool = True,
    light: Path | None = None,
    link: str | None = None,
    feedback: str | None = None,
    av1: Path | None = None,
    small: Path | None = None,
    review: bool = False,
    share: jobs.Share = jobs.quiet,
    made: tuple[dict, dict | None] | None = None,
) -> dict:
    """The match page in `site` with the `footage` FOOTAGE says (`club` the user's team) and the
    pictures of the `pictured` teams' players; `light` a lighter copy of `video` on its timeline for
    the page to play with the full footage, `av1` an AV1 copy played first where the browser can, `small` a 720p one played in a small player, and `link`, on a page without footage, where the same
    page with it is (behind a password); `feedback` where viewers report what is wrong in a moment
    (none: they are not asked); `review` keeps the review's screens (review-app.js) beside it; `made` the match's data
    (`computed`) when another page took it already; returns data.js's match. The share done told as it goes (`share`). ValueError for `light`, `av1` or `small` with a footage to blur (blurring
    works on the tracked video)."""
    if (light or av1 or small) and footage != "full":
        raise ValueError("--light-video, --av1-video and --small-video go with --footage full")
    # Its parts' shares of the time, measured on the second match (15 Nov): players.csv read for the samples, the rest of
    # the data, the pictures, the ball, the zoom's views, the files written.
    part = jobs.parts(share, {"rows": 3.6, "data": 3.5, "photos": 2.0 if pictures else 0.0, "ball": 1.5, "views": 1.7, "write": 4.1})
    if made:
        # The players' positions only read below.
        data, players = deepcopy(made[0]), made[1]
    else:
        data, players = computed(match, video, court, part("rows"))
    part("data")(1.0)
    blurred = {3 - (club or 1)} if footage == "blur-opponents" else {"none": None, "full": set(), "blur-all": {1, 2}}[footage]
    if pictures:
        shutil.rmtree(site / "players", ignore_errors=True)
        photos(match, video, data["people"], site / "players", pictured, match / PHOTO_SHOWN if review else None)
    else:
        kept_photos(data["people"], site, match, ("photo",))
    # The looks the review made and corrected; only beside the video (the hosted one behind its password),
    # never for a blurred team.
    if not review:
        for person in data["people"].values():
            person.pop("look", None)
        kept_photos(data["people"], match / "review", match, ("look",))
    elif not pictures:
        # The looks from the card pictures kept: no new picture needed (a few seconds, each parsed once).
        likeness.dress(match, data["people"], {key: site / p["photo"].split("?")[0] for key, p in data["people"].items() if p.get("photo") and (site / p["photo"].split("?")[0]).exists()})
    hide_looks(data["people"], blurred)
    part("photos")(1.0)
    # The logo's folder, and the one older builds named brand/.
    for folder in ("club", "brand"):
        shutil.rmtree(site / folder, ignore_errors=True)
    data["club"] = club_page(theme, site)
    data["videoPage"] = link if blurred is None else None
    data["feedback"] = feedback
    ball = None
    if blurred is not None and (match / "ball.csv").exists():
        from volleyball_stats import film

        ball = ball_track(match, decode.size(video), data["fps"], film.frame_times(match, video))
    part("ball")(1.0)
    if blurred is not None and (match / "players.csv").exists():
        samples = np.array(ball["samples"] if ball else [], dtype=float).reshape(-1, 3)
        data["views"] = framing.views(framing.read_boxes(match / "players.csv", decode.size(video), data["fps"]), data["rallies"], [c for c in data["contacts"] if c["type"] not in NO_PLAYER], samples)
    pieces = None
    if blurred is not None:
        # The automatic zoom: the copies are cut by the camera recorded with them (`zoomed`), on their own shorter time
        # (`timeline.py`), which the page draws on them with; on the source (the review's page) the page zooms by the
        # camera of the views now.
        made = video_copies.recorded(match, light) if light else None
        data["lineCalls"] = line_calls(data)
        seen = np.array((ball or {}).get("samples", []), dtype=float).reshape(-1, 3)
        if made:
            camera, pieces = made["camera"], made["map"]
        else:
            camera = framing.camera_spans(framing.camera(data.get("views", []), seen, data["duration"], framing.bounces(data["lineCalls"], seen, data["rallies"])))
        ball = {**(ball or {"samples": []}), "camera": camera}
        data["zoomed"] = made is not None
    part("views")(1.0)
    # The commentary placed on the time the video plays, none of it over a cut, which fades the sound out.
    voice = voice_index(match, timeline.retimed(data, pieces), tuple(at + side * timeline.CUT_FADE_S for at in timeline.cuts(pieces) for side in (-1, 1))) if pieces else voice_index(match, data)
    write_site(data, players, None if blurred is None else light or footage_video(match, video, blurred), site, copy, av1, ball, small, voice, match / "films", pieces)
    part("write")(1.0)
    if not review:
        (site / "review-app.js").unlink(missing_ok=True)
    return data


def computed(match: Path, video: Path, court: Path, share: jobs.Share = jobs.quiet) -> tuple[dict, dict | None]:
    """`match_data` for `build`, the court checked against the video: computed once for the pages of a match (`made`)."""
    calibration = Calibration.load(court)
    calibration.check(decode.size(video))
    return match_data(match, video, calibration, share)


def review_page(match: Path, video: Path, court: Path, theme: str = CLUB, pictures: bool = True, share: jobs.Share = jobs.quiet) -> dict:
    """The review's own page in MATCH/review/, with the video and every picture: the published one
    stays as it was built. Without `pictures`, each player keeps their last one (`refresh_photos`)."""
    return build(match, video, court, match / "review", theme=theme, footage="full", pictured={1, 2}, feedback="feedback", pictures=pictures, review=True, share=share)


def hide_looks(people: dict[int, dict], blurred: set[int] | None) -> None:
    """`people` without their looks (hair, skin: taken from the video) on a page without the video (`blurred` None: the
    open hosted one) and for a blurred team: the video goes online behind its password only."""
    for person in people.values():
        if blurred is None or person["team"] in blurred:
            person.pop("look", None)


def kept_photos(people: dict[int, dict], site: Path, match: Path, kept: tuple[str, ...] = ("photo", "look")) -> None:
    """`people` with the pictures the page at `site` shows and the looks that go with them (`kept`), each on
    the player it shows now: the (team, number) whose piece holds where it was taken (PHOTO_SHOWN), else
    the player of the same name; none for the others until the new pictures come. An apply moves numbers
    between players."""
    path = match / PHOTO_SHOWN
    taken = files.read_json(path, {})
    find = finder(read_identities(match / "identities.csv")) if taken and (match / "identities.csv").exists() else None
    by_card: dict[tuple[int, int], dict] = {}
    by_name: dict[str, dict] = {}
    for p in (page_data(site) or {}).get("people", {}).values():
        file = (p.get("photo") or "").split("?")[0]
        if not file or not (site / file).exists():
            continue
        at = taken.get(file)
        if at and at.get("track") is not None and find:
            now = find(at["track"], at["frame"])
            if now:
                by_card.setdefault(now, p)
        elif p.get("name"):
            by_name.setdefault(p["name"], p)
    for person in people.values():
        found = by_card.get((person["team"], person["number"])) or by_name.get(person.get("name") or "")
        for field in kept:
            if found and found.get(field):
                person[field] = found[field]


def refresh_photos(match: Path, video: Path, site: Path, stop: Callable[[], bool] = lambda: False) -> dict:
    """The people of the page at `site` with new pictures in its folder, for `patch_people`; Stopped once `stop` says so."""
    people = page_data(site)["people"]
    photos(match, video, people, site / "players", {1, 2}, match / PHOTO_SHOWN, stop)
    return people


def patch_people(site: Path, people: dict) -> None:
    """The page at `site` showing `people`, its data.js under a new address."""
    data = {**page_data(site), "people": people}
    old = data["v"]
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    new = hashlib.sha256(text.encode()).hexdigest()[:10]
    data["v"] = new
    (site / "data.js").write_text(f"window.MATCH = {json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n")
    index = site / "index.html"
    index.write_text(index.read_text().replace(f"data.js?v={old}", f"data.js?v={new}"))


def publish(match: Path, video: Path, court: Path, theme: str, given: dict, site: Path | None = None, share: jobs.Share = jobs.quiet, made: tuple[dict, dict | None] | None = None) -> tuple[dict, dict]:
    """The page to publish, MATCH/site/ built with page.json's choices, those `given` (not None)
    replacing theirs and saved back, or `site` (to host) with only those `given`: no footage nor
    pictures unless asked, from the data `made` when given (`build`); returns data.js's match and the choices. ValueError for a choice needing a
    club without one, or a court calibrated on another video."""
    path = match / "page.json"
    saved = json.loads(path.read_text()) if path.exists() and site is None else {}
    settings = {"footage": "none", "club": None, "pictures": False, "copy": False, "light": None, "av1": None, "small": None, "link": None, "feedback": None, **saved}
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
    small = Path(settings["small"]) if settings["small"] else None
    data = build(match, video, court, site or match / "site", settings["copy"], theme, settings["footage"], settings["club"], pictured, light=light, link=settings["link"], feedback=settings["feedback"], av1=av1, small=small, share=share, made=made)
    return data, settings


def main() -> None:
    themes = sorted(p.parent.name for p in club_settings.THEMES.glob(f"*/{club_settings.THEME_FILE}"))
    parser = argparse.ArgumentParser(description="Build the static match page from the pipeline's outputs.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/matches/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--out", type=Path, help="Site directory (default: MATCH/site)")
    parser.add_argument("--footage", choices=FOOTAGE, help="What the page shows of the video (default: the previous build's, none with --out: the court's top view replays the moments)")
    parser.add_argument("--club", type=lambda v: v if v == "both" else int(v), choices=(1, 2, "both"), help="Your team, 1 or 2 (team 1 is on the left at the first rally), or both (two teams of your club)")
    parser.add_argument("--pictures", action=argparse.BooleanOptionalAction, help="Your team's players' pictures on their cards (needs --club)")
    parser.add_argument("--copy-video", action=argparse.BooleanOptionalAction, help="Copy the video instead of symlinking it, for hosting")
    parser.add_argument("--light-video", type=Path, help="A lighter copy of --video on its timeline (e.g. 1440p) for the page to play with --footage full; the data still come from --video")
    parser.add_argument("--av1-video", type=Path, help="An AV1 copy of --video on its timeline, 1440p 8-bit (level 5.0), that the page plays first where the browser can; the others play --light-video or --video")
    parser.add_argument("--small-video", type=Path, help="A 720p H.264 copy of --video on its timeline that the page plays while its player is small (not full screen, no zoom on the ball)")
    parser.add_argument("--feedback", help="Where viewers report what is wrong in a moment (e.g. /volleyball/feedback, the hosting's nginx keeps them); none asks nothing")
    parser.add_argument("--video-page", help="On a page without the video, a link to the same page with it, behind a password (e.g. video/)")
    parser.add_argument("--theme", default=CLUB, help=f"Club theme: {CLUB} (the app's), one of branding/NAME/brand.json ({', '.join(themes)}) or none (default: {CLUB})")
    args = parser.parse_args()
    try:
        data, settings = publish(args.match, args.video, args.court, args.theme, {"footage": args.footage, "club": args.club, "pictures": args.pictures, "copy": args.copy_video, "light": args.light_video and str(args.light_video), "av1": args.av1_video and str(args.av1_video), "small": args.small_video and str(args.small_video), "link": args.video_page, "feedback": args.feedback}, args.out)
    except ValueError as error:
        parser.error(str(error))
    site = args.out or args.match / "site"
    sizes = ", ".join(f"{name} {(site / name).stat().st_size / 1e3:.0f} KB" for name in ("data.js",) if (site / name).exists())
    shown = {"none": "no video", "full": "video", "blur-opponents": "video, opponents blurred", "blur-all": "video, both teams blurred"}[settings["footage"]]
    print(f"{len(data['contacts'])} contacts, {len(data['rallies'])} rallies, {sizes}, {shown}{', pictures' if settings['pictures'] else ''} -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
