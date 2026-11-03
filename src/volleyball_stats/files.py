"""Files written whole: through a temporary file beside them that then takes their place, so a crash
or Ctrl+C mid-write leaves the previous file and a reader sees one or the other, never half.

ponytail: no fsync, a power cut may still lose the last write; fsync the file and its folder if
that matters.
"""

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

# Beside a match's outputs: what they were made from.
SOURCE = "source.json"


@contextmanager
def replacing(path: Path, mode: str = "w", **kwargs) -> Iterator[IO]:
    """`path` opened for writing (`mode` and `kwargs` as `open`'s), in place once the block ends."""
    # One temporary file per process and thread: the review server writes from several threads.
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(temporary, mode, **kwargs) as f:
            yield f
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    with replacing(path) as f:
        f.write(text)


def write_bytes(path: Path, data: bytes) -> None:
    with replacing(path, "wb") as f:
        f.write(data)


def aliases(match: Path) -> list[str]:
    """The names `match` had before (rename.py), which viewers' reports and choices may still carry."""
    path = match / SOURCE
    return json.loads(path.read_text()).get("aliases", []) if path.exists() else []


def write_source(match: Path, video: Path, court: Path, squad: tuple[int, int] | None = None) -> None:
    """What `match` was made from, in its SOURCE: the review opens it from that."""
    given = {"video": str(video), "court": str(court), "squad": f"{squad[0]},{squad[1]}" if squad else None, "aliases": aliases(match)}
    write_text(match / SOURCE, json.dumps(given, indent=1) + "\n")
