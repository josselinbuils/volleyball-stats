"""The matches kept in step between machines through the hosting server, outside its website, the videos aside
(`data_sync`). A push is the backup (`backup.py`); one machine works on a match at a time: the review claims it on
opening, and a push is refused when another machine holds it or the server's copy is newer than the one this machine
started from. Pulling a match brings its newest copy, this machine's unpushed changes kept aside in `backup-sync-*`,
and what the outputs folder lacks of the courts, lens, sponsors and roster.

    uv run python -m volleyball_stats.sync setup root@HOST ~/.ssh/KEY   # a machine with no match yet
    uv run python -m volleyball_stats.sync list
    uv run python -m volleyball_stats.sync pull MATCH... | --all
    uv run python -m volleyball_stats.sync push outputs/matches/MATCH
"""

import argparse
import json
import os
import shlex
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from volleyball_stats import backup, files, matches

# Per machine, not copied: the server's version this machine's copy started from, and its files' signature then.
STATE = backup.STATE
SERVER = "server.json"
REMOTE = Path(__file__).with_name("sync_remote.py")
DEFAULT_OUTPUTS = Path("outputs")


class Elsewhere(RuntimeError):
    """The match is not this machine's to push: another holds it, or the server's copy is newer."""

    def __init__(self, claim: dict):
        self.claim = claim
        super().__init__(f"{claim['machine']} has this match" + (f" (copy at {claim['at']})" if claim.get("at") else ""))


def machine() -> str:
    return os.environ.get("VOLLEYBALL_MACHINE") or socket.gethostname().removesuffix(".local")


def server(outputs: Path) -> dict | None:
    """The hosting server's `upload` and `key`: outputs/server.json's, else a match's publish.json's."""
    if (outputs / SERVER).exists():
        return json.loads((outputs / SERVER).read_text())
    for path in sorted((outputs / "matches").glob(f"*/{matches.PUBLISH}")):
        config = json.loads(path.read_text())
        if config.get("upload") and config.get("key"):
            return {"upload": config["upload"], "key": config["key"]}
    return None


def remote(config: dict, op: str, match: str = "-", base: int = 0, force: bool = False, root: str = backup.ROOT) -> dict:
    """`sync_remote.run` on the server, under its lock."""
    host, ssh = backup.connection(config)
    command = f"mkdir -p {shlex.quote(root)} && chmod 700 {shlex.quote(root)} && flock {shlex.quote(root + '/.claims.lock')} python3 - " + " ".join(
        shlex.quote(str(a)) for a in (root, op, match, machine(), base, "force" if force else "-")
    )
    run = subprocess.run([*ssh, host, command], input=REMOTE.read_text(), capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    return json.loads(run.stdout)


def local(match: Path) -> dict:
    path = match / STATE
    return json.loads(path.read_text()) if path.exists() else {"version": 0, "signature": None}


def changed(match: Path) -> bool:
    """Whether the match changed here since this machine last pushed or pulled it."""
    return match.exists() and any(match.iterdir()) and local(match)["signature"] != list(backup.signature([match]))


def remember(match: Path, version: int, signature: tuple[int, float]) -> None:
    files.write_text(match / STATE, json.dumps({"version": version, "signature": list(signature)}) + "\n")


def shown(claim: dict, match: Path) -> dict:
    """What the review says of a match held elsewhere: by which machine, its copy's time, whether this one changed it."""
    at = claim.get("pushed") or claim.get("since")
    other = claim["owner"] if claim["owner"] not in (None, machine()) else claim.get("pushedBy") or claim["owner"]
    return {"machine": other or "?", "at": at[11:16] if at else None, "changed": changed(match)}


def claim(match: Path) -> dict | None:
    """Takes `match` for this machine on the server. What the review shows when another machine holds it or the server's
    copy is newer than this one; None otherwise, and when the server cannot be reached (the next push says it)."""
    config = server(files.root(match))
    if config is None:
        return None
    try:
        found = remote(config, "claim", match.name)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return None
    return None if found["ok"] and found["version"] == local(match)["version"] else shown(found, match)


def push(match: Path) -> None:
    """The match's backup, if this machine may: Elsewhere otherwise."""
    config = json.loads((match / matches.PUBLISH).read_text())
    base = local(match)["version"]
    found = remote(config, "begin", match.name, base)
    if not found["ok"]:
        raise Elsewhere(shown(found, match))
    signature = backup.signature([match])
    merge_roster(match.parent, config)
    backup.backup(match)
    # ponytail: another machine taking the match between `begin` and here may pull a half-written copy; a lock held
    # across the copy would close it.
    done = remote(config, "commit", match.name, base)
    if not done["ok"]:
        raise Elsewhere(shown(done, match))
    remember(match, done["version"], signature)


def take(match: Path) -> None:
    """`match` taken for this machine: the server's copy first, if it has one."""
    outputs = files.root(match)
    config = server(outputs)
    if config is None:
        raise LookupError("no server")
    if match.name in remote(config, "list")["matches"]:
        pull(match.name, outputs)
    remote(config, "claim", match.name, force=True)


def listing(outputs: Path) -> dict[str, dict]:
    """The matches with a copy on the server: their day, claim and version. Empty without a server."""
    config = server(outputs)
    return remote(config, "list")["matches"] if config else {}


def rsync(config: dict, source: str, target: Path, *options: str) -> None:
    host, ssh = backup.connection(config)
    run = subprocess.run(["rsync", "-rt", *options, "-e", " ".join(ssh), f"{host}:{source}", str(target)], capture_output=True, text=True, timeout=backup.TIMEOUT_S)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"rsync: {run.returncode}")


