"""Rename a match, everywhere on this machine and in its backups: by default to the name its date and teams give, its hosted page's.

    uv run python -m volleyball_stats.rename outputs/MATCH [NEW_NAME]

data/NEW/NEW.mp4 with the match's other video files, outputs/NEW/ with its own court; the old name stays an alias (files.SOURCE) so
that the viewers' reports and choices made under it still count. The hosted page follows on its next upload (matches.host), with a
redirect from its old address (matches.build).
"""

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from volleyball_stats import backup, files, matches

ROSTER = "roster.json"
PORT = 8765


def target_name(match: Path) -> str | None:
    """The name teams.json gives `match`; None while a date or a team's name is missing."""
    path = match / "teams.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    if not saved.get("date") or not all(t.get("name") for t in saved.get("teams") or [{}]):
        return None
    return matches.address({"date": saved["date"], "name": "", "teams": saved["teams"]}) or None


def moved(path: Path, folder: Path, name: str | None = None) -> Path:
    """`path` moved into `folder`, under `name` if given."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (name or path.name)
    path.rename(target)
    return target


def rename_match(match: Path, new: str, data: Path | None = None) -> Path:
    """Moves the files of `match` under the name `new` and returns its new folder. ValueError, with nothing moved, if it cannot."""
    old, outputs = match.name, match.parent
    source = match / files.SOURCE
    if not source.exists() or not (match / "report.md").exists():
        raise ValueError(f"{match}: its pipeline has not ended")
    given = json.loads(source.read_text())
    video, court = Path(given["video"]), Path(given["court"])
    # Where its video is: in its own folder, or still directly in the data folder.
    data = data or (video.parent.parent if video.parent.name == old else video.parent)
    folder, target = data / new, outputs / new
    if new == old:
        raise ValueError(f"{match} is already named {new}")
    if not video.exists() or not court.exists():
        raise ValueError(f"{video} or {court} is missing")
    if target.exists() or folder.exists():
        raise ValueError(f"{target} or {folder} already exists")
    publish = match / matches.PUBLISH
    config = json.loads(publish.read_text()) if publish.exists() else {}
    copies = [key for key in ("light", "av1", "small") if config.get(key)]
    missing = [config[key] for key in copies if not Path(config[key]).expanduser().exists()]
    if missing:
        raise ValueError(f"{', '.join(missing)} missing")

    # Its folder holds what belongs to the match; else its video files are found by name.
    if video.resolve().parent == (data / old).resolve():
        (data / old).rename(folder)
        video = folder / video.name
    else:
        moved(video, folder)
        video = folder / video.name
        for other in sorted(data.glob(f"{old}_*")):
            moved(other, folder)
    video = video.rename(folder / f"{new}{video.suffix}")
    for key in copies:
        path = Path(config[key]).expanduser()
        path = moved(path, folder) if path.exists() else folder / path.name
        config[key] = str(path.resolve())
    # A court of its own goes with it; a gym's, in the library, stays for the next matches.
    own = outputs / "court"
    match.rename(target)
    if court.resolve().parent == (outputs / old).resolve():
        court = target / court.name
    elif court.resolve().parent == own.resolve() and court.stem == old:
        court = moved(court, target, "court.json")
    for other in sorted(p for p in own.glob(f"{old}*") if p.stem == old or p.stem.startswith(f"{old}_")):
        moved(other, target, "court.jpg" if other.suffix == ".jpg" and other.stem == old else None)
    if config:
        files.write_text(target / matches.PUBLISH, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    given["aliases"] = sorted({*given.get("aliases", []), old} - {new})
    files.write_text(target / files.SOURCE, json.dumps({**given, "video": str(video), "court": str(court)}, indent=1) + "\n")
    roster = outputs / ROSTER
    if roster.exists():
        saved = json.loads(roster.read_text())
        for player in saved["players"]:
            if old in player.get("vectors", {}):
                player["vectors"][new] = player["vectors"].pop(old)
        files.write_text(roster, json.dumps(saved, ensure_ascii=False) + "\n")
    shutil.rmtree(outputs / ".review_matches", ignore_errors=True)
    return target


def reviewing(name: str) -> bool:
    """Whether the review on this machine has the match `name` open."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/current", timeout=2) as response:
            return json.load(response).get("name") == name
    except (OSError, urllib.error.URLError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename a match, by default to the name its date and teams give.")
    parser.add_argument("match", type=Path)
    parser.add_argument("new", nargs="?", help="Default: its date and teams")
    args = parser.parse_args()
    new = args.new or target_name(args.match)
    if not new:
        parser.error(f"{args.match}: no date or a team without a name in teams.json")
    if reviewing(args.match.name):
        parser.error(f"The review has {args.match.name} open: change it from there, or stop the review")
    try:
        target = rename_match(args.match, new)
    except ValueError as error:
        parser.error(str(error))
    print(target)
    try:
        backup.rename_copies(target, args.match.name)
    except Exception as error:  # noqa: BLE001
        print(f"The backups keep the old name: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
