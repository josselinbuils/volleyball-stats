"""Which code made a match's analysis: a fingerprint of the pipeline's modules and learned models, kept with the match
(analysis.json) at the end of each run, for the app to tell the matches the code changed under ("Nouvelles règles").
"""

import ast
import hashlib
import json
from pathlib import Path

from volleyball_stats import files

FILE = "analysis.json"
PACKAGE = Path(__file__).resolve().parent
# The pipeline's entry; web.py makes the pages, not the analysis (scoreboard.py only reads a CSV with it).
ENTRY, OUTSIDE = "match", {"web"}
# What was read, by the files' change times: the fingerprint is asked at every load of the list.
_seen: dict[tuple, object] = {}


def modules(entry: str = ENTRY) -> list[Path]:
    """The package's modules `entry` imports at their top, and theirs, but OUTSIDE."""
    key = (entry, *((p.name, p.stat().st_mtime_ns) for p in sorted(PACKAGE.glob("*.py"))))
    if key not in _seen:
        _seen[key] = imported(entry)
    return _seen[key]


def imported(entry: str) -> list[Path]:
    found, todo = set(), [entry]
    while todo:
        name = todo.pop()
        path = PACKAGE / f"{name}.py"
        if name in found or name in OUTSIDE or not path.exists():
            continue
        found.add(name)
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ImportFrom) and node.module == "volleyball_stats":
                todo += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("volleyball_stats."):
                todo.append(node.module.split(".")[1])
    return sorted(PACKAGE / f"{n}.py" for n in found)


def code(path: Path) -> str:
    """A module's code without its comments, layout or docstrings: changing those changes no result."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def fingerprint(match: Path | None = None) -> str:
    """The pipeline's code and the learned order of who touched the ball (ranker.py), with the play model of `match`'s
    folder (playing.py). ponytail: one fingerprint for every step, so a change to one step reruns them all; a step's own
    would rerun only from it."""
    from volleyball_stats import playing, ranker

    parts = [*modules(), ranker.WEIGHTS]
    key = tuple((p, p.stat().st_mtime_ns, p.stat().st_size) for p in parts if p.exists())
    if key not in _seen:
        digest = hashlib.sha256()
        for path, *_ in key:
            digest.update(path.name.encode())
            digest.update((code(path) if path.suffix == ".py" else path.read_text()).encode())
        _seen[key] = digest.hexdigest()[:16]
    play = playing.stamp(playing.weights(match)) if match else None
    return f"{_seen[key]}-{play or 0}"


def made_by(match: Path) -> str | None:
    """The fingerprint of the code that made `match`'s analysis, None when unknown (made before 14 Nov 2026)."""
    path = match / FILE
    try:
        return json.loads(path.read_text())["code"]
    except (OSError, ValueError, KeyError):
        return None


def write(match: Path, made: str) -> None:
    files.write_text(match / FILE, json.dumps({"code": made}) + "\n")
