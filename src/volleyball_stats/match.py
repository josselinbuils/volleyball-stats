"""Run the whole pipeline on a match video and write a first report.

    uv run python -m volleyball_stats.match VIDEO (--court CALIBRATION_JSON | --net-x PX) [--players [--teams "NAME_1[:COLOUR],NAME_2[:COLOUR]"] [--date YYYY-MM-DD] [--title TITLE] [--sets M:SS,...] [--scores 25-21,...] [--squad N[,N]]] [--force]

Each step writes its output to outputs/matches/<video>/; the ball and player tracks, the slow steps, are
reused when they exist unless --force. With the players, teams.json holds the teams' names, colours,
the match's date and title, the set starts and the sets' final scores: written on the first run
(asked on a terminal), edited by hand if need be, reused on the next runs unless the flags override
them. The players also give each rally's winner and the score (points.csv) and one identity per
player for the whole match (identities.csv, identity.py). Last, the review's page and its pictures,
for its first open to be quick (--no-page to leave them to the review).
"""

import argparse
import csv
import os
import queue
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime
from itertools import repeat, tee
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import actions, attribution, ball, ball3d, contacts, court, decode, files, identity, jerseys, jumps, players, playing, points, rallies, ranker, scoreboard, teams, timeouts

TYPES = ["serve", "pass", "set", "attack", "relance", "block", "dig", "floor", "net"]
# Balls under the line SPARE_Y meters toward the camera (1 m past the near sideline) are spare ones,
# bounced or held off the court.
SPARE_Y = 5.5
# Seconds from a window's start within which a serve the players' positions show is its serve
# (`unseen_serves`): 0.4-1.0 s after the contact on the first ASPOM match.
UNSEEN_SERVE_S = 1.0
# Tracking is refused above this load per core: other work slowed the second match's run 2.6 times.
BUSY_LOAD = 0.5
# The line starting each step's output: a caller reading it (the review's progress) knows which runs.
STAGE = "::stage "
# The line telling how much of the tracking is done (0-1), every PROGRESS_EVERY frames.
PROGRESS, PROGRESS_EVERY = "::progress ", 500


# Frames a step may run ahead of the other (`side_by_side`): over the ball's lag (ball.BATCH * stride + WINDOW frames).
AHEAD = 64
_END = object()


class _Failed:
    def __init__(self, error: BaseException):
        self.error = error


def side_by_side(frames: Iterator, steps: list[Callable[[Iterator], Iterator]]) -> Iterator[tuple]:
    """Each step's result per frame, together: every step reads every frame and yields one result per frame, each but
    the first in a thread of its own, so that one model runs while the other's Python prepares its next frame (one
    thread ran them in turn on the RTX 5080: a core at 100%, the card half idle; `benchmarks/speed.py`). The results
    are those the steps give one after the other. A step's error is raised here; stopping early stops them all."""
    feeds = [queue.Queue(AHEAD) for _ in steps]
    outs = [queue.Queue(AHEAD) for _ in steps[1:]]
    stop = threading.Event()

    def put(q: queue.Queue, item) -> bool:
        while not stop.is_set():
            try:
                q.put(item, timeout=0.2)
                return True
            except queue.Full:
                pass
        return False

    def take(q: queue.Queue):
        while not stop.is_set():
            try:
                item = q.get(timeout=0.2)
            except queue.Empty:
                continue
            if isinstance(item, _Failed):
                raise item.error
            return item
        return _END

    def read(q: queue.Queue) -> Iterator:
        while (item := take(q)) is not _END:
            yield item

    def feed() -> None:
        try:
            for frame in frames:
                if not all(put(q, frame) for q in feeds):
                    return
            for q in feeds:
                put(q, _END)
        except BaseException as error:  # noqa: BLE001
            for q in feeds:
                put(q, _Failed(error))
        finally:
            # In this thread: ends a decoder stopped early (ffmpeg).
            getattr(frames, "close", lambda: None)()

    def run(step: Callable[[Iterator], Iterator], source: queue.Queue, out: queue.Queue) -> None:
        try:
            for result in step(read(source)):
                if not put(out, result):
                    return
            put(out, _END)
        except BaseException as error:  # noqa: BLE001
            put(out, _Failed(error))

    threads = [threading.Thread(target=feed, daemon=True)]
    threads += [threading.Thread(target=run, args=(step, source, out), daemon=True) for step, source, out in zip(steps[1:], feeds[1:], outs)]
    for thread in threads:
        thread.start()
    try:
        for first in steps[0](read(feeds[0])):
            others = [take(out) for out in outs]
            if any(o is _END for o in others):
                raise RuntimeError("a step gave fewer results than frames")
            yield (first, *others)
        if any(take(out) is not _END for out in outs):
            raise RuntimeError("a step gave more results than frames")
    finally:
        stop.set()


