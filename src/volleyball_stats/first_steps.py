"""The guided first run: the steps from the club to a shared match, each ticked once done, kept in FILE so a step done
once stays ticked (a match deleted later unticks nothing)."""

import json
from pathlib import Path

from volleyball_stats import club_settings, files, identity, matches, netlify
from volleyball_stats.review_answers import log_of

FILE = "first_steps.json"
STEPS = ("club", "guide", "framing", "import", "analysis", "review", "share")
# What a screen marks seen itself: the recording guide opened, the list's card hidden, the review's intro read.
SEEN = ("guide", "hidden", "review_intro")


def reviewed(match: Path) -> bool:
    """Whether the review gave `match` names or applied answers."""
    return any(e.get("applied", True) for e in log_of(match)) or bool(files.read_json(match / identity.NAMES, {}).get("players"))


def found(outputs: Path, listed: list[dict], seen: dict) -> set[str]:
    """The steps done as the files show them. The guide counts read and the framing tested once a match was analysed or
    imported: who got there needs neither."""
    from volleyball_stats import placement

    club = club_settings.read(outputs / "club")
    imported, ready = bool(listed), any(m.get("ready") for m in listed)
    done = {
        "club": bool(club and club.get("name") and club.get("teams")),
        "guide": bool(seen.get("guide")) or ready,
        "framing": (outputs / placement.FOLDER / placement.VERDICT).exists() or imported,
        "import": imported,
        "analysis": ready,
        "review": any(reviewed(outputs / "matches" / m["path"]) for m in listed if m.get("ready")),
        "share": bool(matches.online(outputs / "matches")) or bool(netlify.published(outputs).get("matches")) or (outputs / matches.EXPORT).exists(),
    }
    return {k for k, v in done.items() if v}


def state(outputs: Path, listed: list[dict]) -> dict:
    """The steps done (`done`, in STEPS' order), whether the card is hidden, whether the review's intro was read; a step
    newly done is kept."""
    path = outputs / FILE
    saved = files.read_json(path, {})
    kept = set(saved.get("done", []))
    done = kept | found(outputs, listed, saved)
    if done != kept:
        files.write_text(path, json.dumps({**saved, "done": [s for s in STEPS if s in done]}, indent=2) + "\n")
    return {"done": [s for s in STEPS if s in done], "hidden": bool(saved.get("hidden")), "review_intro": bool(saved.get("review_intro")) or "review" in done}


def mark(outputs: Path, key: str, value: bool = True) -> None:
    """`key` (one of SEEN) set to `value`; ValueError for another."""
    if key not in SEEN:
        raise ValueError(key)
    path = outputs / FILE
    files.write_text(path, json.dumps({**files.read_json(path, {}), key: value}, indent=2) + "\n")