def pull(name: str, outputs: Path = DEFAULT_OUTPUTS) -> Path:
    """The match `name` brought from the server into outputs/matches/; this machine's unpushed changes to it kept in
    its `backup-sync-<time>` folder. LookupError if the server has no copy."""
    config = server(outputs)
    if config is None:
        raise LookupError("no server: sync setup")
    found = remote(config, "list")["matches"]
    if name not in found:
        raise LookupError(name)
    match = outputs / "matches" / name
    match.mkdir(parents=True, exist_ok=True)
    aside = ["--backup", f"--backup-dir=backup-sync-{time.strftime('%Y%m%d-%H%M%S')}"] if changed(match) else []
    day = f"{backup.ROOT}/{found[name]['day']}"
    rsync(config, f"{day}/{name}/", match, "--delete", *[f"--exclude={p}" for p in backup.SKIP], *aside)
    remember(match, found[name]["version"], backup.signature([match]))
    relative_copies(match)
    # What this machine lacks of the files beside the matches; its own stay.
    for source, target in ((f"{day}/courts/", outputs / "courts"), (f"{day}/lens.json", outputs / "lens.json"), (f"{day}/sponsors/", backup.SPONSORS)):
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            rsync(config, source, target, "--ignore-existing")
        except RuntimeError:
            # Not in that copy.
            pass
    merge_roster(outputs / "matches", config, pulled=name, claims=found)
    return match


def relative_copies(match: Path) -> None:
    """publish.json's video copies under data/matches/, where the other machine's paths do not exist here."""
    path = match / matches.PUBLISH
    if not path.exists():
        return
    config = json.loads(path.read_text())
    moved = False
    for key in ("light", "av1", "small"):
        value = config.get(key)
        if value and not Path(value).expanduser().exists() and "/data/matches/" in value:
            config[key] = "data/matches/" + value.split("/data/matches/", 1)[1]
            moved = True
    if moved:
        files.write_text(path, json.dumps(config, indent=1, ensure_ascii=False) + "\n")


