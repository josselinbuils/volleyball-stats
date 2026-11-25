"""The ball's path in the films: the first pass's detections (ball.csv) chained into flights and searched again, sharper, around
them in the frames the films show (`search_ball`, kept in BALL_CACHE whatever changes), then each film's path across the holes
(`film_path`). And the 4K footage's frames read exactly, at their real times (`frame_times`, `decoder`)."""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import ball as tracker
from volleyball_stats import decode, files, jobs, tables
from volleyball_stats.court import Calibration, distort, undistort

BALL_CACHE, TIMES_CACHE = "film_ball.json", "frame_times.npy"
SOURCE_W, SOURCE_H = 3840, 2160
FPS = 50.0
# The ball. A ball never stays put this long, moves no faster, and a sudden change of its velocity is a touch, a block or the floor.
STILL_FRAMES, STILL_PX, TELEPORT_PX = 20, 14.0, 110.0
CHAIN_FRAMES, KINK_PX, INLIER_PX = 60, 8.0, 16.0
# A flight this much smaller than a ball on our court can look, at its worst, is a ball on another court: its size, read against
# frames SIZE_GAP away so that all of it shows. Single frames read too small at times, so a flight is judged by its upper sizes.
SMALL_FLIGHT, SIZE_GAP, SIZE_LEAST_POINTS = 0.7, 10, 5
# A ball's diameter, and the volume it plays in around the court, in metres.
BALL_M, VOLUME_X, VOLUME_Y, VOLUME_H = 0.21, 13.0, 7.0, 10.0
# Flights this close join up: a line drawn over a longer hole is a guess, and no effect is better than one on nothing. After the
# last touch this long unseen, the ball is lost.
JOIN_FRAMES, LOST_FRAMES = 10, 8
# Where the search looks around the first pass: sharper first, in up to 4 times the first pass's detail.
CROPS = ((1536, 864), (960, 540))
TAIL_CROPS = ((1536, 864), (2560, 1440))
WINDOW_PAD_S = 0.4
TAIL_FRAMES = 90
BATCH = 16



def moving(points: list[tuple]) -> list[tuple]:
    """Without what stays put for STILL_FRAMES: a ball on the floor, a light, a spot on the wall."""
    need = STILL_FRAMES * 0.6
    kept = []
    for p in points:
        near = [q[0] for q in points if abs(q[0] - p[0]) <= STILL_FRAMES and q is not p and np.hypot(q[1] - p[1], q[2] - p[2]) < STILL_PX]
        long_before = any(p[0] - q >= need for q in near)
        long_after = any(q - p[0] >= need for q in near)
        if len(near) < need or not (long_before or long_after):
            kept.append(p)
    return kept


def chain(points: list[tuple]) -> list[tuple]:
    """The longest sequence of `points` (frame, x, y) a ball could have followed, smooth where it can be."""
    n = len(points)
    if not n:
        return []
    frames = np.array([p[0] for p in points])
    xy = np.array([p[1:3] for p in points], float)
    score, before, speed = np.ones(n), -np.ones(n, int), np.zeros((n, 2))
    for i in range(n):
        for j in range(np.searchsorted(frames, frames[i] - CHAIN_FRAMES), i):
            gap = frames[i] - frames[j]
            if gap <= 0:
                continue
            v = (xy[i] - xy[j]) / gap
            if np.hypot(*v) > (TELEPORT_PX if gap <= 25 else 60):
                continue
            kink = min(1.0, np.hypot(*(v - speed[j])) / 40) * (0.7 if before[j] >= 0 else 0)
            value = score[j] + 1 - kink - 0.02 * (gap - 1)
            if value > score[i]:
                score[i], before[i], speed[i] = value, j, v
    i, out = int(np.argmax(score)), []
    while i >= 0:
        out.append(i)
        i = before[i]
    return [points[k] for k in reversed(out)]


