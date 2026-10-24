"""Run the whole pipeline on a match video and write a first report.

    uv run python -m volleyball_stats.match VIDEO (--court CALIBRATION_JSON | --net-x PX) [--force]

Each step writes its output to outputs/<video>/; the ball track, the slow step, is reused when it
exists unless --force.
"""

import argparse
import csv
import time
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import ball, contacts, court, rallies

# Seconds around a rally window still counted as its contacts: the serve contact comes slightly
# before the window's start, which is placed where the served ball has travelled.
RALLY_MARGIN = 0.5


def track_ball(video: Path, out: Path) -> None:
    device = ball.default_device()
    model = ball.load_model(device)
    with open(out, "w", newline="") as f:
        rows = csv.writer(f)
        rows.writerow(["frame", "visible", "x", "y"])
        for index, (_, position) in enumerate(ball.track_frames(ball.read_frames(video), model, device)):
            rows.writerow([index, int(position is not None), *(position or ("", ""))])


def in_rallies(frames: list[int], windows: list[tuple[int, int]], margin: int) -> list[int]:
    return [f for f in frames if any(start - margin <= f <= end + margin for start, end in windows)]


def write_csv(path: Path, header: list[str], rows: list) -> None:
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([header, *rows])


def report(video: Path, fps: float, frame_count: int, windows: list[tuple[int, int]], hits: list[int], crossings: list[int], timings: dict[str, float]) -> str:
    lengths = np.array([(end - start) / fps for start, end in windows])
    duration = frame_count / fps
    lines = [
        f"# {video.stem}",
        "",
        f"- Duration: {duration / 60:.1f} min",
        f"- Rallies: {len(windows)}, ball in play {lengths.sum() / 60:.1f} min ({lengths.sum() / duration:.0%})"
        + (f", median rally {np.median(lengths):.1f} s" if len(windows) else ""),
        f"- Contacts in rallies: {len(hits)}" + (f", {len(hits) / len(windows):.1f} per rally" if windows else ""),
        f"- Net crossings in rallies: {len(crossings)}",
        "",
        "Processing time: " + ", ".join(f"{step} {seconds / 60:.1f} min" for step, seconds in timings.items()),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline on a match video.")
    parser.add_argument("video", type=Path)
    net = parser.add_mutually_exclusive_group(required=True)
    net.add_argument("--court", type=Path, help="Court calibration JSON (court.py fit or auto)")
    net.add_argument("--net-x", type=float, help="Net position in frame pixels, without a calibration")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    parser.add_argument("--force", action="store_true", help="Track the ball again even if a track exists")
    args = parser.parse_args()

    out = args.out / args.video.stem
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    fps, frame_count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    # ponytail: the net as a vertical line through the court center; the calibration could give
    # its leaning plane (about 25 px between the posts at 720p) if crossings near the posts matter.
    net_x = args.net_x if args.net_x is not None else float(court.Calibration.load(args.court).to_image(np.array([[0.0, 0.0]]))[0, 0])
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
    margin = round(RALLY_MARGIN * fps)
    kept = set(in_rallies([frame for frame, _, _ in found], windows, margin))
    hits = [c for c in found if c[0] in kept]
    crossings = in_rallies(crossings, windows, margin)
    write_csv(out / "contacts.csv", ["frame", "x", "y"], hits)
    write_csv(out / "net.csv", ["frame"], [[f] for f in crossings])
    timings["contacts"] = time.perf_counter() - start

    text = report(args.video, fps, frame_count, windows, [c[0] for c in hits], crossings, timings)
    (out / "report.md").write_text(text)
    print(text, end="")
    print(out / "report.md")


if __name__ == "__main__":
    main()
