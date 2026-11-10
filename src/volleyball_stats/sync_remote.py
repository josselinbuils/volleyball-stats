"""The server's side of `sync`: each match's version in `ROOT/claims/MATCH.json`, read and changed under a lock (the ssh
command runs it under flock). Sent to the server's python3 (3.8) on stdin, so it imports nothing of the project.

    python3 - ROOT OP MATCH MACHINE [BASE] [FORCE]

Prints the match's record as JSON with `ok`: whether the operation went through. No machine holds a match: a push goes
from the server's version, and only one machine copies a match at a time (`pushing`, for COPY_S at most).
"""

import json
import os
import re
import subprocess
import sys
import time

# A copy's name: its day, and its hour since copies are hourly (backup.COPY).
DAY = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2})?$")
# A copy that takes longer than this was cut off: another machine may copy then (backup.TIMEOUT_S).
COPY_S = 3600
# The server's copies a machine's "keep this one" replaced, kept here by hard links.
ASIDE = "aside"


def read(root, match):
    path = os.path.join(root, "claims", match + ".json")
    found = {"version": 0, "pushed": None, "pushedBy": None, "pushing": None}
    if os.path.exists(path):
        with open(path) as f:
            found.update({k: v for k, v in json.load(f).items() if k in found})
    return found


def write(root, match, record):
    folder = os.path.join(root, "claims")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, match + ".json")
    with open(path + ".tmp", "w") as f:
        json.dump({k: v for k, v in record.items() if k != "day"}, f)
    os.replace(path + ".tmp", path)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def newest(root):
    """Each match's newest dated copy, by name: its day."""
    found = {}
    for day in sorted(d for d in os.listdir(root) if DAY.match(d)) if os.path.isdir(root) else []:
        for name in os.listdir(os.path.join(root, day)):
            if os.path.exists(os.path.join(root, day, name, "source.json")):
                found[name] = day
    return found


def run(root, op, match, machine, base=0, force=False):
    """`status` gives the match's record; `begin` says whether `machine` may copy the match from `base` (the server's
    version, or any with `force`, the server's copy then set aside first) and marks it copying; `commit` moves the
    version on after the copy; `list` gives every match with a copy, its day and record."""
    if op == "list":
        days = newest(root)
        return {"ok": True, "matches": {name: dict(read(root, name), day=day) for name, day in days.items()}}
    record = dict(read(root, match), day=newest(root).get(match))
    pushing = record["pushing"]
    busy = bool(pushing and pushing["machine"] != machine and time.time() - pushing["at"] < COPY_S)
    if op == "status":
        return dict(record, ok=True, busy=busy)
    if op == "begin":
        if busy or (record["version"] != base and not force):
            return dict(record, ok=False, busy=busy)
        if record["version"] != base and record["day"]:
            # "Keep this one": the server's copy stays, beside the dated ones.
            aside = os.path.join(root, ASIDE, time.strftime("%Y%m%d-%H%M%S") + "-v" + str(record["version"]))
            os.makedirs(aside, exist_ok=True)
            subprocess.run(["cp", "-al", os.path.join(root, record["day"], match), aside], check=True)
        record["pushing"] = {"machine": machine, "at": time.time()}
        write(root, match, record)
        return dict(record, ok=True, busy=False)
    if op == "commit":
        if not pushing or pushing["machine"] != machine:
            return dict(record, ok=False, busy=busy)
        record.update(version=record["version"] + 1, pushed=now(), pushedBy=machine, pushing=None)
        write(root, match, record)
        return dict(record, ok=True, busy=False)
    raise ValueError(op)


if __name__ == "__main__":
    args = sys.argv[1:]
    print(json.dumps(run(args[0], args[1], args[2], args[3], int(args[4]) if len(args) > 4 else 0, len(args) > 5 and args[5] == "force")))