def tracked(video: Path, calibration: court.Calibration | None, with_ball: bool, with_players: bool, fps: float) -> Iterator[tuple[ball.Position, list[players.Row]]]:
    """Per frame, the ball's position (None when not found or not tracked) and the players' rows
    (none when not tracked), from one decoding pass of the video at `fps`; `with_ball` or
    `with_players`, both side by side."""
    device, native = ball.default_device(), decode.size(video)
    balls = lambda frames: (p for _, p in ball.track_frames(frames, ball.load_model(device), device, size=native))  # noqa: E731
    found = lambda frames: players.track_frames(frames, calibration, players.load_model(), device, size=native, fps=fps)  # noqa: E731
    if with_ball and with_players and device == "cuda":
        # The players first, in this thread: they yield frame by frame, the ball in batches.
        return ((b, p) for p, b in side_by_side(decode.frames(video), [found, balls]))
    # Metal (MPS) aborts when two threads run models at once: one thread, both models in turn.
    branches = iter(tee(decode.frames(video), with_ball + with_players))
    return zip(balls(next(branches)) if with_ball else repeat(None), found(next(branches)) if with_players else repeat([]))


def track(video: Path, calibration: court.Calibration | None, fps: float, ball_path: Path | None, players_path: Path | None, frame_count: int = 0) -> None:
    """The ball track into `ball_path` and the players' into `players_path`, either None to skip it; the share of the
    `frame_count` frames done on PROGRESS lines, for the app."""
    positions, rows = [], []
    for index, (position, frame_rows) in enumerate(tracked(video, calibration, ball_path is not None, players_path is not None, fps)):
        positions.append([index, int(position is not None), *(position or ("", ""))])
        rows += frame_rows
        if frame_count and index % PROGRESS_EVERY == 0:
            print(f"{PROGRESS}{min(1.0, index / frame_count):.4f}", flush=True)
    if ball_path:
        write_csv(ball_path, ["frame", "visible", "x", "y"], positions)
    if players_path:
        players.write_csv(players.finish(rows, fps), players_path)


