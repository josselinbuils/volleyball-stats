"""The match page: a static site built from the pipeline's outputs, index.html + data.js + the video.

    uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court COURT_JSON [--club N] [--footage MODE] [--pictures] [--out DIR] [--copy-video] [--theme NAME]

The page (site/, built from web/ with `npm run build` and copied as is) reads the match from data.js,
a script rather than fetched JSON so it opens from the disk by double-clicking index.html, and the
players' positions over the whole video from players.js, which it loads once it has rendered. Every
path is relative: the site directory serves as plain static files. The page holds no footage by
default (`--footage none`): its moments replay on the top view of the court. `--footage full` adds
the video, `blur-opponents` the video with the team other than the `--club` one blurred (blur.py),
`blur-all` the video with both teams blurred. The cards show a silhouette, the `--club` team's
players their picture with `--pictures`. MATCH/page.json remembers these choices: a later build
without them keeps them, a flag changes only its own (`--no-pictures` takes the pictures off); the
blurred copy is kept beside the outputs and made again only when the player tracks change. The video is symlinked unless --copy-video, for hosting; a
poster frame stands in for it until it plays. Teams (names, colours,
sets, the match's date and title, the sets' final scores) come from teams.json, written by match.py
--players, with each player's identity for the whole match (identities.csv) and the score
(points.csv); a teams.json from before the date takes the video's recording date. --theme picks a
club theme from branding/NAME/brand.json (logo, colours), `none` for the neutral one.
"""

import argparse
import csv
import hashlib
import json
import shutil
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.actions import LEAD_S, UNDER_PX, player_under
from volleyball_stats.attribution import GAP_S, box_at
from volleyball_stats.court import LENGTH, WIDTH, Calibration, zone
from volleyball_stats.identity import lookup, named, read_identities, read_names
from volleyball_stats.teams import recording_date

TEMPLATE = Path(__file__).with_name("site")
BRANDING = Path("branding")
# Player positions are kept every STEP_S seconds over the whole video, to the centimetre.
STEP_S = 0.1
POSTER_WIDTH = 800
# What the page shows of the video: nothing, all of it, or the video with some players blurred.
FOOTAGE = ("none", "full", "blur-opponents", "blur-all")
# The club logo shows at most 64 px tall, the players' pictures about 240 px: kept at twice that for
# sharp high-density screens, never enlarged. The pictures are 3 wide for 4 tall, like a photo.
LOGO_PX, PHOTO_PX, PHOTO_RATIO = 128, 480, 0.75


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
    """Outcome of a contact from the next one of its rally: "point" when that is the ball landing in
    the court on the other side of the net, "error" when it lands on the contact's side, out, or
    in the net, "play" otherwise, and for the floor and net contacts themselves."""
    if contact["type"] in ("floor", "net") or after is None or after["type"] not in ("floor", "net"):
        return "play"
    inside = after["x"] is not None and abs(after["x"]) <= LENGTH / 2 and abs(after["y"]) <= WIDTH / 2
    return "point" if after["type"] == "floor" and after["side"] != contact["side"] and inside else "error"


# The player a (track, frame) shows on the page, None without a track.
Who = Callable[[int | None, int], int | None]


