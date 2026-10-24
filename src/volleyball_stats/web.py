"""The match page: a static site built from the pipeline's outputs, index.html + data.js + the video.

    uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court COURT_JSON [--out DIR] [--copy-video] [--theme NAME]

The page (site/, built from web/ with `npm run build` and copied as is) reads the match from data.js,
a script rather than fetched JSON so it opens from the disk by double-clicking index.html, and the
players' positions over the whole video from players.js, which it loads once it has rendered. Every
path is relative: the site directory serves as plain static files. The video is symlinked unless
--copy-video, for hosting; a poster frame stands in for it until it plays. Teams (names, colours,
sets, the match's date and title) come from teams.json, written by match.py --players; a teams.json
from before the date takes the video's recording date. --theme picks a club theme from
branding/NAME/brand.json (logo, colours), `none` for the neutral one.
"""

import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.actions import LEAD_S, UNDER_PX, player_under
from volleyball_stats.attribution import GAP_S, box_at
from volleyball_stats.court import ATTACK, LENGTH, WIDTH, Calibration
from volleyball_stats.teams import recording_date

TEMPLATE = Path(__file__).with_name("site")
BRANDING = Path("branding")
# Player positions are kept every STEP frames over the whole video, to the centimetre.
STEP = 3
# The page plays a rally with a second around it, and numbers its players over that time.
PAD_S = 1.0
POSTER_WIDTH = 800
# The club logo shows at most 64 px tall: kept at twice that for sharp high-density screens.
LOGO_PX = 128


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