def chains(points: list[tuple], least: int = 6) -> list[list[tuple]]:
    """Every chain in time order: the longest, then those before and after it, for a rally with long holes."""
    run = chain(points)
    if len(run) < least:
        return []
    return [*chains([p for p in points if p[0] < run[0][0]], least), run, *chains([p for p in points if p[0] > run[-1][0]], least)]


def split(run: list[tuple]) -> list[list[tuple]]:
    """`run` cut where the ball's velocity changes at once. Gravity bends it slowly."""
    f = np.array([p[0] for p in run], float)
    xy = np.array([p[1:3] for p in run], float)
    change = np.zeros(len(run))
    for k in range(3, len(run) - 3):
        if f[k + 3] - f[k - 3] <= 12:
            change[k] = np.hypot(*((xy[k + 3] - xy[k]) / max(1, f[k + 3] - f[k]) - (xy[k] - xy[k - 3]) / max(1, f[k] - f[k - 3])))
    cuts: list[int] = []
    for k in np.argsort(-change):
        if change[k] > max(KINK_PX, 0.3 * np.hypot(*((xy[min(k + 3, len(run) - 1)] - xy[k]) / 3))) and all(abs(k - c) >= 4 for c in cuts):
            cuts.append(int(k))
    edges = [0, *sorted(cuts), len(run) - 1]
    parts = []
    for a, b in zip(edges, edges[1:]):
        begin = a
        for k in range(a, b):
            hole = f[k + 1] - f[k]
            # Across a long hole the same flight goes on; another one is a touch nothing saw.
            if hole > LOST_FRAMES and np.hypot(*((xy[k + 1] - xy[k]) / hole - (xy[k] - xy[max(k - 3, 0)]) / max(1, f[k] - f[max(k - 3, 0)]))) > KINK_PX:
                parts.append(run[begin : k + 1])
                begin = k + 1
        parts.append(run[begin : b + 1])
    return parts


