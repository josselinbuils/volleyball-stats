"""Import a match from the camera's card, named like its hosted page.

    uv run python -m volleyball_stats.import_match SOURCE --teams "NAME_1[:COLOUR],NAME_2[:COLOUR]" [--from TIME] [--to TIME] [--date DATE] [--recording N]

Joins a recording's chapters without re-encoding, from --from to --to in the joined video, into data/matches/MATCH/MATCH.mp4, and starts
outputs/matches/MATCH/ with teams.json and start.jpg to check the sides. The first team is the one on the left at the first rally. The cut
starts on the keyframe before --from. SOURCE is only read.
"""

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from volleyball_stats import files, jobs, matches, teams

CAMERA_NAME = re.compile(r"(\d{14})_\d+_")
# Chapters of one recording follow each other within this long.
SAME_RECORDING_S = 5.0
# How far from the times asked the cut video may end up: a keyframe's distance.
CUT_TOLERANCE_S = 2.0
# The import's preview: wide enough to see the serve and the scoreboard, quick to make from 4K.
PREVIEW_WIDTH = 640


@dataclass
class Chapter:
    path: Path
    duration: float
    frames: int

    @property
    def stamp(self) -> datetime | None:
        found = CAMERA_NAME.search(self.path.name)
        return datetime.strptime(found[1], "%Y%m%d%H%M%S") if found else None


def probe(path: Path) -> Chapter:
    """The video stream's length; its frames, 0 when the file does not say."""
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,duration", "-of", "json", str(path)]
    stream = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)["streams"][0]
    frames = stream.get("nb_frames", "0")
    return Chapter(path, float(stream["duration"]), int(frames) if frames.isdigit() else 0)


def videos(source: Path | list[Path]) -> list[Path]:
    """The videos of a card or folder in name order, which is the camera's; SOURCE itself if it is a file; those of
    each of several sources together."""
    if isinstance(source, list):
        return sorted({p for one in source for p in videos(one)}, key=lambda p: p.name)
    if source.is_file():
        return [source]
    return sorted((p for p in source.rglob("*") if p.suffix.lower() == ".mp4" and not any(part.startswith(".") for part in p.relative_to(source).parts)), key=lambda p: p.name)


def recordings(chapters: list[Chapter]) -> list[list[Chapter]]:
    """The chapters grouped by recording: a new one where the next chapter does not start as the last one ends."""
    groups: list[list[Chapter]] = []
    for chapter in chapters:
        last = groups[-1][-1] if groups else None
        follows = last and last.stamp and chapter.stamp and abs((chapter.stamp - last.stamp - timedelta(seconds=last.duration)).total_seconds()) <= SAME_RECORDING_S
        if follows or (last and not (last.stamp and chapter.stamp)):
            groups[-1].append(chapter)
        else:
            groups.append([chapter])
    return groups


def describe(groups: list[list[Chapter]]) -> str:
    return "; ".join(f"{k}: {g[0].stamp or g[0].path.name}, {teams.clock(sum(c.duration for c in g))}" for k, g in enumerate(groups, 1))


def concat_list(chapters: list[Chapter], start: float | None, end: float | None) -> str:
    """ffmpeg's list of the chapters from `start` to `end` in the joined video, the cut inside them: seeking across chapters lands too early."""
    lines, at = [], 0.0
    for chapter in chapters:
        begin, at = at, at + chapter.duration
        if (start and at <= start) or (end and begin >= end):
            continue
        lines.append("file '" + str(chapter.path.resolve()).replace("'", "'\\''") + "'")
        if start and begin < start:
            lines.append(f"inpoint {start - begin:.3f}")
        if end and at > end:
            lines.append(f"outpoint {end - begin:.3f}")
    return "\n".join(lines) + "\n"


def frame_at(chapters: list[Chapter], at: float, width: int = PREVIEW_WIDTH) -> bytes:
    """The picture at `at` seconds in the joined video, a JPEG `width` pixels wide: the import's preview."""
    begin = 0.0
    for chapter in chapters[:-1]:
        if at < begin + chapter.duration:
            break
        begin += chapter.duration
    else:
        chapter = chapters[-1]
    offset = min(max(at - begin, 0.0), chapter.duration)
    # The keyframe at or before: three times quicker on the camera's 4K (0.3 s against 1 s, a keyframe every 0.6 s there),
    # and where the cut starts. Past a chapter's last keyframe it gives nothing: a picture a second before its end then.
    for seek, at_most in ((["-skip_frame", "nokey", "-noaccurate_seek"], offset), ([], max(chapter.duration - 1.0, 0.0))):
        command = ["ffmpeg", "-nostdin", "-v", "error", *seek, "-ss", f"{min(offset, at_most):.2f}", "-i", str(chapter.path), "-frames:v", "1", "-vf", f"scale={width}:-2"]
        picture = subprocess.run([*command, "-q:v", "5", "-f", "image2pipe", "-c:v", "mjpeg", "-"], capture_output=True).stdout
        if picture:
            return picture
    raise LookupError("frame")


# What the copy and the index's move to the front of the file (+faststart, a second pass ffmpeg tells nothing of) took
# here, by second of video, kept beside the matches; before any, a camera card's (about 90 MB/s).
TIMINGS, TOOK = "import_timings.json", {"copy": 0.09, "index": 0.02}