def merged(mine: list[dict], theirs: list[dict], ours: Callable[[str], bool]) -> list[dict]:
    """One roster from two: each match's players and embeddings from this machine's roster where `ours(match)`, else
    from the server's when it has that match; a jersey number from this machine's first."""
    here = {m for p in mine for m in p["vectors"]}
    there = {m for p in theirs for m in p["vectors"]}
    out: dict[tuple, dict] = {}
    jerseys = {(p.get("team"), p["name"].casefold()): p.get("jersey") for p in theirs}
    jerseys.update({(p.get("team"), p["name"].casefold()): p.get("jersey") for p in mine if p.get("jersey") is not None})
    for match in sorted(here | there):
        for p in mine if (ours(match) and match in here) or match not in there else theirs:
            if match not in p["vectors"]:
                continue
            key = (p.get("team"), p["name"].casefold())
            player = out.setdefault(key, {**{k: v for k, v in p.items() if k != "vectors"}, "jersey": jerseys.get(key), "vectors": {}})
            player["vectors"][match] = p["vectors"][match]
    return list(out.values())


def merge_roster(folder: Path, config: dict, pulled: str | None = None, claims: dict | None = None) -> None:
    """outputs/roster.json joined with the server's newest: each match's names from the machine that holds it (this one
    for a match it has and nobody else holds), the match just `pulled` from the server's."""
    path = folder.parent / "roster.json"
    host, ssh = backup.connection(config)
    command = f"f=$(ls -1d {backup.ROOT}/*/roster.json 2>/dev/null | grep -E '/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}/roster.json$' | tail -1); if [ -n \"$f\" ]; then cat \"$f\"; else echo '{{\"players\": []}}'; fi"
    run = subprocess.run([*ssh, host, command], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    theirs = json.loads(run.stdout)["players"]
    mine = json.loads(path.read_text())["players"] if path.exists() else []
    claims = claims if claims is not None else remote(config, "list")["matches"]
    me = machine()

    def ours(match: str) -> bool:
        if match == pulled:
            return False
        owner = claims.get(match, {}).get("owner")
        return owner == me or (owner is None and (folder / match).exists())

    out = merged(mine, theirs, ours)
    if out != mine:
        files.write_text(path, json.dumps({"players": out}, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Keep the matches in step between machines through the hosting server.")
    parser.add_argument("--outputs", type=Path, default=DEFAULT_OUTPUTS)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="The server, for a machine with no match yet")
    setup.add_argument("host", help="root@HOST")
    setup.add_argument("key", help="The ssh key, e.g. ~/.ssh/id_ed25519_ovh")
    commands.add_parser("list", help="The matches on the server")
    pulling = commands.add_parser("pull", help="Bring matches from the server")
    pulling.add_argument("names", nargs="*")
    pulling.add_argument("--all", action="store_true", help="Every match on the server")
    pushing = commands.add_parser("push", help="Send a match to the server")
    pushing.add_argument("match", type=Path)
    args = parser.parse_args()
    if args.command == "setup":
        args.outputs.mkdir(parents=True, exist_ok=True)
        files.write_text(args.outputs / SERVER, json.dumps({"upload": f"{args.host}:", "key": args.key}) + "\n")
    elif args.command == "list":
        for name, c in sorted(listing(args.outputs).items()):
            here = args.outputs / "matches" / name
            state = "not here" if not here.exists() else f"here v{local(here)['version']}" + (", changed" if changed(here) else "")
            print(f"{name}  v{c['version']}  {c['owner'] or 'nobody'}  copy {c['day']}  ({state})")
    elif args.command == "pull":
        found = listing(args.outputs)
        names = sorted(found) if args.all else args.names
        if not names:
            parser.error("name matches or pass --all")
        for name in names:
            here = args.outputs / "matches" / name
            # This machine's own and those it has up to date.
            if args.all and here.exists() and (found[name]["owner"] == machine() or local(here)["version"] >= found[name]["version"]):
                continue
            print(pull(name, args.outputs), flush=True)
    else:
        try:
            push(args.match)
        except Elsewhere as error:
            parser.exit(1, f"{error}: open it in the review to take it here\n")
        print("pushed", flush=True)


if __name__ == "__main__":
    main()