def curve(part: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """Frames and places of a flight across its holes: its curve, staying on the detections where they fit, else straight between them."""
    f = np.array([p[0] for p in part], float)
    xy = np.array([p[1:3] for p in part], float)
    frames = np.arange(int(f[0]), int(f[-1]) + 1)
    straight = np.c_[np.interp(frames, f, xy[:, 0]), np.interp(frames, f, xy[:, 1])]
    if len(part) < 4:
        return frames, straight
    degree = 3 if np.ptp(f) > 30 and len(part) >= 12 else 2
    centre = f.mean()
    design = lambda q: np.vander((np.asarray(q, float) - centre) / 25.0, degree + 1)  # noqa: E731
    good = np.ones(len(f), bool)
    for _ in range(3):
        cx = np.linalg.lstsq(design(f[good]), xy[good, 0], rcond=None)[0]
        cy = np.linalg.lstsq(design(f[good]), xy[good, 1], rcond=None)[0]
        off = np.c_[xy[:, 0] - design(f) @ cx, xy[:, 1] - design(f) @ cy]
        now = np.hypot(*off.T) < INLIER_PX
        if now.sum() < 4:
            break
        good = now
    if good.mean() < 0.8:
        return frames, straight
    w = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    w /= w.sum()
    smooth = lambda v: np.convolve(np.pad(np.interp(frames, f[good], v[good]), 4, mode="edge"), w, "valid")  # noqa: E731
    return frames, np.c_[design(frames) @ cx + smooth(off[:, 0]), design(frames) @ cy + smooth(off[:, 1])]


def size_key(frame: int, x: float, y: float) -> str:
    return f"{frame}:{round(x)}:{round(y)}"


def too_small(part: list[tuple], sizes: dict[str, float], least: Callable[[float, float], float]) -> bool:
    """Whether this flight's ball is too small to be on our court."""
    read = [sizes[size_key(*p)] for p in part if size_key(*p) in sizes]
    if len(read) < SIZE_LEAST_POINTS:
        return False
    middle = part[len(part) // 2]
    return float(np.percentile(read, 80)) < SMALL_FLIGHT * least(middle[1], middle[2])


def small_flights(found: dict, also: dict | None, start: int, end: int, sizes: dict[str, float], least: Callable[[float, float], float]) -> list[list[tuple]]:
    """The flights among the detections too small to be on our court."""
    return [part for run in chains(moving(candidates(found, also, start, end))) for part in split(run) if too_small(part, sizes, least)]


def candidates(found: dict, also: dict | None, start: int, end: int, rejected: dict | None = None) -> list[tuple]:
    """The detections through [start, end] as (frame, x, y), both when they differ, without those `rejected`."""
    points = [(q, float(found[q][0]), float(found[q][1])) for q in range(start, end + 1) if q in found]
    for q in range(start, end + 1):
        if also and q in also and (q not in found or np.hypot(found[q][0] - also[q][0], found[q][1] - also[q][1]) > 3):
            points.append((q, float(also[q][0]), float(also[q][1])))
    if rejected:
        points = [p for p in points if not (p[0] in rejected and np.hypot(p[1] - rejected[p[0]][0], p[2] - rejected[p[0]][1]) < 15)]
    return sorted(points)


def rally_path(found: dict, marks: list[int], start: int, end: int, also: dict | None = None, rejected: dict | None = None) -> dict[int, tuple[float, float]]:
    """Frame -> the ball's place through [start, end] from the detections `found` and `also` but those `rejected`; after the last touch
    (`marks`) it ends at the landing, or where the ball is lost. A touch's own frame can be some frames off: the ball's motion makes the flights."""
    points = candidates(found, also, start, end, rejected)
    last_touch = max([m for m in marks if start < m < end], default=end)
    out: dict[int, tuple[float, float]] = {}
    was = None
    for part in (p for run in chains(moving(points)) for p in split(run)):
        frames, path = curve(part)
        if was is not None:
            gap = frames[0] - was[0]
            if frames[0] > last_touch:
                v0 = (was[1] - was[2]) / max(1, was[3])
                back = min(3, len(path) - 1)
                v1 = (path[back] - path[0]) / max(1, back)
                # The floor: going down, then up, still the same way across. A block turns it back instead.
                if gap > LOST_FRAMES or (was[0] > last_touch and v0[1] > 2 and v1[1] < -2 and v0[0] * v1[0] >= 0):
                    break
            if 1 < gap <= JOIN_FRAMES and np.hypot(*(path[0] - was[1])) / gap <= TELEPORT_PX:
                for q in range(was[0] + 1, int(frames[0])):
                    place = was[1] + (path[0] - was[1]) * ((q - was[0]) / gap)
                    out[q] = (float(place[0]), float(place[1]))
        for q, p in zip(frames, path):
            # A curve's end past the picture is no ball.
            if -200 < p[0] < SOURCE_W + 200 and -400 < p[1] < SOURCE_H + 200:
                out[int(q)] = (float(p[0]), float(p[1]))
        back = min(3, len(path) - 1)
        was = (int(frames[-1]), path[-1], path[-1 - back], back)
    return out


def projector(cal: Calibration) -> Callable[[float, float, float], np.ndarray]:
    """(x, y, h) on the court, in metres, to the picture: the court's homography and the lens give the camera."""
    k = np.array(cal.lens["K"], float)
    inverse = np.linalg.inv(k)
    h = cal.homography
    r1, r2 = inverse @ h[:, 0], inverse @ h[:, 1]
    up = k @ np.cross(r1 / np.linalg.norm(r1), r2 / np.linalg.norm(r2)) * (np.linalg.norm(r1) + np.linalg.norm(r2)) / 2

    def project(x: float, y: float, height: float, sign: float = 1.0) -> np.ndarray:
        p = h @ np.array([x, y, 1.0]) + sign * height * up
        return distort((p[:2] / p[2])[None], cal.lens)[0]

    sign = 1.0 if project(0, 0, 2)[1] < project(0, 0, 0)[1] else -1.0
    return lambda x, y, height: project(x, y, height, sign)


def least_sizes(cal: Calibration) -> Callable[[float, float], float]:
    """Point of the picture -> the smallest a ball can look there while on our court, in pixels: along the ray through it, inside the
    volume it plays in, as far from the camera as it gets. From a grid of the picture."""
    k = np.array(cal.lens["K"], float)
    inverse = np.linalg.inv(k)
    h1, h2, h3 = (inverse @ cal.homography[:, c] for c in range(3))
    scale = (np.linalg.norm(h1) + np.linalg.norm(h2)) / 2
    r1, r2, t = h1 / scale, h2 / scale, h3 / scale
    r3 = np.cross(r1, r2)
    camera = -np.c_[r1, r2, r3].T @ t
    if camera[2] < 0:
        r3 = -r3
        camera = -np.c_[r1, r2, r3].T @ t
    rotation = np.c_[r1, r2, r3]

    def project(points: np.ndarray) -> np.ndarray:
        p = (k @ (rotation @ points.T + t[:, None])).T
        return distort(p[:, :2] / p[:, 2:], cal.lens)

    xs, ys = np.arange(0, SOURCE_W + 1, 120), np.arange(0, SOURCE_H + 1, 120)
    grid = np.zeros((len(ys), len(xs)))
    distances = np.linspace(1, 60, 120)[:, None]
    for j, y in enumerate(ys):
        pinhole = undistort(np.c_[xs, np.full(len(xs), y)].astype(float), cal.lens)
        for i, u in enumerate(pinhole):
            ray = rotation.T @ (inverse @ np.array([u[0], u[1], 1.0]))
            ray /= np.linalg.norm(ray)
            side = np.cross(ray, [0, 0, 1.0])
            side /= np.linalg.norm(side)
            points = camera + distances * ray
            inside = points[(np.abs(points[:, 0]) <= VOLUME_X) & (np.abs(points[:, 1]) <= VOLUME_Y) & (points[:, 2] >= 0) & (points[:, 2] <= VOLUME_H)]
            if len(inside):
                grid[j, i] = np.hypot(*(project(inside + side * BALL_M / 2) - project(inside - side * BALL_M / 2)).T).min()

    def least(x: float, y: float) -> float:
        return float(grid[int(np.clip(round(y / 120), 0, len(ys) - 1)), int(np.clip(round(x / 120), 0, len(xs) - 1))])

    return least


def ball_size(before: np.ndarray, picture: np.ndarray, after: np.ndarray, x: float, y: float) -> float | None:
    """The narrow side of what is at (x, y) in `picture` alone, in pixels: its length is the ball's blur."""
    reach = 70
    x0, y0 = int(max(0, x - reach)), int(max(0, y - reach))
    x1, y1 = int(x + reach), int(y + reach)
    if x1 <= x0 or y1 <= y0:
        return None
    crops = [cv2.cvtColor(p[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.int16) for p in (before, picture, after)]
    if not crops[1].size:
        return None
    changed = np.minimum(np.abs(crops[1] - crops[0]), np.abs(crops[1] - crops[2])).astype(np.uint8)
    mask = cv2.morphologyEx((changed > 16).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, centres = cv2.connectedComponentsWithStats(mask)
    best, nearest = None, 40.0
    for k in range(1, count):
        d = np.hypot(centres[k][0] + x0 - x, centres[k][1] + y0 - y)
        if d < nearest and stats[k, cv2.CC_STAT_AREA] >= 12:
            best, nearest = k, d
    if best is None:
        return None
    return float(min(cv2.minAreaRect(np.argwhere(labels == best)[:, ::-1].astype(np.float32))[1]))


def frame_times(match: Path, video: Path) -> np.ndarray:
    """Each frame's real time: a video's rate need not be even, and a time made from a frame's number then drifts."""
    path = match / TIMES_CACHE
    if path.exists():
        return np.load(path)
    done = decode.probe(video, "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", check=True)
    times = np.sort(np.array([float(line.split(",")[0]) for line in done.splitlines() if line.strip()]))
    np.save(path, times)
    return times


def decoder(video: Path, times: np.ndarray, frame: int, count: int) -> subprocess.Popen:
    """The video's frames from `frame`, exactly, as raw pictures: decoded on the GPU when ffmpeg can, through yuv420p for
    the CPU's pixels (decode.piped). Three films at once on the Avia match: 125 s against 133, the reading 1.6x faster (the
    drawing takes the rest)."""
    flags = decode.hardware(video)
    return subprocess.Popen(
        ["ffmpeg", "-v", "quiet", *flags, "-ss", f"{times[frame] - 0.004:.4f}", "-i", str(video), "-frames:v", str(count), "-an", *(("-vf", "format=yuv420p") if flags else ()), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE,
    )




def read_picture(process: subprocess.Popen) -> np.ndarray | None:
    size = SOURCE_W * SOURCE_H * 3
    raw = process.stdout.read(size)
    return np.frombuffer(raw, np.uint8).reshape(SOURCE_H, SOURCE_W, 3) if len(raw) == size else None


def closed(process: subprocess.Popen) -> None:
    process.stdout.close()
    process.terminate()
    process.wait()




def search_ball(match: Path, video: Path, court: Path, shown: list[tuple[int, float, float]], page: dict, share: jobs.Share = jobs.quiet) -> dict:
    """The ball searched again around where the first pass puts it, in the frames `shown` (rally, from and to in the match's
    time: what the films show) that no search has seen. Kept."""
    import torch

    path = match / BALL_CACHE
    cache = files.read_json(path, {"seen": [], "found": {}})
    seen = {int(q) for q in cache["seen"]}
    found = {int(q): tuple(v) for q, v in cache["found"].items()}
    sizes: dict[str, float] = cache.get("sizes", {})
    sized = {int(q) for q in cache.get("sized", [])}
    rejected = {int(q): tuple(v) for q, v in cache.get("rejected", {}).items()}
    least = least_sizes(Calibration.load(court).with_lens((SOURCE_W, SOURCE_H)))
    detected = tables.seen(match / "ball.csv")
    times = frame_times(match, video)
    marks_of = marks(page)
    wanted: dict[int, set[int]] = {}
    for rally, a, b in shown:
        wanted.setdefault(rally, set()).update(range(round((a - WINDOW_PAD_S) * FPS), round((b + WINDOW_PAD_S) * FPS) + 1))
    device = tracker.default_device()
    model = tracker.load_model(device)

    @torch.no_grad()
    def look(jobs: list[tuple], crop: tuple[int, int], avoid: Callable[[int], tuple | None] = lambda _: None) -> list[tuple | None]:
        """The best place of each job (three frames, a centre, a frame) in a crop around its centre, away from `avoid`'s for its frame."""
        out = []
        w, h = crop
        for at in range(0, len(jobs), BATCH):
            part = jobs[at : at + BATCH]
            corners = [(int(np.clip(job[1][0] - w / 2, 0, SOURCE_W - w)), int(np.clip(job[1][1] - h / 2, 0, SOURCE_H - h))) for job in part]
            inputs = np.stack([np.concatenate([tracker.preprocess(p[y : y + h, x : x + w]) for p in job[0]]) for job, (x, y) in zip(part, corners)])
            maps = model(torch.from_numpy(inputs).to(device))[0].sigmoid().cpu().numpy()
            for heat, (x, y), job in zip(maps, corners, part):
                middle = heat[1].copy()
                spot = avoid(job[2]) if len(job) > 2 else None
                if spot:
                    cv2.circle(middle, (round((spot[0] - x) * tracker.WIDTH / w), round((spot[1] - y) * tracker.HEIGHT / h)), max(3, round(50 * tracker.WIDTH / w)), 0, -1)
                blob = tracker.best_blob(middle)
                out.append((round(x + blob[0] * w / tracker.WIDTH, 1), round(y + blob[1] * h / tracker.HEIGHT, 1), round(blob[2], 3)) if blob and blob[2] >= tracker.THRESHOLD[1] else None)
        return out

    def sweep(frames: list[int], centre: Callable[[int], tuple[float, float]], avoid: Callable[[int], tuple | None] = lambda _: None) -> None:
        """Searches `frames`, around `centre`, in the sharper crop where the wider one misses or doubts."""
        asked = set(frames)
        for a, b in ranges(frames):
            process = decoder(video, times, a - 1, b - a + 3)
            rolling, pending = [], []
            current = a - 2

            def flush() -> None:
                results = look([(pictures, centre(q), q) for q, pictures in pending], CROPS[0], avoid)
                sharper = [(k, q, pictures) for k, ((q, pictures), hit) in enumerate(zip(pending, results)) if hit is None]
                for (k, _, _), hit in zip(sharper, look([(pictures, centre(q), q) for _, q, pictures in sharper], CROPS[1], avoid)):
                    results[k] = hit
                for (q, _), hit in zip(pending, results):
                    if hit:
                        found[q] = hit
                    elif avoid(q):
                        found.pop(q, None)
                pending.clear()

            while current < b + 1:
                picture = read_picture(process)
                if picture is None:
                    break
                current += 1
                rolling = [*rolling[-2:], picture]
                if len(rolling) == 3 and current - 1 in asked:
                    pending.append((current - 1, list(rolling)))
                    if len(pending) == BATCH:
                        flush()
            if pending:
                flush()
            closed(process)

    @torch.no_grad()
    def follow(k: int, frames: list[int], last: int) -> None:
        """The ball after a rally's last touch, followed forward from it."""
        known = sorted(q for q in {**detected, **found} if last - 8 <= q <= last)
        if not known or not frames:
            return
        merged = {**detected, **found}
        place, at, velocity = np.array(merged[known[-1]][:2], float), known[-1], np.zeros(2)
        process = decoder(video, times, last - 1, frames[-1] - last + 3)
        rolling, current = [], last - 2
        while current < frames[-1] + 1:
            picture = read_picture(process)
            if picture is None:
                break
            current += 1
            rolling = [*rolling[-2:], picture]
            if len(rolling) < 3 or current - 1 <= last:
                continue
            q = current - 1
            expected = np.clip(place + velocity * (q - at), 0, [SOURCE_W, SOURCE_H])
            best = None
            for crop in TAIL_CROPS:
                hit = look([(rolling, expected)], crop)[0]
                if hit:
                    score = hit[2] / (1 + np.hypot(hit[0] - expected[0], hit[1] - expected[1]) / 300)
                    if best is None or score > best[0]:
                        best = (score, hit)
            if best:
                spot = np.array(best[1][:2])
                # Right after the touch it can be anywhere: the touch changed its way.
                if q - last < 6 or np.hypot(*(spot - expected)) < 260:
                    if q - at <= 6:
                        velocity = 0.5 * velocity + 0.5 * (spot - place) / (q - at)
                    place, at = spot, q
                    if q not in detected:
                        found[q] = best[1]
        closed(process)

    def measure(frames: list[int]) -> None:
        """The size of every detection at `frames`."""
        for a, b in ranges(frames):
            process = decoder(video, times, a - SIZE_GAP - 1, b - a + 2 * SIZE_GAP + 3)
            pictures: dict[int, np.ndarray] = {}
            current = a - SIZE_GAP - 2
            while current < b + SIZE_GAP:
                picture = read_picture(process)
                if picture is None:
                    break
                current += 1
                pictures[current] = picture
                q = current - SIZE_GAP
                if q >= a and q - SIZE_GAP in pictures:
                    for place in (found.get(q), detected.get(q)):
                        if place:
                            size = ball_size(pictures[q - SIZE_GAP], pictures[q], picture, place[0], place[1])
                            if size is not None:
                                sizes[size_key(q, place[0], place[1])] = round(size, 1)
                    sized.add(q)
                pictures.pop(current - 2 * SIZE_GAP - 1, None)
            closed(process)

    def save() -> None:
        files.write_text(path, json.dumps({"seen": sorted(seen), "found": {str(q): v for q, v in found.items()}, "sizes": sizes, "sized": sorted(sized), "rejected": {str(q): v for q, v in rejected.items()}}, separators=(",", ":")))

    # The share done: the frames not searched yet, rally after rally.
    total, searched = max(sum(len(f - seen) for f in wanted.values()), 1), 0
    for k, frames in sorted(wanted.items()):
        new = sorted(frames - seen)
        share(searched / total)
        searched += len(new)
        rally_marks = marks_of[k]
        if not new:
            if frames <= sized:
                continue
        last = max(rally_marks)
        inside = [q for q in new if q <= last]
        if inside:
            wide = rally_path({}, rally_marks, min(rally_marks) - 30, last + 10, detected)
            sweep(inside, centre_of(wide, detected))
            missing = [q for q in inside if q not in found]
            if missing:
                sweep(missing, centre_of(rally_path(found, rally_marks, min(rally_marks) - 30, last + 10, detected), detected))
        follow(k, [q for q in new if q > last], last)
        seen.update(new)
        # What is too small is another court's ball: dropped, its frames searched again away from it for the real one.
        start, end = min(rally_marks) - 30, last + TAIL_FRAMES
        measure(sorted(frames - sized))
        for part in small_flights(found, detected, start, end, sizes, least):
            rejected.update({p[0]: (p[1], p[2]) for p in part})
        wrong = sorted(q for q in rejected if q in frames and q <= last)
        if wrong:
            sweep(wrong, centre_of(rally_path(found, rally_marks, start, end, detected, rejected), detected), rejected.get)
            for q in wrong:
                sized.discard(q)
            measure(wrong)
        save()
    return found


def ranges(frames: list[int]) -> list[tuple[int, int]]:
    """`frames`, sorted, as ranges, those under 6 frames apart joined: the video is read through them anyway."""
    out: list[list[int]] = []
    for q in frames:
        if out and q - out[-1][1] <= 6:
            out[-1][1] = q
        else:
            out.append([q, q])
    return [(a, b) for a, b in out]


def centre_of(path: dict, detected: dict) -> Callable[[int], tuple[float, float]]:
    """Where to look at a frame: on the path, else between the places around it."""
    known = sorted(path) or sorted(detected)
    xs, ys = np.array([path.get(q, detected.get(q))[0] for q in known]), np.array([path.get(q, detected.get(q))[1] for q in known])
    return lambda q: (float(np.interp(q, known, xs)), float(np.interp(q, known, ys)))


def marks(page: dict) -> dict[int, list[int]]:
    """Each rally's contacts' frames."""
    out: dict[int, list[int]] = {}
    for c in page["contacts"]:
        out.setdefault(c["rally"], []).append(int(c.get("f", round(c["t"] * FPS))))
    return out


def film_path(page: dict, film: dict, detected: dict, found: dict, places: dict[int, list[float]], cal: Calibration, rejected: dict | None = None) -> dict[int, tuple[float, float]]:
    """Frame -> the ball's place through a film's rallies, across the holes; up to a touch's 3D place for a fast ball nothing sees."""
    project = projector(cal)
    out: dict[int, tuple[float, float]] = {}
    marks_of = marks(page)
    for k in {s["rally"] for s in film["shots"]}:
        m = marks_of[k]
        path = rally_path(found, m, min(m) - 30, max(m) + TAIL_FRAMES, detected, rejected)
        for c in page["rallies"][k]["contacts"]:
            frame = int(c.get("f", round(c["t"] * FPS)))
            before = max((q for q in path if q < frame), default=None)
            if c["type"] == "floor" or c["i"] not in places or before is None or not 2 <= frame - before <= 45:
                continue
            a, b = np.array(path[before]), project(*places[c["i"]])
            for q in range(before + 1, frame + 1):
                if q not in path:
                    place = a + (b - a) * ((q - before) / (frame - before))
                    path[q] = (float(place[0]), float(place[1]))
        out.update(path)
    return out