def contacts(typed: list[dict], windows: list[tuple[int, int]], players: dict[int, list[dict]], fps: float, calibration: Calibration, reach: float, who: Who = lambda track, _: track) -> list[dict]:
    """The page's contacts from the actions CSV rows: time, type, side, team (None without teams),
    rally index, court position, zone, result and the attributed track's player (`who`); an ace
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
            "person": who(track, frame),
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


def people(track_team: dict[int, int], identities: list[tuple[int, int, int, int, int]], names: dict[tuple[int, int], dict] | None = None) -> tuple[Who, dict[int, dict]]:
    """The page's players, keyed 0, 1, ... as they are first asked for: one per identity
    (identities.csv's rows) with its team, number and the name and jersey number the user gave it
    (`names`, by (team, identity)), one per track without identity, with its team and no number;
    and `who`, the key of the player a track shows at a frame."""
    names = names or {}
    by_track: dict[int, list] = {}
    for r in identities:
        by_track.setdefault(r[0], []).append(r)
    keys: dict[tuple, int] = {}
    table: dict[int, dict] = {}

    def who(track: int | None, frame: int) -> int | None:
        if track is None:
            return None
        found = lookup(by_track.get(track, []), track, frame)
        name = ("identity", *found) if found else ("track", track)
        if name not in keys:
            keys[name] = len(keys)
            given = names.get(found, {}) if found else {}
            table[keys[name]] = {"team": found[0] if found else track_team.get(track, 1), "number": found[1] if found else None, "jersey": given.get("jersey"), "name": given.get("name")}
        return keys[name]

    return who, table


def read_teams(match: Path) -> dict | None:
    """teams.json of a match run with --players, None without it."""
    path = match / "teams.json"
    return json.loads(path.read_text()) if path.exists() else None


def brand(name: str, site: Path) -> dict | None:
    """The club theme branding/NAME/brand.json with its logo copied into the site; None for `none`."""
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


def match_data(match: Path, video: Path, calibration: Calibration) -> tuple[dict, dict | None]:
    """data.js's match and players.js's player positions, None without player tracks."""
    cap = cv2.VideoCapture(str(video))
    fps, frame_count, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()
    rally_rows = read_csv(match / "rallies.csv")
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rally_rows]
    actions = read_csv(match / "actions.csv")
    gap = round(GAP_S * fps)
    # The player rows around the touches place them; all the rows feed the samples, read once.
    near = {f for row in actions for f in range(int(row["frame"]) - gap, int(row["frame"]) + gap + 1)}
    teams = read_teams(match)
    with_teams = bool(teams) and (match / "tracks.csv").exists()
    track_team = {int(r["track"]): int(r["team"]) for r in read_csv(match / "tracks.csv")} if with_teams else {}
    teams = teams if with_teams else None
    identities = read_identities(match / "identities.csv") if teams and (match / "identities.csv").exists() else []
    who, table = people(track_team, identities, named(identities, read_names(match)))
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
    found = contacts(actions, windows, by_frame, fps, calibration, UNDER_PX * height / 720, who)
    scores = read_csv(match / "points.csv") if teams and (match / "points.csv").exists() else [{}] * len(windows)
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
    data = {
        "name": video.stem,
        "video": video.name,
        "fps": round(fps, 3),
        "duration": round(frame_count / fps, 2),
        "teams": teams and [{"name": t["name"], "colour": t["colour"] or t["jersey"]} for t in teams["teams"]],
        "date": teams and (teams.get("date") or recording_date(video)),
        "title": teams and teams.get("title"),
        "rallies": rallies,
        "contacts": found,
        "zones": zone_cells(),
        "scores": teams and teams.get("scores"),
    }
    data["people"] = table
    return data, {"step": step, "samples": samples} if any(samples) else None


def write_site(data: dict, players: dict | None, video: Path | None, site: Path, copy: bool) -> None:
    """The page, data.js, players.js and, unless `video` is None, the video and its poster, a frame
    from the middle of the first rally."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(site / "assets", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    # A previous build's footage goes: the page may now hold none, or another copy.
    for old in [site / "poster.webp", *site.glob("*.mp4")]:
        old.unlink(missing_ok=True)
    first = data["rallies"][0] if data["rallies"] else {"start": 0, "end": 0}
    data = {**data, "video": video and video.name}
    if video and poster(video, round((first["start"] + first["end"]) / 2 * data["fps"]), site / "poster.webp"):
        data["poster"] = "poster.webp"
    (site / "players.js").unlink(missing_ok=True)
    players_js = players and f"window.MATCH_PLAYERS = {json.dumps(players, separators=(',', ':'))};\n"
    if players_js:
        (site / "players.js").write_text(players_js)
    # The unhashed scripts load with the build's hash in their URL: a host or CDN caching them by URL
    # serves each build its own.
    built = json.dumps(data, sort_keys=True) + (players_js or "") + (site / "scene3d.js").read_text()
    data["v"] = hashlib.sha256(built.encode()).hexdigest()[:10]
    (site / "data.js").write_text(f"window.MATCH = {json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n")
    index = site / "index.html"
    index.write_text(index.read_text().replace('src="data.js"', f'src="data.js?v={data["v"]}"'))
    if video:
        if copy:
            shutil.copy(video, site / video.name)
        else:
            (site / video.name).symlink_to(video.resolve())


def photos(match: Path, video: Path, people: dict[int, dict], folder: Path, teams: set[int] = {1, 2}) -> None:
    """A picture of each numbered player of `teams` among `people` in `folder`, as their `photo`: the clearest
    moment of their longest piece of track, a little room above and below them, widened to
    PHOTO_RATIO."""
    from volleyball_stats.identity import frames_at
    from volleyball_stats.review import CROP_MARGIN, Questions

    if not teams or not (match / "identity_candidates.json").exists():
        return
    questions = Questions(match, cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS))
    wanted: dict[int, list] = {}
    for key, person in people.items():
        pieces = questions.pieces(person["team"], person["number"]) if person["number"] and person["team"] in teams else []
        if pieces and pieces[0][0] in questions.rows:
            track, start, end, _, _ = pieces[0]
            frame = questions.clear(track, start, end)
            wanted.setdefault(frame, []).append((key, questions.box(track, frame)))
    folder.mkdir(parents=True, exist_ok=True)
    for frame, image in frames_at(video, wanted):
        for key, (x1, y1, x2, y2) in wanted[frame]:
            my = round((y2 - y1) * CROP_MARGIN)
            top, bottom = max(0, y1 - my), min(image.shape[0], y2 + my)
            half = max(x2 - x1, round((bottom - top) * PHOTO_RATIO)) // 2
            left = min(max(0, (x1 + x2) // 2 - half), max(0, image.shape[1] - 2 * half))
            part = image[top:bottom, left : left + 2 * half]
            if part.size:
                if part.shape[0] > PHOTO_PX:
                    part = cv2.resize(part, (max(1, round(part.shape[1] * PHOTO_PX / part.shape[0])), PHOTO_PX), interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(folder / f"{key}.webp"), part, [cv2.IMWRITE_WEBP_QUALITY, 80])
                people[key]["photo"] = f"{folder.name}/{key}.webp"


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
    match: Path, video: Path, court: Path, site: Path, copy: bool = False, theme: str = "aspom", footage: str = "none", club: int | None = None, pictured: set[int] = frozenset()
) -> dict:
    """The match page in `site` with the `footage` FOOTAGE says (`club` the user's team) and the
    pictures of the `pictured` teams' players; returns data.js's match."""
    data, players = match_data(match, video, Calibration.load(court))
    blurred = {"none": None, "full": set(), "blur-all": {1, 2}}.get(footage, {3 - (club or 1)})
    shutil.rmtree(site / "players", ignore_errors=True)
    photos(match, video, data["people"], site / "players", pictured)
    shutil.rmtree(site / "brand", ignore_errors=True)
    data["brand"] = brand(theme, site)
    write_site(data, players, None if blurred is None else footage_video(match, video, blurred), site, copy)
    return data


def publish(match: Path, video: Path, court: Path, theme: str, given: dict, site: Path | None = None) -> tuple[dict, dict]:
    """The page to publish, MATCH/site/ unless `site`, built with page.json's choices, those `given`
    (not None) replacing theirs and saved back; returns data.js's match and the choices. ValueError
    for a choice needing a club without one."""
    path = match / "page.json"
    settings = {"footage": "none", "club": None, "pictures": False, "copy": False, **(json.loads(path.read_text()) if path.exists() else {})}
    settings.update({k: v for k, v in given.items() if v is not None})
    if settings["club"] is None and (settings["footage"] == "blur-opponents" or settings["pictures"]):
        raise ValueError("--footage blur-opponents and --pictures need --club 1 or 2")
    path.write_text(json.dumps(settings, indent=2) + "\n")
    pictured = {settings["club"]} if settings["pictures"] else set()
    data = build(match, video, court, site or match / "site", settings["copy"], theme, settings["footage"], settings["club"], pictured)
    return data, settings


def main() -> None:
    themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
    parser = argparse.ArgumentParser(description="Build the static match page from the pipeline's outputs.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--out", type=Path, help="Site directory (default: MATCH/site)")
    parser.add_argument("--footage", choices=FOOTAGE, help="What the page shows of the video (default: the previous build's, else none: the court's top view replays the moments)")
    parser.add_argument("--club", type=int, choices=(1, 2), help="Your team, 1 or 2 (team 1 is on the left at the first rally)")
    parser.add_argument("--pictures", action=argparse.BooleanOptionalAction, help="Your team's players' pictures on their cards (needs --club)")
    parser.add_argument("--copy-video", action=argparse.BooleanOptionalAction, help="Copy the video instead of symlinking it, for hosting")
    parser.add_argument("--theme", default="aspom", help=f"Club theme from branding/NAME/brand.json: {', '.join(themes + ['none'])} (default: aspom)")
    args = parser.parse_args()
    try:
        data, settings = publish(args.match, args.video, args.court, args.theme, {"footage": args.footage, "club": args.club, "pictures": args.pictures, "copy": args.copy_video}, args.out)
    except ValueError as error:
        parser.error(str(error))
    site = args.out or args.match / "site"
    sizes = ", ".join(f"{name} {(site / name).stat().st_size / 1e3:.0f} KB" for name in ("data.js", "players.js") if (site / name).exists())
    shown = {"none": "no video", "full": "video", "blur-opponents": "video, opponents blurred", "blur-all": "video, both teams blurred"}[settings["footage"]]
    print(f"{len(data['contacts'])} contacts, {len(data['rallies'])} rallies, {sizes}, {shown}{', pictures' if settings['pictures'] else ''} -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