def rally_windows(
    track: np.ndarray, whistle_times: list[tuple[float, float]], fps: float, net_x: float, calibration: court.Calibration | None = None, positions: list[tuple[int, float, float]] | None = None
) -> tuple[list[rallies.Rally], list[contacts.Contact], list[int]]:
    """The rally windows, ball contacts and net crossings of a ball track (NaN where not visible):
    spare balls masked, pixel constants at the court's scale, the serves the players' positions
    (frame, court x, court y) show added, the windows opening on a contact inside the court
    dropped, then the serves after the referee's go (`rallies.whistled`) where no window is near;
    each window opening after its serve contact moved to it, then those the ball's absence ended carried on
    (`rallies.carried_on`). The benchmarks score this."""
    track, scale = track.copy(), 1.0
    if calibration is not None:
        track[calibration.in_front(track, SPARE_Y)] = np.nan
        scale = rallies.court_scale(calibration)
    windows = rallies.segment(track, whistle_times, fps, scale)
    gap = round(rallies.SAME_SERVE_S * fps)
    if positions is not None:
        windows = rallies.with_serves(windows, rallies.served(positions, track, whistle_times, fps, calibration), round(rallies.SERVE_LEAD_S * fps), gap)
    found, crossings = contacts.detect(track, fps, net_x, scale, (lambda x, y: actions.on_floor(calibration, x, y, True)) if calibration is not None else None)
    windows = actions.served(windows, found, fps, calibration)
    if positions is not None:
        alone = rallies.alone(windows, rallies.whistled(track, whistle_times, fps, calibration), gap)
        windows = sorted(windows + actions.served(alone, found, fps, calibration))
    windows = actions.serve_starts(windows, found, crossings, fps, net_x, calibration, scale)
    if calibration is not None:
        windows = actions.late_serves(windows, found, crossings, whistle_times, fps, net_x, calibration)
    windows = rallies.carried_on(windows, [c[0] for c in found], whistle_times, fps, round(actions.LEAD_S * fps))
    return windows, found, crossings


def typed_windows(
    windows: list[rallies.Rally], found: list[contacts.Contact], crossings: list[int], fps: float, net_x: float, calibration: court.Calibration | None, rows: list[players.Row] | None,
    track: np.ndarray, whistle_times: list[tuple[float, float]], alive: Callable[[int], bool] | None = None,
) -> tuple[list[rallies.Rally], list[actions.Typed]]:
    """The windows' contacts typed; with the players' `rows`, the touches no player reaches dropped and the serves the ball
    track missed added (`unseen_serves`) and the blocks away from the net dropped (`actions.off_net_blocks`)."""
    typed = actions.classify(found, crossings, windows, fps, net_x, calibration, alive)
    if rows is None:
        return windows, typed
    # Touches with no player at the ball are none; the rest typed again without them.
    far = attribution.unreached(typed, rows, fps, crossings)
    found = [c for c in found if c[0] not in far]
    typed = actions.classify(found, crossings, windows, fps, net_x, calibration, alive)
    track = track.copy()
    track[calibration.in_front(track, SPARE_Y)] = np.nan
    windows, added = unseen_serves(windows, typed, crossings, rallies.served([(r.frame, *r.court) for r in rows], track, whistle_times, fps, calibration), rows, fps)
    if added:
        typed = actions.classify(sorted(found + added), crossings, windows, fps, net_x, calibration, alive)
    return windows, actions.off_net_blocks(typed, calibration)


def unseen_serves(
    windows: list[rallies.Rally], typed: list[actions.Typed], crossings: list[int], serves: list[tuple[int, int, int]], rows: list[players.Row], fps: float
) -> tuple[list[rallies.Rally], list[contacts.Contact]]:
    """The serves the ball track missed: in each window with no serve typed, a serve `rallies.served`
    saw within UNSEEN_SERVE_S of its start (side -1 from the left end) is a contact at the top of the
    box of the player standing deepest behind that end line, before the window's first contact and
    crossing; the windows start early enough to hold them."""
    lead, near = round(actions.LEAD_S * fps), round(UNSEEN_SERVE_S * fps)
    served = {t[0] for t in typed if t[3] == "serve"}
    wanted = {}
    for k, (start, end) in enumerate(windows):
        if any(start - lead <= f <= end for f in served):
            continue
        found = [(abs(f - start), f, side) for f, _, side in serves if abs(f - start) <= near]
        if found:
            _, f, side = min(found)
            first = min([f, *(c - 1 for c in crossings if start - lead <= c <= end), *(t[0] - 1 for t in typed if start - lead <= t[0] <= end)])
            wanted[k] = (first, side)
    boxes: dict[int, list[players.Row]] = {}
    frames = {f for f, _ in wanted.values()}
    for r in rows:
        if r.frame in frames:
            boxes.setdefault(r.frame, []).append(r)
    out, added = list(windows), []
    for k, (f, side) in wanted.items():
        behind = [r for r in boxes.get(f, []) if rallies.SERVER_X < side * r.court[0] < rallies.SERVER_MAX_X and abs(r.court[1]) < rallies.HALF_WIDTH]
        if behind:
            box = max(behind, key=lambda r: side * r.court[0]).box
            added.append((f, round((box[0] + box[2]) / 2), round(box[1])))
            out[k] = (min(out[k][0], f + lead), out[k][1])
    return out, added


