"""The app's open windows, for `stats` (the review's --with-window) to stop once its last one closes: each page says it
is open (/app/alive, every 30 s) and that it goes (/app/leaving, as it unloads). A reload or a match being opened leaves
and comes back within AFTER_LEAVING_S. Started by the Mac app (--with-app), it stops once that app quits: its stdin, the
app's pipe, ends; its window closed only hides it. Started otherwise (`stats browser`, `stats server`), Ctrl+C stops it."""

import os
import sys
import threading
import time
from collections.abc import Callable

# How long a page that left has to come back (a reload, the review of another match) before the app stops: a reload
# after an apply comes while the server still works (the pictures), 5 s were too few (13 Nov).
AFTER_LEAVING_S = 30.0
# A page heard from no more for so long is gone without saying it (a browser that crashed); a minimized window's
# timers may slow to once a minute, a sleeping one's longer.
SILENT_S = 30 * 60.0
# The time the first page has to show once the server listens (the window opening, a restart's page coming back): from
# Windows, a page polling a port not listening yet may wait some 20 s per try; 60 s from the process's start were too few
# for a review taking 20-35 s to load (18 Nov).
START_S = 120.0


class Presence:
    """The pages open, each by its id and when it was last heard from."""

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self.now = now
        self.started = now()
        self.pages: dict[str, float] = {}
        self.left_at: float | None = None
        self.lock = threading.Lock()

    def listening(self) -> None:
        """The server answers from now: the first page's time counts from here."""
        with self.lock:
            self.started = self.now()

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
APP = False
PAGES = Presence()


def app_quit() -> Callable[[], bool]:
    """Whether the app that started this server has quit: its pipe on stdin, read to its end aside."""
    ended = threading.Event()

    def read() -> None:
        try:
            sys.stdin.buffer.read()
        except (OSError, ValueError):
            pass
        ended.set()

    threading.Thread(target=read, daemon=True).start()
    return ended.is_set


def watch(may_stop: Callable[[], bool], lock: Callable[[], object] | None = None) -> None:
    """With --with-window or --with-app: the server stopped once its windows closed or its app quit and `may_stop` (no
    job, no apply running), the lock `lock` gives taken first (no answer being saved). Called as the server starts
    listening."""
    if APP:
        gone, why = app_quit(), "Its app quit"
    elif ON:
        PAGES.listening()
        gone, why = PAGES.closed, "Its last window closed"
    else:
        return

    def run() -> None:
        while True:
            time.sleep(1)
            if gone() and may_stop():
                print(f"{why}: stopped.", flush=True)
                held = lock and lock()
                if held:
                    held.acquire()
                os._exit(0)

    threading.Thread(target=run, daemon=True).start()
