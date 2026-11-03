"""Files written whole: through a temporary file beside them that then takes their place, so a crash
or Ctrl+C mid-write leaves the previous file and a reader sees one or the other, never half.

ponytail: no fsync, a power cut may still lose the last write; fsync the file and its folder if
that matters.
"""

import hashlib
import inspect
import json
import os
import threading
import types
from collections.abc import Callable, Iterable, Iterator
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


def cache_stamp(video: Path | None, sources: Iterable[Path], extra: str = "") -> str:
    """What a result cut from `video` depends on: the video itself (size and date), the code making
    it (`sources`, any change counts), the locked dependencies and `extra`. A cache under another
    stamp is out of date."""
    digest = hashlib.sha256(extra.encode())
    if video is not None and video.exists():
        found = video.stat()
        digest.update(f"{found.st_size}:{found.st_mtime_ns}".encode())
    for path in [*sources, Path(__file__).parents[2] / "uv.lock"]:
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def code_text(*functions: Callable) -> str:
    """The source of `functions` and of this package's functions and classes they use, in turn, with
    the values of the constants they read: what a stamp needs to see them change, and nothing else
    of their modules. What they import inside their body counts only if given as well."""
    seen: set = set()
    parts: set[str] = set()

    def visit(function: Callable) -> None:
        if function in seen:
            return
        seen.add(function)
        parts.add(inspect.getsource(function))
        codes = [function.__code__]
        while codes:
            code = codes.pop()
            codes += [c for c in code.co_consts if isinstance(c, types.CodeType)]
            for name in code.co_names:
                value = function.__globals__.get(name)
                if isinstance(value, (bool, int, float, str, tuple, Path)):
                    parts.add(f"{name}={value}")
                elif inspect.isclass(value) and value.__module__.startswith("volleyball_stats"):
                    parts.add(inspect.getsource(value))
                elif inspect.isfunction(value) and value.__module__.startswith("volleyball_stats"):
                    visit(value)

    for function in functions:
        visit(function)
    return "\n".join(sorted(parts))