def zone(x: float, y: float) -> int:
    """Volleyball zone of (x, y) in its half, seen from that half's end line: front row 4-3-2 and
    back row 5-6-1 from left to right. A point off the court takes the nearest zone."""
    # Thirds of the width from the far sideline: the left half's players face the net, their
    # left hand toward the far sideline; the right half's toward the near one.
    third = min(2, max(0, int((y + WIDTH / 2) // (WIDTH / 3))))
    if x > 0:
        third = 2 - third
    return (4, 3, 2)[third] if abs(x) < ATTACK else (5, 6, 1)[third]


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


def contacts(typed: list[dict], windows: list[tuple[int, int]], players: dict[int, list[dict]], fps: float, calibration: Calibration, reach: float) -> list[dict]:
    """The page's contacts from the actions CSV rows: time, type, side, team (None without teams),
    rally index, court position, zone, result and attributed track. A contact with a track is placed
    at that player's feet, else by `spot`. `players` holds the player CSV rows by frame."""
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
            "track": track,
        })
    for contact, after in zip(out, out[1:] + [None]):
        contact["result"] = result(contact, after if after and after["rally"] == contact["rally"] else None)
    return out


def player_samples(rows: list[dict], step: int, frame_count: int) -> list[list[float]]:
    """The players' court feet every `step` frames of the video, from frame 0, each sample a flat
    [track, x, y, ...] list rounded to the centimetre."""
    samples: list[list[float]] = [[] for _ in range(-(-frame_count // step))]
    for row in rows:
        frame = int(row["frame"])
        if frame % step == 0 and frame // step < len(samples):
            samples[frame // step] += [int(row["track"]), round(float(row["court_x"]), 2), round(float(row["court_y"]), 2)]
    return samples


def numbers(players: dict[int, list[dict]], window: tuple[int, int], serve: int, teams: dict[int, int]) -> dict[int, int]:
    """Numbers 1, 2, ... of each team's tracks over a rally `window`, for the page to tell them apart
    until they are named: the tracks already there at the `serve` frame by their zone then (1 back
    right, 2 front right, 3 front middle, 4 front left, 5 back left, 6 back middle), then the later
    ones as they appear. `players` holds the player CSV rows by frame."""
    first: dict[int, int] = {}
    near: dict[int, tuple[int, tuple[float, float]]] = {}
    for frame in range(window[0], window[1] + 1):
        for row in players.get(frame, []):
            track = int(row["track"])
            if track in teams:
                first.setdefault(track, frame)
                if track not in near or abs(frame - serve) < near[track][0]:
                    near[track] = (abs(frame - serve), (float(row["court_x"]), float(row["court_y"])))
    out = {}
    for team in (1, 2):
        mine = [t for t in first if teams[t] == team]
        starters = sorted((t for t in mine if first[t] <= serve), key=lambda t: (zone(*near[t][1]), near[t][1][1]))
        later = sorted((t for t in mine if first[t] > serve), key=lambda t: first[t])
        out.update((t, k) for k, t in enumerate(starters + later, 1))
    return out


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
    rows = read_csv(match / "players.csv") if (match / "players.csv").exists() else []
    by_frame: dict[int, list[dict]] = {}
    for row in rows:
        by_frame.setdefault(int(row["frame"]), []).append(row)
    teams = read_teams(match)
    if teams and (match / "tracks.csv").exists():
        track_team = {int(r["track"]): int(r["team"]) for r in read_csv(match / "tracks.csv")}
    else:
        # Without teams, tracks are grouped by their side of the net: 1 left, 2 right.
        teams, track_team = None, {int(r["track"]): 1 if r["team"] == "left" else 2 for r in rows}
    found = contacts(read_csv(match / "actions.csv"), windows, by_frame, fps, calibration, UNDER_PX * height / 720)
    pad = round(PAD_S * fps)
    rallies = []
    for (start, end), row in zip(windows, rally_rows):
        rallies.append({
            "start": round(start / fps, 2),
            "end": round(end / fps, 2),
            "set": int(row.get("set") or 1),
            "left": int(row["left"]) if row.get("left") else None,
            "numbers": numbers(by_frame, (start - pad, end + pad), start, track_team),
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
        "tracks": {track: {"team": team, "jersey": None} for track, team in sorted(track_team.items())},
    }
    return data, {"step": STEP, "samples": player_samples(rows, STEP, frame_count)} if rows else None


def write_site(data: dict, players: dict | None, video: Path, site: Path, copy: bool) -> None:
    """The page, data.js, players.js, the video and its poster, a frame from the middle of the first
    rally."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(site / "assets", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    first = data["rallies"][0] if data["rallies"] else {"start": 0, "end": 0}
    if poster(video, round((first["start"] + first["end"]) / 2 * data["fps"]), site / "poster.webp"):
        data = {**data, "poster": "poster.webp"}
    (site / "data.js").write_text(f"window.MATCH = {json.dumps(data, separators=(',', ':'), ensure_ascii=False)};\n")
    (site / "players.js").unlink(missing_ok=True)
    if players:
        (site / "players.js").write_text(f"window.MATCH_PLAYERS = {json.dumps(players, separators=(',', ':'))};\n")
    target = site / video.name
    target.unlink(missing_ok=True)
    if copy:
        shutil.copy(video, target)
    else:
        target.symlink_to(video.resolve())


def main() -> None:
    themes = sorted(p.parent.name for p in BRANDING.glob("*/brand.json"))
    parser = argparse.ArgumentParser(description="Build the static match page from the pipeline's outputs.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--out", type=Path, help="Site directory (default: MATCH/site)")
    parser.add_argument("--copy-video", action="store_true", help="Copy the video instead of symlinking it, for hosting")
    parser.add_argument("--theme", default="aspom", help=f"Club theme from branding/NAME/brand.json: {', '.join(themes + ['none'])} (default: aspom)")
    args = parser.parse_args()

    site = args.out or args.match / "site"
    data, players = match_data(args.match, args.video, Calibration.load(args.court))
    shutil.rmtree(site / "brand", ignore_errors=True)
    data["brand"] = brand(args.theme, site)
    write_site(data, players, args.video, site, args.copy_video)
    sizes = ", ".join(f"{name} {(site / name).stat().st_size / 1e3:.0f} KB" for name in ("data.js", "players.js") if (site / name).exists())
    print(f"{len(data['contacts'])} contacts, {len(data['rallies'])} rallies, {sizes} -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
