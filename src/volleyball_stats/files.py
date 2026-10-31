"""Files written whole: through a temporary file beside them that then takes their place, so a crash
or Ctrl+C mid-write leaves the previous file and a reader sees one or the other, never half.

ponytail: no fsync, a power cut may still lose the last write; fsync the file and its folder if
that matters.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


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