def stage(name: str) -> None:
    print(f"{STAGE}{name}", flush=True)


def in_rallies(frames: list[int], windows: list[tuple[int, int]], lead: int) -> list[int]:
    """Frames inside a rally window started `lead` frames early, like actions.classify's."""
    return [f for f in frames if any(start - lead <= f <= end for start, end in windows)]


def write_csv(path: Path, header: list[str], rows: list) -> None:
    with files.replacing(path, newline="") as f:
        csv.writer(f).writerows([header, *rows])


def rally_of(frame: int, windows: list[tuple[int, int]], lead: int) -> int | None:
    """Index of the rally window, started `lead` frames early, holding `frame`."""
    return next((k for k, (start, end) in enumerate(windows) if start - lead <= frame <= end), None)


def table(typed: list[actions.Typed], groups: list, names: dict) -> list[str]:
    """Markdown table of the actions per group (team or side), `groups` holding each contact's."""
    counts = Counter((t[3], g) for t, g in zip(typed, groups))
    return [
        "| Action | " + " | ".join(names.values()) + " |",
        "| --- |" + " --- |" * len(names),
        *(f"| {kind} | " + " | ".join(str(counts[kind, g]) for g in names) + " |" for kind in TYPES),
    ]


def report(
    video: Path,
    fps: float,
    frame_count: int,
    windows: list[tuple[int, int]],
    typed: list[actions.Typed],
    crossings: list[int],
    timings: dict[str, float],
    tracks: dict[str, int] | None = None,
    names: list[str] | None = None,
    contact_teams: list[int | None] | None = None,
    sets: list[int] | None = None,
    day: str | None = None,
    title: str | None = None,
) -> str:
    """The match summary. With `names` (team 1, team 2) and each contact's team the actions are split
    by team, otherwise by side of the net; `sets` (each rally's) adds a section per set when the
    match has more than one. With `names` the heading is the match's `title`, by default "Match
    <team 1> vs <team 2>" with the table's names, and its date (yyyy-mm-dd `day`); else the video's
    name."""
    lengths = np.array([(end - start) / fps for start, end in windows])
    duration = frame_count / fps
    if names and contact_teams is not None:
        groups, labels = contact_teams, {1: names[0], 2: names[1]}
    else:
        groups, labels = [t[4] for t in typed], {"left": "Left of the net", "right": "Right of the net"}
    heading = video.stem
    if names:
        heading = title or teams.default_title(names)
        if day:
            date = datetime.strptime(day, "%Y-%m-%d")
            heading += f" · {date.day} {date:%B %Y}"
    lines = [
        f"# {heading}",
        "",
        f"- Duration: {duration / 60:.1f} min",
        f"- Rallies: {len(windows)}, ball in play {lengths.sum() / 60:.1f} min ({lengths.sum() / duration:.0%})"
        + (f", median rally {np.median(lengths):.1f} s" if len(windows) else ""),
        f"- Contacts in rallies: {len(typed)}" + (f", {len(typed) / len(windows):.1f} per rally" if windows else ""),
        f"- Net crossings in rallies: {len(crossings)}",
        *([f"- Player tracks: " + ", ".join(f"{n} {label}" for label, n in tracks.items())] if tracks is not None else []),
        *([f"- Sets: {max(sets)}"] if sets and max(sets) > 1 else []),
        "",
        *table(typed, groups, labels),
        *([] if names else ["", "Teams need the player tracks (--players): actions are split by side of the net."]),
    ]
    if sets and max(sets) > 1:
        lead = round(actions.LEAD_S * fps)
        contact_sets = [sets[k] if (k := rally_of(t[0], windows, lead)) is not None else None for t in typed]
        for number in range(1, max(sets) + 1):
            inside = [k for k, c in enumerate(contact_sets) if c == number]
            rallies = sum(s == number for s in sets)
            lines += ["", f"## Set {number}", "", f"- Rallies: {rallies}, contacts: {len(inside)}", ""]
            lines += table([typed[k] for k in inside], [groups[k] for k in inside], labels)
    lines += ["", "Processing time: " + ", ".join(f"{step} {seconds / 60:.1f} min" for step, seconds in timings.items())]
    return "\n".join(lines) + "\n"


