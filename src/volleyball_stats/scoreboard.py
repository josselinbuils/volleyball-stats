"""The flip score board the scorer keeps beside the court, read before each serve by RapidOCR (as
jerseys.py) on the frame's lower part, where it stands near the camera: its two scores and, between
them, the sets each side won. What each frame read is kept in scoreboard.csv: a rerun reads only
the frames it lacks. The review compares the board with the running score (`review.board_off`).
A step of match.py; alone:

    uv run python -m volleyball_stats.scoreboard outputs/matches/MATCH --video VIDEO
"""

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

import cv2

from volleyball_stats import decode, files, web

FILE = "scoreboard.csv"
# The board stands on the floor near the camera: the frame's rows below this share of its height.
LOW = 0.7
# Frames read every STEP_S of the match (the same frames whatever the rallies) over the last
# BEFORE_S seconds before a serve: the board shows the score after the rally before. A reading
# AGREE frames give is kept; the reader's texts under CONFIDENCE are dropped.
BEFORE_S, STEP_S, AGREE, CONFIDENCE = 3.0, 0.5, 2, 0.8
# Over this, a score is a misreading.
MAX_SCORE = 40

Board = tuple[int, int, int, int]


def parse(text: str, sets: set[int]) -> Board | None:
    """(left score, left sets, right sets, right score) of a reading such as "152011": one digit of
    sets for each side in the middle, adding up to one of `sets`, and scores of 1-2 digits without a
    leading zero; None for no such reading or more than one."""
    found = []
    for i in (1, 2):
        j = len(text) - i - 2
        if not text.isdigit() or j not in (1, 2):
            continue
        left, a, b, right = text[:i], int(text[i]), int(text[i + 1]), text[i + 2 :]
        if any(len(s) > 1 and s[0] == "0" for s in (left, right)) or a + b not in sets or max(int(left), int(right)) > MAX_SCORE:
            continue
        found.append((int(left), a, b, int(right)))
    return found[0] if len(found) == 1 else None


def gaps(rallies: list[tuple[float, float, int]]) -> list[tuple[float, float, set[int]]]:
    """Where the board shows the score after each rally (start, end, set; seconds), as (from, to,
    sets played): before the next serve, or after the last rally; the board may already count the
    set just ended."""
    out = [(max(rallies[k][1], rallies[k + 1][0] - BEFORE_S), rallies[k + 1][0], {rallies[k][2] - 1, rallies[k + 1][2] - 1}) for k in range(len(rallies) - 1)]
    if rallies:
        out.append((rallies[-1][1] + STEP_S, rallies[-1][1] + BEFORE_S, {rallies[-1][2] - 1, rallies[-1][2]}))
    return out


def grid(start: float, end: float, fps: float) -> range:
    """The frames read between two moments: every STEP_S of the match."""
    step = round(STEP_S * fps)
    return range(-(-round(start * fps) // step) * step, round(end * fps), step)


def boards(texts: dict[int, list[str]], rallies: list[tuple[float, float, int]], fps: float) -> list[tuple[int, Board]]:
    """(rally index, board after it) where AGREE frames or more read the same, `steady` ones only."""
    out = []
    for k, (start, end, sets) in enumerate(gaps(rallies)):
        read = [b for f in grid(start, end, fps) for b in (parse(t, sets) for t in texts.get(f, [])) if b]
        if read:
            board, n = Counter(read).most_common(1)[0]
            if n >= AGREE:
                out.append((k, board))
    return steady(out)


def steady(found: list[tuple[int, Board]]) -> list[tuple[int, Board]]:
    """The longest run of readings, set by set (the sets played: the reader may swap the two digits),
    whose scores never go down: a misread one goes."""
    out = []
    for sets in dict.fromkeys(b[1] + b[2] for _, b in found):
        mine = [(k, b) for k, b in found if b[1] + b[2] == sets]
        # ponytail: O(n²) over a set's readings, a few dozen.
        best: list[list[tuple[int, Board]]] = []
        for i, (k, b) in enumerate(mine):
            before = [best[j] for j in range(i) if mine[j][1][0] <= b[0] and mine[j][1][3] <= b[3]]
            best.append(max(before, key=len, default=[]) + [(k, b)])
        out += max(best, key=len, default=[])
    return sorted(out)


def load(match: Path) -> dict[int, list[str]]:
    """FILE's texts by frame, an empty list for a frame read with none."""
    path = match / FILE
    found: dict[int, list[str]] = {}
    if path.exists():
        with open(path) as f:
            for r in csv.DictReader(f):
                found.setdefault(int(r["frame"]), []).extend([r["text"]] if r["text"] else [])
    return found


def run(match: Path, video: Path) -> None:
    """Reads the board before each serve of the match's rallies (rallies.csv), the frames not read yet."""
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    rows = web.read_csv(match / "rallies.csv")
    rallies = [(int(r["start_frame"]) / fps, int(r["end_frame"]) / fps, int(r.get("set") or 1)) for r in rows]
    texts = load(match)
    wanted = {f for a, b, _ in gaps(rallies) for f in grid(a, b, fps)} - texts.keys()
    if not wanted:
        return
    from rapidocr_onnxruntime import RapidOCR

    reader = RapidOCR()
    for frame, image in decode.frames_at(video, wanted):
        found = reader(image[int(image.shape[0] * LOW) :])[0] or []
        texts[frame] = [t.replace(" ", "") for _, t, confidence in found if confidence >= CONFIDENCE and t.replace(" ", "").isdigit()]
    with files.replacing(match / FILE, newline="") as f:
        csv.writer(f).writerows([["frame", "text"], *[(frame, t) for frame, found in sorted(texts.items()) for t in found or [""]]])


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the score board before each serve of a match.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/matches/VIDEO)")
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    run(args.match, args.video)
    print(f"{len(load(args.match))} frames read in {time.perf_counter() - start:.0f} s: {args.match / FILE}")


if __name__ == "__main__":
    main()