def copied(command: list[str], expected: float, stages: jobs.Stages) -> None:
    """Runs ffmpeg's `command`, telling the copy's share done from its time over the `expected` seconds of video, then
    the index's move by its last duration (`stages`)."""
    process = subprocess.Popen([*command[:1], "-progress", "pipe:1", "-nostats", *command[1:]], stdout=subprocess.PIPE, text=True)
    stages.start("copy")
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and expected > 0:
            stages.share_of_stage(int(value) / 1e6 / expected)
            # Written to the end: the index moves to the front.
            if int(value) / 1e6 >= expected - 1 and stages.key == "copy":
                stages.start("index")
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, command)
    stages.start(None)


def join(chapters: list[Chapter], target: Path, start: float | None, end: float | None, timings: Path | None = None) -> None:
    """Writes the chapters as one video from `start` to `end`, checked, without re-encoding, telling its progress (each
    step's last duration kept in `timings`); `target` only appears once whole."""
    part = target.with_name(f"{target.stem}.part.mp4")
    listing = target.with_name(f"{target.stem}.part.txt")
    listing.write_text(concat_list(chapters, start, end))
    total = sum(c.duration for c in chapters)
    length = min(end or total, total) - (start or 0.0)
    try:
        copied(
            ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
            + ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-map_metadata", "0", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", "-y", str(part)],
            length,
            jobs.Stages(timings, ["copy", "index"], TOOK, scale=length),
        )
        made = probe(part)
        expected = min(end or total, total) - (start or 0.0)
        if abs(made.duration - expected) > CUT_TOLERANCE_S:
            raise RuntimeError(f"The video lasts {made.duration:.1f} s instead of {expected:.1f} s")
        frames = sum(c.frames for c in chapters)
        if not (start or end) and made.frames != frames:
            raise RuntimeError(f"The video has {made.frames} frames instead of {frames}")
        part.replace(target)
    finally:
        part.unlink(missing_ok=True)
        listing.unlink(missing_ok=True)


def named(chapters: list[Chapter], names: list[str], date: str | None = None) -> tuple[str, str]:
    """The match's name, its hosted page's, and its day: `date` (any form `teams.parse_date` reads), else the camera's."""
    first = chapters[0]
    day = teams.parse_date(date) if date else first.stamp.date().isoformat() if first.stamp else teams.recording_date(first.path)
    return matches.address({"date": day, "name": "", "teams": [{"name": n} for n in names]}), day


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a match from the camera's card, named like its hosted page.")
    parser.add_argument("source", type=Path, nargs="+", help="The card, a folder of chapters, one video or several")
    parser.add_argument("--teams", required=True, help='"NAME_1[:COLOUR],NAME_2[:COLOUR]", the first on the left at the first rally')
    parser.add_argument("--from", dest="start", help="Where the match starts in the joined video, m:ss or h:mm:ss")
    parser.add_argument("--to", dest="end", help="Where it ends")
    parser.add_argument("--date", help="The match's date. Default: the camera's")
    parser.add_argument("--recording", type=int, help="Which recording, when the card holds several")
    parser.add_argument("--data", type=Path, default=Path("data/matches"))
    parser.add_argument("--out", type=Path, default=Path("outputs/matches"))
    args = parser.parse_args()

    try:
        names = teams.parse_teams(args.teams)
        start, end = [teams.seconds(t) if t else None for t in (args.start, args.end)]
    except ValueError as error:
        parser.error(str(error))
    if not all(name for name, _ in names):
        parser.error("--teams needs both teams' names")
    if args.date and not teams.parse_date(args.date):
        parser.error(f"Not a date: {args.date!r} (use YYYY-MM-DD)")
    found = videos(args.source)
    if not found:
        parser.error(f"No video in {' '.join(map(str, args.source))}")
    groups = recordings([probe(p) for p in found])
    if len(groups) > 1 and not args.recording:
        parser.error(f"{len(groups)} recordings: {describe(groups)}. Choose one with --recording.")
    if args.recording and not 1 <= args.recording <= len(groups):
        parser.error(f"No recording {args.recording}: {describe(groups)}")
    chapters = groups[(args.recording or 1) - 1]
    if start and start >= (end or sum(c.duration for c in chapters)):
        parser.error("--from is past the end")

    name, day = named(chapters, [n for n, _ in names], args.date)
    target = args.data / name / f"{name}.mp4"
    if target.exists():
        parser.error(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    # The video may need its size again while its index moves to the front.
    needed = 2 * sum(c.path.stat().st_size for c in chapters)
    if shutil.disk_usage(target.parent).free < needed:
        parser.error(f"{needed / 1e9:.0f} GB free needed in {target.parent}")

    join(chapters, target, start, end, args.out.parent / TIMINGS if args.out.name == "matches" else None)
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    files.write_text(out / "teams.json", json.dumps({"teams": [{"name": n, "colour": c} for n, c in names], "date": day}, indent=2, ensure_ascii=False) + "\n")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(min(3.0, probe(target).duration / 2)), "-i", str(target), "-frames:v", "1", "-vf", "scale=1280:-1", "-y", str(out / "start.jpg")], check=True)
    print(f"{target}\n{names[0][0]} must be on the left at the first rally: check {out / 'start.jpg'}")
    print(f"Next: uv run python -m volleyball_stats.court auto {target} --out {out / 'court.json'}")
    print(f"then: uv run python -m volleyball_stats.match {target} --court {out / 'court.json'} --players")


if __name__ == "__main__":
    main()
