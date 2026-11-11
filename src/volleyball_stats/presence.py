"""The app's open windows, for `stats` (the review's --with-window) to stop once its last one closes: each page says it
is open (/app/alive, every 30 s) and that it goes (/app/leaving, as it unloads). A reload or a match being opened leaves
and comes back within AFTER_LEAVING_S. Started otherwise (`stats browser`, `stats server`), Ctrl+C stops it."""

import os
import threading
import time
from collections.abc import Callable

# How long a page that left has to come back (a reload, the review of another match) before the app stops.
AFTER_LEAVING_S = 5.0
# A page heard from no more for so long is gone without saying it (a browser that crashed); a minimized window's
# timers may slow to once a minute, a sleeping one's longer.
SILENT_S = 30 * 60.0
# The time the first page has to show (the window opening, a restart's page coming back).
START_S = 60.0


class Presence:
    """The pages open, each by its id and when it was last heard from."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self.now = now
        self.started = now()
        self.pages: dict[str, float] = {}
        self.left_at: float | None = None
        self.lock = threading.Lock()

    def seen(self, page: str) -> None:
        with self.lock:
            self.pages[page] = self.now()

    def left(self, page: str) -> None:
        with self.lock:
            self.pages.pop(page, None)
            self.left_at = self.now()

    def closed(self) -> bool:
        """Whether every window has closed: none open, the last one gone AFTER_LEAVING_S ago, none ever within
        START_S."""
        now = self.now()
        with self.lock:
            self.pages = {page: at for page, at in self.pages.items() if now - at < SILENT_S}
            if self.pages:
                return False
            if self.left_at is not None and now - self.left_at < AFTER_LEAVING_S:
                return False
            return now - self.started >= START_S or self.left_at is not None


ON = False
PAGES = Presence()


def watch(may_stop: Callable[[], bool], lock=None) -> None:
    """With --with-window: the server stopped once its windows closed and `may_stop` (no job, no apply running)."""
    if not ON:
        return

    def run() -> None:
        while True:
            time.sleep(1)
            if PAGES.closed() and may_stop():
                print("Its last window closed: stopped.", flush=True)
                if lock:
                    lock.acquire()
                os._exit(0)

    threading.Thread(target=run, daemon=True).start()
