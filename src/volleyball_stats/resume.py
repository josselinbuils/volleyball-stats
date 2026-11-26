"""The tracking pass kept as it goes, CHUNK frames at a time in the match's FOLDER: a run stopped (a sleep, a restart, the
app closed) starts again after the last part kept, its tracks byte for byte those of a run never stopped (`match.track`).

Each part holds its frames' ball positions and player rows, and the players' tracker as it was after its last frame (its
tracks, their Kalman filters, the next track id): the next frames carry on from it. The ball needs no state but the
frames: each frame's position is the best of the 3-frame windows seeing it, run BATCH at a time, so a run started again
reads the BATCH frames before the part again, its windows batched as before.
"""

import json
import pickle
import shutil
from pathlib import Path

from volleyball_stats import files

FOLDER, KEY = "tracking_parts", "key.json"
# The ball's batch in frames (ball.BATCH * ball.STRIDE, not imported: it loads torch, and the app reads `done`), and the
# frames of a part, a whole number of them: about 3 minutes at 50 fps.
LEAD, CHUNK = 16, 9600


def stamp(video: Path, court: Path | None, with_ball: bool, with_players: bool, fps: float, device: str) -> str:
    """What the parts depend on: the video, its court, the models, the tracking's code and dependencies: parts kept
    under another stamp would not join with what this run tracks."""
    from volleyball_stats import ball, match, players

    code = files.code_text(match.tracked, match.track, match.side_by_side, ball.track_frames, players.track_frames, players.make_tracker)
    sources = [p for p in (court, ball.WEIGHTS_PATH, players.MODEL) if p is not None]
    return files.cache_stamp(video, sources, f"{with_ball}:{with_players}:{fps}:{CHUNK}:{device}:{code}")


def part(folder: Path, end: int) -> Path:
    return folder / f"{end:08d}.pkl"


def kept(folder: Path, key: str) -> tuple[int, list[list], list, object | None]:
    """Where the tracking starts again (a frame), the ball positions and player rows before it and the players' tracker
    there (None from the start): the parts kept in `folder` under `key`, those of another key removed."""
    from volleyball_stats import players

    if files.read_json(folder / KEY, {}).get("key") != key:
        shutil.rmtree(folder, ignore_errors=True)
        return 0, [], [], None
    positions: list[list] = []
    rows: list[players.Row] = []
    tracker, end = None, 0
    # Parts in a row from the start: one missing ends them (written in order, it is the last, cut short).
    while (path := part(folder, end + CHUNK)).exists():
        try:
            found = pickle.loads(path.read_bytes())
        except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ImportError):
            break
        positions += found["positions"]
        rows += found["rows"]
        tracker, end = found["tracker"], end + CHUNK
        players.restore_ids(found["ids"])
    return end, positions, rows, tracker


def start(folder: Path, key: str, frames: int) -> None:
    """A new pass on `frames` frames under `key` (kept for `done`)."""
    folder.mkdir(parents=True, exist_ok=True)
    files.write_text(folder / KEY, json.dumps({"key": key, "frames": frames}) + "\n")


def save(folder: Path, end: int, positions: list[list], rows: list, tracker) -> None:
    """The part ending at frame `end`: its CHUNK frames' `positions` and player rows, the `tracker` after them."""
    from volleyball_stats import players

    # The parts are this machine's own files: the backups leave FOLDER out (backup.SKIP).
    files.write_bytes(part(folder, end), pickle.dumps({"positions": positions, "rows": rows, "tracker": tracker, "ids": players.next_ids()}, pickle.HIGHEST_PROTOCOL))


def done(out: Path) -> float:
    """The share of the video a stopped pass on the match in `out` tracked (0 when none), as the app tells it before it
    starts again."""
    folder = out / FOLDER
    frames = files.read_json(folder / KEY, {}).get("frames") or 0
    end = 0
    while part(folder, end + CHUNK).exists():
        end += CHUNK
    return min(1.0, end / frames) if frames else 0.0


def clear(out: Path) -> None:
    shutil.rmtree(out / FOLDER, ignore_errors=True)
