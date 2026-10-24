"""Run the whole pipeline on a match video and write a first report.

    uv run python -m volleyball_stats.match VIDEO (--court CALIBRATION_JSON | --net-x PX) [--players [--teams "NAME_1[:COLOUR],NAME_2[:COLOUR]"] [--date YYYY-MM-DD] [--title TITLE]] [--force]

Each step writes its output to outputs/<video>/; the ball and player tracks, the slow steps, are
reused when they exist unless --force. With the players, teams.json holds the teams' names, colours,
the match's date and title and the set starts: written on the first run (asked on a terminal),
edited by hand if need be, reused on the next runs unless the flags override them.
"""

import argparse
import csv
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import actions, attribution, ball, contacts, court, players, rallies, teams

TYPES = ["serve", "pass", "set", "attack", "relance", "block", "dig", "floor", "net"]


def track_ball(video: Path, out: Path) -> None:
    device = ball.default_device()
    model = ball.load_model(device)
    with open(out, "w", newline="") as f:
        rows = csv.writer(f)
        rows.writerow(["frame", "visible", "x", "y"])
        for index, (_, position) in enumerate(ball.track_frames(ball.read_frames(video), model, device)):
            rows.writerow([index, int(position is not None), *(position or ("", ""))])


def in_rallies(frames: list[int], windows: list[tuple[int, int]], lead: int) -> list[int]:
    """Frames inside a rally window started `lead` frames early, like actions.classify's."""
    return [f for f in frames if any(start - lead <= f <= end for start, end in windows)]


def write_csv(path: Path, header: list[str], rows: list) -> None:
    with open(path, "w", newline="") as f:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline on a match video.")
    parser.add_argument("video", type=Path)
    net = parser.add_mutually_exclusive_group(required=True)
    net.add_argument("--court", type=Path, help="Court calibration JSON (court.py fit or auto)")
    net.add_argument("--net-x", type=float, help="Net position in frame pixels, without a calibration (no floor contacts)")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
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
    parser.add_argument("--force", action="store_true", help="Track the ball and players again even if tracks exist")
    args = parser.parse_args()
    day = teams.parse_date(args.date) if args.date else None
    if args.date and day is None:
        parser.error(f"Not a date: {args.date!r} (use YYYY-MM-DD)")

    out = args.out / args.video.stem
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    fps, frame_count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    calibration = court.Calibration.load(args.court) if args.court else None
    # ponytail: net crossings use a vertical line through the court center; actions.py follows the
    # net's leaning line, which contacts.py could use too if crossings near the posts matter.
    net_x = args.net_x if calibration is None else float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    timings: dict[str, float] = {}

    track_path = out / "ball.csv"
    if args.force or not track_path.exists():
        start = time.perf_counter()
        track_ball(args.video, track_path)
        timings["ball"] = time.perf_counter() - start

    start = time.perf_counter()
    windows = rallies.segment(rallies.load_track(track_path), rallies.whistles(rallies.read_audio(args.video)), fps)
    timings["rallies"] = time.perf_counter() - start

    start = time.perf_counter()
    found, crossings = contacts.detect(contacts.read_track(track_path), fps, net_x)
    typed = actions.mark_relances(args.video, actions.classify(found, crossings, windows, fps, net_x, calibration), fps)
    crossings = in_rallies(crossings, windows, round(actions.LEAD_S * fps))
    write_csv(out / "net.csv", ["frame"], [[f] for f in crossings])
    timings["contacts and actions"] = time.perf_counter() - start

    tracks, touchers, found_teams, settled = None, [None] * len(typed), None, None
    if args.players:
        if calibration is None:
            parser.error("--players needs --court")
        players_path = out / "players.csv"
        if args.force or not players_path.exists():
            start = time.perf_counter()
            players.write_csv(players.track(args.video, calibration), players_path)
            timings["players"] = time.perf_counter() - start
        rows = attribution.read_players(players_path)
        touchers = attribution.attribute(typed, rows, fps)
        start = time.perf_counter()
        found_teams = teams.assign(args.video, rows, windows)
        timings["teams"] = time.perf_counter() - start
        try:
            settled = teams.settle(out / "teams.json", found_teams, windows, fps, args.teams, sys.stdin.isatty(), teams.recording_date(args.video), day, args.title)
        except ValueError as error:
            parser.error(str(error))
        write_csv(out / "tracks.csv", ["track", "team"], sorted(found_teams.tracks.items()))
    elif args.teams or args.date or args.title is not None:
        parser.error("--teams, --date and --title need --players")

    if found_teams is None:
        write_csv(out / "rallies.csv", ["start_frame", "end_frame"], windows)
        write_csv(out / "actions.csv", ["frame", "x", "y", "type", "side", "track"], [[*t, "" if k is None else k] for t, k in zip(typed, touchers)])
        text = report(args.video, fps, frame_count, windows, typed, crossings, timings)
    else:
        sets = teams.set_numbers(windows, [teams.seconds(s) for s in settled["sets"]], fps)
        write_csv(out / "rallies.csv", ["start_frame", "end_frame", "left", "set"], [[*w, "" if g is None else g, s] for w, g, s in zip(windows, found_teams.left, sets)])
        contact_teams = teams.contact_teams(typed, windows, found_teams.left, round(actions.LEAD_S * fps))
        rows_out = [[*t, "" if k is None else k, "" if g is None else g] for t, k, g in zip(typed, touchers, contact_teams)]
        write_csv(out / "actions.csv", ["frame", "x", "y", "type", "side", "track", "team"], rows_out)
        names = [team["name"] or teams.default_name(k) for k, team in enumerate(settled["teams"], 1)]
        counts = Counter(found_teams.tracks.values())
        tracks = {names[0]: counts[1], names[1]: counts[2]}
        text = report(args.video, fps, frame_count, windows, typed, crossings, timings, tracks, names, contact_teams, sets, settled["date"], settled["title"])
    (out / "report.md").write_text(text)
    print(text, end="")
    print(out / "report.md")


if __name__ == "__main__":
    main()
