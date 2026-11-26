"""How long a match's analysis takes on this machine, said before it starts: each stage's duration here per second of
video, kept by every full run (TIMINGS), else the RTX 5080's scaled by this machine's speed, measured once at
the first import on the video's first seconds (`measure`, kept in SPEED).

    python -m volleyball_stats.estimate VIDEO --outputs outputs   # measures this machine, for the app's import
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from volleyball_stats import files

# The pipeline's stages' durations here (match.plan), and this machine's measure.
TIMINGS, SPEED = "pipeline_timings.json", "speed.json"
# The RTX 5080's stages per second of a 4K 50 fps video (WSL2, pipeline_timings.json on 26 Nov; the gesture stage,
# not run there, review.TOOK's scaled as its tracking), and its tracking pass's seconds per frame as `measure` times it.
REFERENCE = {
    "tracking": 1.260, "play": 0.149, "rallies": 0.013, "actions": 0.049, "wrists": 0.049, "gesture": 0.084, "teams": 0.121,
    "jerseys": 0.333, "scoreboard": 0.038, "identity": 0.389, "jumps": 0.073, "page": 0.023,
}
REFERENCE_FRAME_S, REFERENCE_FPS = 0.0250, 50.0
# `measure`: the frames timed after the first WARMUP ones (the models loading), FRAMES of them, fewer past LIMIT_S.
WARMUP, FRAMES, LIMIT_S = 50, 500, 30.0
# Slower than this many seconds per second of video (a 2-hour match past two days): too slow, the app says.
SLOW = 24.0


def kept(outputs: Path) -> dict[str, float]:
    return files.read_json(outputs / TIMINGS, None) or {}


def factor(outputs: Path) -> float | None:
    """This machine's time over the RTX 5080's: its tracking kept by a full run, else its measure; None before either."""
    here = kept(outputs).get("tracking")
    if here:
        return here / REFERENCE["tracking"]
    measured = files.read_json(outputs / SPEED, None)
    return measured["frame_s"] / REFERENCE_FRAME_S if measured else None


def stages(outputs: Path) -> dict[str, float] | None:
    """Each stage's seconds per second of video here: those a run kept, the others the RTX 5080's times `factor`; None
    before any run or measure."""
    # ponytail: every stage scaled as the tracking (GPU) pass; the CPU-bound ones (the OCR, the jerseys) may scale
    # otherwise on a machine whose CPU and GPU differ from the PC's, until its first full run keeps its own.
    scale = factor(outputs)
    return None if scale is None else {**{k: v * scale for k, v in REFERENCE.items()}, **kept(outputs)}


def planned(video: Path, out: Path) -> list[str]:
    """The stages a first run on `video` goes through (match.main's plan), its result in `out`."""
    from volleyball_stats import gesture, playing

    play, gestures = playing.wanted(video, out), gesture.wanted(video, out)
    return [s for s in REFERENCE if (s != "play" or play) and (s != "gesture" or gestures)]


def seconds(outputs: Path, video: Path, out: Path, duration: float, tracked: float = 0.0) -> float | None:
    """The analysis of `video` (`duration` seconds long) here, in seconds, the `tracked` share of its tracking kept by a
    run stopped (`resume.done`); None before any run or measure."""
    found = stages(outputs)
    return None if found is None else duration * sum(found.get(s, 0.0) * (1 - tracked if s == "tracking" else 1) for s in planned(video, out))


def measure(video: Path, outputs: Path) -> dict:
    """This machine's tracking pass timed on the video's first frames, kept in `outputs`/SPEED; its share told as the
    frames go (`jobs.tell`). Any calibration keeps the timing honest: the court only drops rows."""
    import cv2

    from volleyball_stats import ball, court, decode, jobs, match

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or REFERENCE_FPS
    cap.release()
    width, height = decode.size(video)
    calibration = court.Calibration(np.diag([width / 20, height / 10, 1.0]) @ [[1, 0, 10], [0, 1, 5], [0, 0, 1]])
    jobs.tell(0.0)
    seen = jobs.every(WARMUP + FRAMES, jobs.tell)
    start, timed = None, 0
    for k, _ in enumerate(match.tracked(video, calibration, True, True, fps, count=WARMUP + FRAMES)):
        seen(k)
        if k + 1 == WARMUP:
            start = time.perf_counter()
        elif start is not None:
            timed += 1
            # A slow machine is told so as well by fewer frames.
            if time.perf_counter() - start > LIMIT_S and timed >= 10:
                break
    if start is None or not timed:
        raise ValueError(f"{video}: too short to time")
    found = {"frame_s": (time.perf_counter() - start) / timed, "frames": timed, "device": ball.default_device(), "at": time.strftime("%Y-%m-%d")}
    files.write_text(outputs / SPEED, json.dumps(found, indent=1) + "\n")
    jobs.tell(1.0)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Time this machine's tracking on a video's first seconds, for the app's time before an analysis.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    # The import goes on without it: the app then says no time.
    try:
        found = measure(args.video, args.outputs)
        print(f"{found['frame_s'] * 1000:.1f} ms a frame on {found['device']} ({found['frames']} frames)", flush=True)
    except Exception as error:  # noqa: BLE001
        print(f"Could not time this machine: {error}", flush=True)


if __name__ == "__main__":
    main()
