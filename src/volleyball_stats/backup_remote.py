"""The server's side of `backup.snapshot`: the day's copy started as the one before, hard-linked, so it holds every
match while taking no room. Sent to the server's python3 (3.8) on stdin, so it imports nothing of the project.

    python3 - ROOT DAY PREVIOUS
"""

import os
import shutil
import sys


def snapshot(root, day, previous):
    """ROOT/DAY made as ROOT/PREVIOUS with each file hard-linked, unless it exists; of two machines at once, one makes it.
    rsync writes a changed file anew, so the copies before keep theirs."""
    target, source = os.path.join(root, day), os.path.join(root, previous)
    if os.path.exists(target) or not os.path.isdir(source):
        return
    part = os.path.join(root, ".%s.%d" % (day, os.getpid()))
    try:
        for folder, dirs, names in os.walk(source):
            here = os.path.join(part, os.path.relpath(folder, source))
            os.makedirs(here)
            shutil.copystat(folder, here)
            for name in names:
                path = os.path.join(folder, name)
                if os.path.islink(path):
                    os.symlink(os.readlink(path), os.path.join(here, name))
                else:
                    os.link(path, os.path.join(here, name))
        os.rename(part, target)
    except OSError:
        # Another machine made it first.
        if not os.path.exists(target):
            raise
    finally:
        shutil.rmtree(part, ignore_errors=True)


if __name__ == "__main__":
    snapshot(*sys.argv[1:4])
