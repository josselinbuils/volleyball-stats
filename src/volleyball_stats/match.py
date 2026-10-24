"""Run the whole pipeline on a match video and write a first report.

    uv run python -m volleyball_stats.match VIDEO (--court CALIBRATION_JSON | --net-x PX) [--players] [--force]

Each step writes its output to outputs/<video>/; the ball and player tracks, the slow steps, are
reused when they exist unless --force.
"""

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import actions, ball, contacts, court, players, rallies

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


def report(
    video: Path,
    fps: float,
    frame_count: int,
    windows: list[tuple[int, int]],
    typed: list[actions.Typed],
    crossings: list[int],
    timings: dict[str, float],
    tracks: dict[str, int] | None = None,
) -> str:
    lengths = np.array([(end - start) / fps for start, end in windows])
    duration = frame_count / fps
    counts = Counter((kind, side) for _, _, _, kind, side in typed)
    lines = [
        f"# {video.stem}",
        "",
        f"- Duration: {duration / 60:.1f} min",
        f"- Rallies: {len(windows)}, ball in play {lengths.sum() / 60:.1f} min ({lengths.sum() / duration:.0%})"
        + (f", median rally {np.median(lengths):.1f} s" if len(windows) else ""),
        f"- Contacts in rallies: {len(typed)}" + (f", {len(typed) / len(windows):.1f} per rally" if windows else ""),
        f"- Net crossings in rallies: {len(crossings)}",
        *([f"- Player tracks: {tracks.get('left', 0)} left of the net, {tracks.get('right', 0)} right"] if tracks is not None else []),
        "",
        "| Action | Left of the net | Right of the net |",
        "| --- | --- | --- |",
        *(f"| {kind} | {counts[kind, 'left']} | {counts[kind, 'right']} |" for kind in TYPES),
        "",
        "Processing time: " + ", ".join(f"{step} {seconds / 60:.1f} min" for step, seconds in timings.items()),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline on a match video.")
    parser.add_argument("video", type=Path)
    net = parser.add_mutually_exclusive_group(required=True)
    net.add_argument("--court", type=Path, help="Court calibration JSON (court.py fit or auto)")
    net.add_argument("--net-x", type=float, help="Net position in frame pixels, without a calibration (no floor contacts)")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--players", action="store_true", help="Also track the players (about 2.5x the ball's time)")
    parser.add_argument("--force", action="store_true", help="Track the ball and players again even if tracks exist")
    args = parser.parse_args()

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
    write_csv(out / "rallies.csv", ["start_frame", "end_frame"], windows)
    timings["rallies"] = time.perf_counter() - start

    start = time.perf_counter()
    found, crossings = contacts.detect(contacts.read_track(track_path), fps, net_x)
    typed = actions.mark_relances(args.video, actions.classify(found, crossings, windows, fps, net_x, calibration), fps)
    crossings = in_rallies(crossings, windows, round(actions.LEAD_S * fps))
    write_csv(out / "actions.csv", ["frame", "x", "y", "type", "side"], typed)
    write_csv(out / "net.csv", ["frame"], [[f] for f in crossings])
    timings["contacts and actions"] = time.perf_counter() - start

    tracks = None
    if args.players:
        if calibration is None:
            parser.error("--players needs --court")
        players_path = out / "players.csv"
        if args.force or not players_path.exists():
            start = time.perf_counter()
            players.write_csv(players.track(args.video, calibration), players_path)
            timings["players"] = time.perf_counter() - start
        with open(players_path) as f:
            teams = {(row["track"], row["team"]) for row in csv.DictReader(f)}
        tracks = dict(Counter(team for _, team in teams))

    text = report(args.video, fps, frame_count, windows, typed, crossings, timings, tracks)
    (out / "report.md").write_text(text)
    print(text, end="")
    print(out / "report.md")


if __name__ == "__main__":
    main()