def slow_run_reasons(nice: int, load: float, cores: int) -> list[str]:
    """Why tracking, hours long, would crawl on this machine."""
    reasons = []
    if nice > 0:
        reasons.append(f"Low priority (nice {nice}): in zsh, `setopt no_bg_nice` before starting in the background.")
    if load > BUSY_LOAD * cores:
        reasons.append(f"Busy machine: load {load:.1f} on {cores} cores.")
    return reasons


def busiest(count: int = 5) -> list[str]:
    """The processes using the most CPU, as "12.3% name"."""
    lines = subprocess.run(["ps", "-Ao", "pcpu=,comm="], capture_output=True, text=True).stdout.splitlines()
    rows = [line.split(None, 1) for line in lines if len(line.split(None, 1)) == 2]
    return [f"{cpu}% {Path(name).name}" for cpu, name in sorted(rows, key=lambda r: -float(r[0].replace(",", ".")))[:count]]


def review_page(out: Path, video: Path, court: Path) -> None:
    """The review's page and its pictures made ahead, for its first open to be quick; the run stands without them."""
    from volleyball_stats import web

    try:
        web.review_page(out, video, court)
    except Exception as error:  # noqa: BLE001
        print(f"The review will make its page when opened: {error}", file=sys.stderr)


def read_jerseys(out: Path, video: Path) -> None:
    """jerseys.csv of the match on footage sharp enough for them, kept for the next runs."""
    if not (out / jerseys.FILE).exists() and decode.size(video)[1] >= jerseys.MIN_HEIGHT:
        jerseys.write(out / jerseys.FILE, jerseys.read(out, video))


