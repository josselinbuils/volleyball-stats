"""The matches kept in step between machines through the hosting server, outside its website, the videos aside
(`data_sync`). A push is the backup (`backup.py`), the review's own every 10 minutes only when this machine chose it (`auto`). Any
machine works on any match: the server keeps each match's version, and a push goes only from it. The review opening a match
(once this machine keeps its matches there, `active`) brings the server's newer copy when nothing changed here (`check`); when
both changed, the owner keeps one, the other set aside (`take`, `keep`). Pulling a match brings its newest copy, this machine's
unpushed changes kept aside in `backup-sync-*`, and what the outputs folder lacks of the courts, lens, club and roster.

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
from datetime import datetime
from collections.abc import Callable
from pathlib import Path

from volleyball_stats import backup, files, jobs, matches

# Per machine, not copied: the server's version this machine's copy started from, and its files' signature then.
STATE = backup.STATE
SERVER = "server.json"
# This machine's choice of automatic copies (`auto`).
BACKUP = "backup.json"
# The settings every machine shares, on the server beside the copies.
SETTINGS = "settings.json"
REMOTE = Path(__file__).with_name("sync_remote.py")
DEFAULT_OUTPUTS = Path("outputs")


class Conflict(RuntimeError):
    """The server's copy is newer than the one this machine started from: another machine pushed since."""

    def __init__(self, claim: dict):
        self.claim = claim
        super().__init__(f"newer on the server, from {claim['machine']}" + (f" (copy at {claim['at']})" if claim.get("at") else ""))


def machine() -> str:
    return os.environ.get("VOLLEYBALL_MACHINE") or socket.gethostname().removesuffix(".local")


# The hosting a match's publish.json shares with outputs/server.json.
HOSTING = ("upload", "key", "url", "site")


def server(outputs: Path) -> dict | None:
    """The hosting server's `upload`, `key`, `url` and `site`: outputs/server.json's (the app's "Serveur" tab), completed
    by a match's publish.json; None without an address and key."""
    given = (json.loads(p.read_text()) for p in sorted((outputs / "matches").glob(f"*/{matches.PUBLISH}")))
    found = next((c for c in given if c.get("upload") and c.get("key")), {})
    saved = json.loads((outputs / SERVER).read_text()) if (outputs / SERVER).exists() else {}
    merged = {k: v for k, v in {**{k: found.get(k) for k in HOSTING}, **saved}.items() if v}
    return merged if merged.get("upload") and merged.get("key") else None


def auto(outputs: Path) -> bool:
    """Whether this machine copies its matches to the server by itself: its own choice (`outputs/backup.json`), on by
    default once a server is set."""
    path = outputs / BACKUP
    if path.exists():
        return json.loads(path.read_text()).get("auto") is True
    return server(outputs) is not None


