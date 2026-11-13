"""The app's log: what its server prints (its errors' tracebacks) kept in a file as well, for the page to show it
(`/app/log`) when the app runs from its shortcut, with no terminal to read it in."""

import sys
import threading
import time
from pathlib import Path

# Beyond it, the log keeps only its last KEEP_BYTES when the server starts.
MAX_BYTES = 2_000_000
KEEP_BYTES = 500_000


class Tee:
    """A stream writing to `stream` and appending to `file`, one write at a time across threads."""

    def __init__(self, stream, file, lock: threading.Lock) -> None:
        self.stream, self.file, self.lock = stream, file, lock

    def write(self, text: str) -> int:
        with self.lock:
            try:
                self.file.write(text)
                self.file.flush()
            except (OSError, ValueError):
                pass
        if self.stream is None:
            return len(text)
        try:
            return self.stream.write(text)
        except (OSError, ValueError):
            # No terminal (the shortcut's headless start): the file holds it.
            return len(text)

    def flush(self) -> None:
        if self.stream is not None:
            try:
                self.stream.flush()
            except (OSError, ValueError):
                pass

    def __getattr__(self, name: str):
        return getattr(self.stream, name)


def start(path: Path) -> None:
    """Copies the server's output to `path` from now on, trimmed first when it grew too long.

    ponytail: only Python's own output; a command it runs writing to the terminal itself is not kept (the pipeline's
    jobs have their own logs, jobs.py)."""
    if isinstance(sys.stderr, Tee):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            with open(path, "rb") as f:
                f.seek(-KEEP_BYTES, 2)
                kept = f.read()
            path.write_bytes(kept[kept.find(b"\n") + 1 :])
        file = open(path, "a", encoding="utf-8", errors="replace")
    except OSError:
        return
    file.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    lock = threading.Lock()
    sys.stdout = Tee(sys.stdout, file, lock)
    sys.stderr = Tee(sys.stderr, file, lock)