def settled_teams(assign: Callable[[list[float] | None], teams.Teams], settle: Callable[[teams.Teams], dict], starts: list[float] | None) -> tuple[teams.Teams, dict]:
    """The teams and what `settle` saves: when that gives other set starts than the `starts` known
    before (typed, or saved during the run), the sides are found again with them."""
    found = assign(starts)
    settled = settle(found)
    given = [teams.seconds(s) for s in settled["sets"]]
    if given == starts:
        return found, settled
    found = assign(given)
    return found, settle(found)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline on a match video.")
    parser.add_argument("video", type=Path)
    net = parser.add_mutually_exclusive_group(required=True)
    net.add_argument("--court", type=Path, help="Court calibration JSON (court.py fit or auto)")
    net.add_argument("--net-x", type=float, help="Net position in frame pixels, without a calibration (no floor contacts)")
    parser.add_argument("--out", type=Path, default=Path("outputs/matches"))
    parser.add_argument("--players", action="store_true", help="Also track the players (about 2.5x the ball's time) and tell the teams apart")
    parser.add_argument(
        "--teams",
        help='Team names and optional jersey colours, "NAME_1[:COLOUR],NAME_2[:COLOUR]": the first is the team on the LEFT of the camera '
        "at the first rally; COLOUR is #rrggbb or a name (white, navy, rouge...). Default: the names in teams.json, else asked "
        "on a terminal, else Team 1 and Team 2 with the detected colours",
    )
    parser.add_argument("--date", help="The match's date, YYYY-MM-DD. Default: the one in teams.json, else asked on a terminal, else the video's recording date")
    parser.add_argument(
        "--title",
        help="The match's title. Default: the one in teams.json, else asked on a terminal, else \"Match NAME_1 vs NAME_2\" in the page's language (\"\" for it)",
    )
    parser.add_argument(
        "--sets",
        help="Set starts in the video, M:SS or H:MM:SS, comma separated, the first set 1's (rallies before it, the warm-up, are left out). "
        "Default: the ones in teams.json, else asked on a terminal, else detected from the changes of ends",
    )
    parser.add_argument("--scores", help="Final score of each set, team 1 first, comma separated (25-21,23-25), empty for an unknown one. Default: the ones in teams.json, else asked on a terminal")
    parser.add_argument("--squad", type=identity.parse_squad, help="Players per team, N or N1,N2, when known: the identities to find")
    parser.add_argument("--force", action="store_true", help="Track the ball and players again even if tracks exist")
    parser.add_argument("--anyway", action="store_true", help="Track even at a low priority or on a busy machine")
    parser.add_argument("--no-page", action="store_true", help="Leave the review's page to the review")
    args = parser.parse_args()
    day = teams.parse_date(args.date) if args.date else None
    if args.date and day is None:
        parser.error(f"Not a date: {args.date!r} (use YYYY-MM-DD)")
    if not args.players and (args.teams or args.date or args.title is not None or args.sets or args.scores or args.squad):
        parser.error("--teams, --date, --title, --sets, --scores and --squad need --players")

    out = args.out / args.video.stem
    out.mkdir(parents=True, exist_ok=True)
    if args.players and args.court:
        files.write_source(out, args.video, args.court, args.squad)
    sets = args.sets and args.sets.split(",")
    try:
        starts = teams.known_starts(out / "teams.json", sets)
    except ValueError:
        parser.error(f"Not set starts: {args.sets or out / 'teams.json'} (use m:ss or h:mm:ss, e.g. 0:00,24:10)")
    cap = cv2.VideoCapture(str(args.video))
    fps, frame_count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    calibration = court.Calibration.load(args.court) if args.court else None
    try:
        if calibration is not None:
            calibration.check(decode.size(args.video))
    except ValueError as error:
        parser.error(str(error))
    # ponytail: net crossings use a vertical line through the court center; actions.py follows the
    # net's leaning line, which contacts.py could use too if crossings near the posts matter.
    net_x = args.net_x if calibration is None else float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    timings: dict[str, float] = {}

    if args.players and calibration is None:
        parser.error("--players needs --court")
    track_path, players_path = out / "ball.csv", out / "players.csv"
    new_ball = args.force or not track_path.exists()
    new_players = args.players and (args.force or not players_path.exists())
    if new_ball or new_players:
        reasons = slow_run_reasons(os.nice(0), os.getloadavg()[0], os.cpu_count() or 1)
        if reasons and not args.anyway:
            parser.error(" ".join(reasons) + " Using the most CPU: " + ", ".join(busiest()) + ". --anyway to track all the same.")
        stage("tracking")
        start = time.perf_counter()
        track(args.video, calibration, fps, track_path if new_ball else None, players_path if new_players else None, frame_count)
        timings[" and ".join(name for name, new in (("ball", new_ball), ("players", new_players)) if new)] = time.perf_counter() - start
    if new_players:
        # New tracks: the identities, their embeddings and the attackers' poses (by track) start over.
        for stale in ("identities.csv", "embeddings.npz", "looks.npz", jerseys.FILE, "jumps.json", "jumps_rows.npz"):
            (out / stale).unlink(missing_ok=True)
        if (out / "identity_answers.json").exists():
            print(f"{out / 'identity_answers.json'} answers about the previous player tracks: review the identities again", file=sys.stderr)

    rows = attribution.read_players(players_path) if args.players else None
    if playing.wanted(args.video, out):
        stage("play")
        start = time.perf_counter()
        playing.predict(args.video, out / playing.FILE, playing.weights(out))
        timings["play"] = time.perf_counter() - start
    stage("rallies")
    start = time.perf_counter()
    whistle_times = rallies.whistles(rallies.read_audio(args.video))
    positions = None if rows is None else [(r.frame, *r.court) for r in rows]
    windows, found, crossings = rally_windows(rallies.load_track(track_path), whistle_times, fps, net_x, calibration, positions)
    play = playing.load(out / playing.FILE) if (out / playing.FILE).exists() else None
    if play:
        windows = playing.moved(windows, fps, *play[:2], play[2])
    if starts:
        # The rallies before set 1 are the warm-up's.
        windows = [w for w in windows if w[0] >= starts[0] * fps]
    end = teams.match_end(out)
    if end is not None:
        windows = [w for w in windows if w[0] < end * fps]
    timings["rallies and contacts"] = time.perf_counter() - start

    stage("actions")
    start = time.perf_counter()
    alive = playing.goes_on(*play[:2], fps) if play and "alive" in play[2] else None
    windows, typed = typed_windows(windows, found, crossings, fps, net_x, calibration, rows, rallies.load_track(track_path), whistle_times, alive)
    typed = actions.mark_relances(args.video, typed, fps, out / "relances.json")
    if calibration is not None and calibration.lens:
        typed = actions.by_flight(typed, ball3d.flight_places(typed, windows, round(actions.LEAD_S * fps), track_path, calibration, fps), fps)
    timings["actions"] = time.perf_counter() - start

    tracks, touchers, gaps, found_teams, settled = None, [None] * len(typed), [None] * len(typed), None, None
    lead = round(actions.LEAD_S * fps)
    if args.players:
        candidates = attribution.ranked(typed, rows, fps)
        gaps = [attribution.gap_to_next(c) for c in candidates]
        # A dead ball is one track nearest the ball touch after touch, whatever the wrists say.
        dead, _ = actions.mark_dead(typed, [c[0][2] if c else None for c in candidates], [rally_of(t[0], windows, lead) for t in typed], alive)
        stage("wrists")
        start = time.perf_counter()
        # The learned order on the camera footage it was trained on, the wrists' rule elsewhere.
        learned = ranker.load() if decode.size(args.video)[1] >= ranker.MIN_HEIGHT else None
        places = ball3d.flight_places(typed, windows, lead, track_path, calibration, fps) if learned else None
        candidates = attribution.by_wrists(args.video, typed, candidates, rows, fps, out / "wrists.json", learned, places)
        timings["wrists"] = time.perf_counter() - start
        touchers = [None if a[3] != b[3] or not c else c[0][2] for a, b, c in zip(typed, dead, candidates)]
        typed = dead
    kept = playing.confirmed(windows, fps, *play[:2]) if play and "keep" in play[2] else None
    idle = actions.no_play(typed, [rally_of(t[0], windows, lead) for t in typed], windows, crossings, fps, kept)
    if idle:
        keep = [k for k, t in enumerate(typed) if rally_of(t[0], windows, lead) not in idle]
        typed, touchers, gaps = [typed[k] for k in keep], [touchers[k] for k in keep], [gaps[k] for k in keep]
        windows = [w for k, w in enumerate(windows) if k not in idle]
    crossings = in_rallies(crossings, windows, lead)
    write_csv(out / "net.csv", ["frame"], [[f] for f in crossings])
    if args.players:
        stage("teams")
        start = time.perf_counter()
        try:
            found_teams, settled = settled_teams(
                lambda known: teams.assign(args.video, rows, windows, fps, known, out / "looks.npz"),
                lambda found: teams.settle(
                    out / "teams.json", found, windows, fps, args.teams, sys.stdin.isatty(), teams.recording_date(args.video), day, args.title,
                    sets, args.scores and args.scores.split(","),
                ),
                starts,
            )
        except ValueError as error:
            parser.error(str(error))
        timings["teams"] = time.perf_counter() - start
        write_csv(out / "tracks.csv", ["track", "team"], sorted(found_teams.tracks.items()))

    if found_teams is None:
        # An earlier run's teams no longer fit these rallies; teams.json keeps what was typed for the next --players run.
        for stale in ("points.csv", "tracks.csv", timeouts.DETECTED):
            (out / stale).unlink(missing_ok=True)
        write_csv(out / "rallies.csv", ["start_frame", "end_frame"], windows)
        write_csv(out / "actions.csv", ["frame", "x", "y", "type", "side", "track"], [[*t, "" if k is None else k] for t, k in zip(typed, touchers)])
        text = report(args.video, fps, frame_count, windows, typed, crossings, timings)
    else:
        sets = teams.set_numbers(windows, [teams.seconds(s) for s in settled["sets"]], fps)
        write_csv(out / "rallies.csv", ["start_frame", "end_frame", "left", "set"], [[*w, "" if g is None else g, s] for w, g, s in zip(windows, found_teams.left, sets)])
        timeouts.detect(out, fps)
        contact_teams = teams.contact_teams(typed, windows, found_teams.left, round(actions.LEAD_S * fps))
        stage("jerseys")
        start = time.perf_counter()
        read_jerseys(out, args.video)
        timings["jerseys"] = time.perf_counter() - start
        stage("scoreboard")
        start = time.perf_counter()
        scoreboard.run(out, args.video)
        timings["scoreboard"] = time.perf_counter() - start
        stage("identity")
        start = time.perf_counter()
        attributed = [(t[0], k) for t, k in zip(typed, touchers) if k is not None]
        known = identity.run(out, args.video, rows, windows, found_teams.left, fps, args.squad, attributed)
        timings["identity"] = time.perf_counter() - start
        stage("jumps")
        start = time.perf_counter()
        # The attackers' poses for the page's jumps (`web.jumped`): its build then only poses the touches the review moves.
        attacks = [(t[0], k) for t, k in zip(typed, touchers) if t[3] == "attack" and k is not None]
        if attacks:
            jumps.pose_all(args.video, attacks, jumps.attack_rows(players_path, attacks, fps, out / "jumps_rows.npz"), fps, out / "jumps.json")
        timings["jumps"] = time.perf_counter() - start
        who = [identity.touch_identity(known, k, t[0], fps) if k is not None else None for t, k in zip(typed, touchers)]
        # A track swapping players across the net can hold an identity of the other team.
        # `gap`: box heights from the toucher to the next candidate, the doubt about the pick.
        rows_out = [
            [*t, "" if k is None else k, "" if k is None or d is None else round(d, 3), "" if g is None else g, "" if w is None or w[0] != g else w[1]]
            for t, k, d, g, w in zip(typed, touchers, gaps, contact_teams, who)
        ]
        write_csv(out / "actions.csv", ["frame", "x", "y", "type", "side", "track", "gap", "team", "identity"], rows_out)
        # ponytail: a rally with unknown sides counts team 1 on the left, as points.main does.
        found_points = points.points(typed, crossings, windows, [g or 1 for g in found_teams.left], sets, fps, calibration)
        points.write_points(out / "points.csv", windows, found_points)
        names = [team["name"] or teams.default_name(k) for k, team in enumerate(settled["teams"], 1)]
        counts = Counter(found_teams.tracks.values())
        tracks = {names[0]: counts[1], names[1]: counts[2]}
        text = report(args.video, fps, frame_count, windows, typed, crossings, timings, tracks, names, contact_teams, sets, settled["date"], settled["title"])
        text += "\n" + "\n".join(f"- {line}" for line in points.summary(found_points, settled["scores"])) + "\n"
    (out / "report.md").write_text(text)
    print(text, end="")
    print(out / "report.md")
    if args.players and args.court and not args.no_page:
        stage("page")
        review_page(out, args.video, args.court)


if __name__ == "__main__":
    main()
