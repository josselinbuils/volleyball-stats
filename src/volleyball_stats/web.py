"""The match page: a static site built from the pipeline's outputs, index.html + data.js + the video.

    uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court COURT_JSON [--out DIR] [--copy-video]

The page (site/, built from web/ with `npm run build` and copied as is) reads the match from data.js,
a script rather than fetched JSON so it opens from the disk by double-clicking index.html. Every
path is relative: the site directory serves as plain static files. The video is symlinked unless
--copy-video, for hosting; a poster frame stands in for it until it plays.
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

TEMPLATE = Path(__file__).with_name("site")
# Player positions are kept every STEP frames, to the centimetre, from PAD_S before each rally to
# PAD_S after: the page plays a rally with a second around it.
STEP = 3
PAD_S = 1.0
POSTER_WIDTH = 800


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
    """The page's contacts from the actions CSV rows: time, type, side, rally index, court position,
    zone, result and attributed track. A contact with a track is placed at that player's feet, else
    by `spot`. `players` holds the player CSV rows by frame."""
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
            "rally": rally,
            "x": None if xy is None else round(xy[0], 2),
            "y": None if xy is None else round(xy[1], 2),
            "zone": None if xy is None else zone(*xy),
            "track": track,
        })
    for contact, after in zip(out, out[1:] + [None]):
        contact["result"] = result(contact, after if after and after["rally"] == contact["rally"] else None)
    return out


def padded(windows: list[tuple[int, int]], pad: int, frame_count: int) -> list[tuple[int, int]]:
    """The (first, last) frame windows widened by `pad` frames within the video, overlaps merged."""
    out: list[tuple[int, int]] = []
    for start, end in windows:
        start, end = max(0, start - pad), min(frame_count - 1, end + pad)
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def player_spans(rows: list[dict], step: int, windows: list[tuple[int, int]]) -> list[dict]:
    """Per window, the court feet of the players every `step` frames as flat [x, y, ...] lists, left
    team first, right team second; `from` is the index (frame // step) of the window's first sample."""
    out, index = [], {}
    for start, end in windows:
        first = -(-start // step)
        samples: list[list[list[float]]] = [[[], []] for _ in range(first, end // step + 1)]
        out.append({"from": first, "samples": samples})
        index.update((first + k, sample) for k, sample in enumerate(samples))
    for row in rows:
        frame = int(row["frame"])
        if frame % step == 0 and (sample := index.get(frame // step)) is not None:
            sample[row["team"] == "right"] += [round(float(row["court_x"]), 2), round(float(row["court_y"]), 2)]
    return out


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


def match_data(match: Path, video: Path, calibration: Calibration) -> dict:
    cap = cv2.VideoCapture(str(video))
    fps, frame_count, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in read_csv(match / "rallies.csv")]
    rows = read_csv(match / "players.csv") if (match / "players.csv").exists() else []
    by_frame: dict[int, list[dict]] = {}
    for row in rows:
        by_frame.setdefault(int(row["frame"]), []).append(row)
    return {
        "name": video.stem,
        "video": video.name,
        "fps": round(fps, 3),
        "duration": round(frame_count / fps, 2),
        "rallies": [{"start": round(start / fps, 2), "end": round(end / fps, 2)} for start, end in windows],
        "contacts": contacts(read_csv(match / "actions.csv"), windows, by_frame, fps, calibration, UNDER_PX * height / 720),
        "zones": zone_cells(),
        "players": {"step": STEP, "spans": player_spans(rows, STEP, padded(windows, round(PAD_S * fps), frame_count))},
    }


def write_site(data: dict, video: Path, site: Path, copy: bool) -> None:
    """The page, data.js, the video and its poster, a frame from the middle of the first rally."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(site / "assets", ignore_errors=True)
    shutil.copytree(TEMPLATE, site, dirs_exist_ok=True)
    first = data["rallies"][0] if data["rallies"] else {"start": 0, "end": 0}
    if poster(video, round((first["start"] + first["end"]) / 2 * data["fps"]), site / "poster.webp"):
        data = {**data, "poster": "poster.webp"}
    (site / "data.js").write_text(f"window.MATCH = {json.dumps(data, separators=(',', ':'))};\n")
    target = site / video.name
    target.unlink(missing_ok=True)
    if copy:
        shutil.copy(video, target)
    else:
        target.symlink_to(video.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static match page from the pipeline's outputs.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--out", type=Path, help="Site directory (default: MATCH/site)")
    parser.add_argument("--copy-video", action="store_true", help="Copy the video instead of symlinking it, for hosting")
    args = parser.parse_args()

    site = args.out or args.match / "site"
    data = match_data(args.match, args.video, Calibration.load(args.court))
    write_site(data, args.video, site, args.copy_video)
    print(f"{len(data['contacts'])} contacts, {len(data['rallies'])} rallies, data.js {(site / 'data.js').stat().st_size / 1e3:.0f} KB -> {site / 'index.html'}")


if __name__ == "__main__":
    main()
