"""The server's side of `sync`: each match's claim and version in `ROOT/claims/MATCH.json`, read and changed under a lock
(the ssh command runs it under flock). Sent to the server's python3 (3.8) on stdin, so it imports nothing of the project.

    python3 - ROOT OP MATCH MACHINE [BASE] [FORCE]

Prints the claim as JSON with `ok`: whether the operation went through.
"""

import json
import os
import re
import sys
import time

DAY = re.compile(r"\d{4}-\d{2}-\d{2}$")


def read(root, match):
    path = os.path.join(root, "claims", match + ".json")
    if not os.path.exists(path):
        return {"owner": None, "since": None, "version": 0, "pushed": None, "pushedBy": None}
    with open(path) as f:
        return json.load(f)


def write(root, match, claim):
    folder = os.path.join(root, "claims")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, match + ".json")
    with open(path + ".tmp", "w") as f:
        json.dump(claim, f)
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
    """`claim` takes the match for `machine` if no other machine holds it, or with `force`; `begin` says whether
    `machine` may push from `base`, taking a match nobody holds; `commit` moves the version past `base` after a push;
    `list` gives every match with a copy, its day and claim."""
    if op == "list":
        days = newest(root)
        return {"ok": True, "matches": {name: dict(read(root, name), day=day) for name, day in days.items()}}
    claim = dict(read(root, match), day=newest(root).get(match))
    free = claim["owner"] in (None, machine)
    if op == "claim":
        if free or force:
            if claim["owner"] != machine:
                claim.update(owner=machine, since=now())
            write(root, match, {k: v for k, v in claim.items() if k != "day"})
            return dict(claim, ok=True)
        return dict(claim, ok=False)
    if op == "begin":
        ok = free and claim["version"] == base
        if ok and claim["owner"] is None:
            claim.update(owner=machine, since=now())
            write(root, match, {k: v for k, v in claim.items() if k != "day"})
        return dict(claim, ok=ok)
    if op == "commit":
        if claim["owner"] == machine and claim["version"] == base:
            claim.update(version=base + 1, pushed=now(), pushedBy=machine)
            write(root, match, {k: v for k, v in claim.items() if k != "day"})
            return dict(claim, ok=True)
        return dict(claim, ok=False)
    raise ValueError(op)


if __name__ == "__main__":
    args = sys.argv[1:]
    print(json.dumps(run(args[0], args[1], args[2], args[3], int(args[4]) if len(args) > 4 else 0, len(args) > 5 and args[5] == "force")))