def shared_settings(config: dict, root: str | None = None) -> dict:
    """The settings the machines share, from the server; RuntimeError when it cannot be read."""
    root = root or backup.ROOT
    host, ssh = backup.connection(config)
    run = subprocess.run([*ssh, host, f"cat {shlex.quote(f'{root}/{SETTINGS}')} 2>/dev/null || echo '{{}}'"], capture_output=True, text=True, timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    return json.loads(run.stdout or "{}")


def share_settings(config: dict, changes: dict, root: str | None = None) -> None:
    """`changes` written into the settings the machines share; RuntimeError when the server cannot take them."""
    root = root or backup.ROOT
    host, ssh = backup.connection(config)
    path = shlex.quote(f"{root}/{SETTINGS}")
    command = f"mkdir -p {shlex.quote(root)} && chmod 700 {shlex.quote(root)} && cat > {path}.tmp && mv {path}.tmp {path}"
    text = json.dumps({**shared_settings(config, root), **changes})
    run = subprocess.run([*ssh, host, command], input=text, capture_output=True, text=True, timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")


def set_auto(outputs: Path, on: bool) -> None:
    """This machine's choice of automatic copies: each machine has its own."""
    files.write_text(outputs / BACKUP, json.dumps({"auto": on}) + "\n")


def active(outputs: Path) -> bool:
    """Whether this machine keeps its matches on the server: automatic copies on, `sync setup` run, or a match pushed or
    pulled. Otherwise the review reaches the server only when asked."""
    return auto(outputs) or (outputs / SERVER).exists() or any((outputs / "matches").glob(f"*/{STATE}"))


def remote(config: dict, op: str, match: str = "-", base: int = 0, force: bool = False, root: str | None = None, timeout: float = 60) -> dict:
    """`sync_remote.run` on the server, under its lock."""
    root = root or backup.ROOT
    host, ssh = backup.connection(config)
    command = f"mkdir -p {shlex.quote(root)} && chmod 700 {shlex.quote(root)} && flock {shlex.quote(root + '/.claims.lock')} python3 - " + " ".join(
        shlex.quote(str(a)) for a in (root, op, match, machine(), base, "force" if force else "-")
    )
    run = subprocess.run([*ssh, host, command], input=REMOTE.read_text(), capture_output=True, text=True, timeout=timeout)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    return json.loads(run.stdout)


def local(match: Path) -> dict:
    path = match / STATE
    return json.loads(path.read_text()) if path.exists() else {"version": 0, "signature": None}


def changed(match: Path) -> bool:
    """Whether the match changed here since this machine last pushed or pulled it."""
    return match.exists() and any(match.iterdir()) and local(match)["signature"] != list(backup.signature([match]))


def remember(match: Path, version: int, signature: tuple[int, float] | None) -> None:
    """The server's version this machine's copy now starts from, and its files' signature then: None leaves it changed,
    to send again."""
    files.write_text(match / STATE, json.dumps({"version": version, "signature": list(signature) if signature else None}) + "\n")


def shown(record: dict, match: Path) -> dict:
    """What the review says of the server's newer copy: which machine sent it, when, whether this machine changed its own."""
    at = record.get("pushed")
    return {"machine": record.get("pushedBy") or "?", "at": at[11:16] if at else None, "changed": changed(match)}


# The review waits this long for the server when it opens a match; unreached, it opens as it is (the next push checks).
CHECK_S = 15


def check(match: Path) -> dict | None:
    """The server's copy of `match` brought here when it is newer and nothing changed here since; what the review shows
    when both changed (`shown`), the owner to keep one. None otherwise, and when the server cannot be reached."""
    config = server(files.root(match))
    if config is None:
        return None
    try:
        found = remote(config, "status", match.name, timeout=CHECK_S)
        if not found["day"] or found["version"] == local(match)["version"]:
            return None
        if changed(match):
            return shown(found, match)
        pull(match.name, files.root(match))
    except (OSError, RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
        print(f"sync: {error}", flush=True)
    return None


def push(match: Path, force: bool = False) -> None:
    """The match's backup from the server's version: Conflict when another machine pushed since. With `force` (the owner
    keeping this machine's), from any version, the server's copy set aside there first. RuntimeError while another machine
    copies it."""
    config = json.loads((match / matches.PUBLISH).read_text())
    base = local(match)["version"]
    found = remote(config, "begin", match.name, base, force)
    if found.get("busy"):
        raise RuntimeError(f"{found['pushing']['machine']} is sending it: try again in a moment")
    if not found["ok"]:
        raise Conflict(shown(found, match))
    signature = backup.signature([match])
    merge_shared(files.root(match), config)
    backup.backup(match)
    # ponytail: a machine pulling while another sends may get a half-written copy; `pull` waiting on `pushing` would close it.
    done = remote(config, "commit", match.name, base)
    if not done["ok"]:
        raise RuntimeError("the copy was cut off: try again")
    remember(match, done["version"], signature)


# A backup's and a check's stages (jobs.Stages) and their seconds before one is measured on this machine, kept in
# outputs/TIMINGS: each match copied ("match:NAME") or compared ("check:NAME"), what sits beside them, the copies listed.
TOOK = {"match": 30.0, "shared": 10.0, "list": 5.0, "check": 15.0}
TIMINGS = "backup_timings.json"


def push_all(outputs: Path, told: bool = False) -> list[str]:
    """Every match changed here since this machine last pushed or pulled it, then what sits beside them kept in step
    (`keep_shared`); what failed. Its stages `told` as it goes for the app's job."""
    failed = []
    found = [p.parent for p in sorted((outputs / "matches").glob(f"*/{matches.PUBLISH}")) if (p.parent / files.SOURCE).exists() and changed(p.parent)]
    config = server(outputs)
    stages = jobs.Stages(outputs / TIMINGS, [*(f"match:{m.name}" for m in found), *(["shared"] if config else [])], TOOK, told)
    for match in found:
        stages.start(f"match:{match.name}")
        try:
            push(match)
            print(f"{match.name}: pushed", flush=True)
        except (Conflict, OSError, RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
            failed.append(f"{match.name}: {error}")
    if config:
        stages.start("shared")
        try:
            keep_shared(outputs, config)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            failed.append(f"shared: {error}")
    stages.start(None)
    return failed


def push_shared(outputs: Path, config: dict) -> None:
    """What sits beside the matches merged with the server's, then copied there: no match's claim moves."""
    merge_shared(outputs, config)
    backup.backup_shared(outputs, config)


def keep_shared(outputs: Path, config: dict) -> None:
    """What sits beside the matches in step with the server: the other machine's brought, this one's sent only when it
    changed here, a copy made for nothing else."""
    mine = backup.shared_changed(outputs)
    merge_shared(outputs, config)
    if mine:
        backup.backup_shared(outputs, config)
    else:
        backup.note(outputs, shared=list(backup.signature(backup.shared(outputs))))


# Files a machine adds lines to: merged line by line, each machine's lines kept.
APPENDED = ("feedback",)


def newest_copy(config: dict) -> str | None:
    """The server's newest copy, None without one."""
    _, _, days = backup.listed(ssh_run(config, backup.listing(backup.ROOT)))
    return max(days) if days else None


def ssh_run(config: dict, command: str, timeout: float = 60) -> str:
    host, ssh = backup.connection(config)
    run = subprocess.run([*ssh, host, command], capture_output=True, text=True, timeout=timeout)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    return run.stdout


def merge_shared(outputs: Path, config: dict, copy: str | None = None, roster: bool = True) -> None:
    """What sits beside the matches brought from the server's newest copy (or `copy`), each file kept here when it is
    newer, none removed; the reports joined line by line, the roster match by match (`merge_roster`) unless not
    `roster` (a pull joins it knowing the match it brought)."""
    copy = copy or newest_copy(config)
    if copy:
        day = f"{backup.ROOT}/{copy}"
        for name in backup.SHARED:
            if name == "roster.json":
                continue
            target = outputs / name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if name in APPENDED:
                    join_lines(config, f"{day}/{name}/", target)
                else:
                    rsync(config, f"{day}/{name}" + ("" if name.endswith(".json") else "/"), target, "--update")
            except RuntimeError:
                # Not in that copy.
                pass
    if roster:
        merge_roster(outputs / "matches", config)


def join_lines(config: dict, source: str, target: Path) -> None:
    """The server's files of `source` joined with `target`'s: a file only there brought, one on both sides given the
    lines this machine lacks, after its own."""
    import tempfile

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        rsync(config, source, Path(folder))
        for theirs in Path(folder).iterdir():
            if not theirs.is_file():
                continue
            mine = target / theirs.name
            if not mine.exists():
                files.write_bytes(mine, theirs.read_bytes())
                continue
            have = mine.read_text().splitlines()
            known = set(have)
            extra = [line for line in theirs.read_text().splitlines() if line not in known]
            if extra:
                files.write_text(mine, "\n".join(have + extra) + "\n")


def verify(outputs: Path, told: bool = False) -> list[str]:
    """Each match unchanged here since it was last sent or brought compared byte by byte with its newest copy on the
    server (`rsync --checksum --dry-run`); what differs, noted in outputs/backup_state.json. Its stages `told` as it goes
    for the app's job."""
    config = server(outputs)
    if config is None:
        raise LookupError("no server")
    host, ssh = backup.connection(config)
    stages = jobs.Stages(outputs / TIMINGS, ["list"], TOOK, told)
    stages.start("list")
    _, _, days = backup.listed(ssh_run(config, backup.listing(backup.ROOT)))
    last = backup.newest(days)
    found = [p.parent for p in sorted((outputs / "matches").glob(f"*/{files.SOURCE}")) if not changed(p.parent) and p.parent.name in last]
    problems = []
    stages.plan = ["list", *(f"check:{m.name}" for m in found)]
    for match in found:
        stages.start(f"check:{match.name}")
        run = subprocess.run(
            ["rsync", "-rcn", "--delete", "--itemize-changes", *[f"--exclude={p}" for p in backup.SKIP], "-e", " ".join(ssh), f"{match}/", f"{host}:{backup.ROOT}/{last[match.name]}/{match.name}/"],
            capture_output=True, text=True, timeout=backup.TIMEOUT_S,
        )  # fmt: skip
        differ = [line for line in run.stdout.splitlines() if line.strip()]
        if run.returncode:
            problems.append(f"{match.name}: {(run.stderr.strip().splitlines() or [f'rsync: {run.returncode}'])[-1]}")
        elif differ:
            problems.append(f"{match.name}: {len(differ)} files differ ({differ[0].split(maxsplit=1)[-1]}…)")
    stages.start(None)
    backup.note(outputs, verified=datetime.now().isoformat(timespec="seconds"), problems=problems)
    return problems


# The copies are checked this often.
VERIFY_EVERY_S = 7 * 24 * 3600


def verify_weekly(outputs: Path) -> None:
    """`verify` when the last check is a week old."""
    last = backup.state(outputs)["verified"]
    if not last or time.time() - datetime.fromisoformat(last).timestamp() > VERIFY_EVERY_S:
        verify(outputs)


def take(match: Path) -> None:
    """The server's copy of `match` kept: brought here, this machine's changes set aside (`backup-sync-*`)."""
    pull(match.name, files.root(match))


def keep(match: Path) -> None:
    """This machine's copy of `match` kept: sent over the server's, which stays set aside there (`sync_remote.ASIDE`)."""
    push(match, force=True)


def behind(found: list[Path]) -> dict[str, str]:
    """The matches of `found` whose server copy is newer than the one this machine started from, by name the machine
    that sent it: putting them online from here would put an older version there. None without the server's matches."""
    if not found or not active(files.root(found[0])):
        return {}
    known = listing(files.root(found[0]))
    return {m.name: known[m.name].get("pushedBy") or "?" for m in found if m.name in known and known[m.name]["version"] > local(m)["version"]}


def listing(outputs: Path) -> dict[str, dict]:
    """The matches with a copy on the server: their day, claim and version. Empty without a server."""
    config = server(outputs)
    return remote(config, "list")["matches"] if config else {}


def rsync(config: dict, source: str, target: Path, *options: str, times: bool = True) -> None:
    """The server's `source` brought into `target`, its files' times kept unless not `times` (they are then now)."""
    host, ssh = backup.connection(config)
    run = subprocess.run(["rsync", "-rt" if times else "-r", *options, "-e", " ".join(ssh), f"{host}:{source}", str(target)], capture_output=True, text=True, timeout=backup.TIMEOUT_S)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"rsync: {run.returncode}")


def pull(name: str, outputs: Path = DEFAULT_OUTPUTS, copy: str | None = None) -> Path:
    """The match `name` brought from the server's newest copy into outputs/matches/; this machine's unpushed changes to
    it kept in its `backup-sync-<time>` folder. With `copy` (a restore) that copy's, this machine's set aside whatever
    it is, and the match left to send again: it becomes the newest. LookupError if the server has no such copy."""
    config = server(outputs)
    if config is None:
        raise LookupError("no server: sync setup")
    found = remote(config, "list")["matches"]
    if name not in found:
        raise LookupError(name)
    match = outputs / "matches" / name
    match.mkdir(parents=True, exist_ok=True)
    aside = ["--backup", f"--backup-dir=backup-sync-{time.strftime('%Y%m%d-%H%M%S')}"] if copy or changed(match) else []
    day = f"{backup.ROOT}/{copy or found[name]['day']}"
    rsync(config, f"{day}/{name}/", match, "--delete", *[f"--exclude={p}" for p in backup.SKIP], *aside)
    remember(match, found[name]["version"], None if copy else backup.signature([match]))
    relative_copies(match)
    merge_shared(outputs, config, copy or found[name]["day"], roster=False)
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
    """outputs/roster.json joined with the server's newest: each match's names from this machine where its copy is not
    behind the server's, the match just `pulled` from the server's."""
    path = folder.parent / "roster.json"
    host, ssh = backup.connection(config)
    command = f"f=$(ls -1d {backup.ROOT}/*/roster.json 2>/dev/null | grep -E '/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}(T[0-9]{{2}})?/roster.json$' | tail -1); if [ -n \"$f\" ]; then cat \"$f\"; else echo '{{\"players\": []}}'; fi"
    run = subprocess.run([*ssh, host, command], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or f"ssh: {run.returncode}")
    theirs = json.loads(run.stdout)["players"]
    mine = json.loads(path.read_text())["players"] if path.exists() else []
    claims = claims if claims is not None else remote(config, "list")["matches"]

    def ours(match: str) -> bool:
        if match == pulled:
            return False
        return (folder / match).exists() and local(folder / match)["version"] >= claims.get(match, {}).get("version", 0)

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
    commands.add_parser("verify", help="Compare every match unchanged here with its copy on the server, byte by byte")
    pulling = commands.add_parser("pull", help="Bring matches from the server")
    pulling.add_argument("names", nargs="*")
    pulling.add_argument("--all", action="store_true", help="Every match on the server")
    pushing = commands.add_parser("push", help="Send a match to the server")
    pushing.add_argument("match", type=Path, nargs="?")
    pushing.add_argument("--all", action="store_true", help="Every match changed here, then what sits beside them")
    args = parser.parse_args()
    if args.command == "setup":
        args.outputs.mkdir(parents=True, exist_ok=True)
        files.write_text(args.outputs / SERVER, json.dumps({"upload": f"{args.host}:", "key": args.key}) + "\n")
    elif args.command == "list":
        for name, c in sorted(listing(args.outputs).items()):
            here = args.outputs / "matches" / name
            state = "not here" if not here.exists() else f"here v{local(here)['version']}" + (", changed" if changed(here) else "")
            print(f"{name}  v{c['version']}  from {c['pushedBy'] or '?'}  copy {c['day']}  ({state})")
    elif args.command == "pull":
        found = listing(args.outputs)
        names = sorted(found) if args.all else args.names
        if not names:
            parser.error("name matches or pass --all")
        for name in names:
            here = args.outputs / "matches" / name
            # This machine's own and those it has up to date.
            if args.all and here.exists() and local(here)["version"] >= found[name]["version"]:
                continue
            print(pull(name, args.outputs), flush=True)
    elif args.command == "verify":
        problems = verify(args.outputs, told=True)
        if problems:
            parser.exit(1, "\n".join(problems) + "\n")
        print("the copies match", flush=True)
    elif args.all:
        failed = push_all(args.outputs, told=True)
        if failed:
            parser.exit(1, "\n".join(failed) + "\n")
        print("pushed", flush=True)
    else:
        if not args.match:
            parser.error("a match or --all")
        try:
            push(args.match)
        except Conflict as error:
            parser.exit(1, f"{error}: open it in the review to keep one\n")
        print("pushed", flush=True)


if __name__ == "__main__":
    main()
