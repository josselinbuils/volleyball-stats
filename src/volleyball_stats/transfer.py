"""rsync's part the app uses (`backup`, `sync`, `matches`), for a machine without rsync: Windows has none. Run as rsync
is, `python -m volleyball_stats.transfer [options] SOURCE... DEST`, one side here and the other here or on a server
reached by `-e`'s ssh, where this very file goes to its python3 (3.8 on the owner's server: the standard library only,
nothing newer than 3.8).

Its options: -r -t -c -n (--dry-run, --checksum), --delete, --delay-updates, --update, --itemize-changes, --include,
--exclude, --backup with --backup-dir, -e. As rsync: its filter rules (the first that matches wins; `/` first anchors
at the transfer's root, `*` stays within a folder, `**` goes across), its sources (a folder without a trailing slash
keeps its name), its quick check (size and time, or -c's checksums), its itemized lines and its exit codes (23 a
source missing, 24 a file vanished). A file is written beside its place then renamed onto it, never in place: the
server's copies share their unchanged files by hard links (`backup.snapshot`).

ponytail: whole files go, not rsync's deltas of the changed ones; deltas (a rolling checksum) if a slow link needs them.
ponytail: folders' times are not kept (nothing reads them); rsync -t keeps them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import zlib

WINDOWS = os.name == "nt"
PARTIAL, VANISHED = 23, 24
CHUNK = 1 << 20
# A file's time to the nanosecond, beside tar's.
MTIME = "VBS.mtime_ns"
# The server's python3 runs this file sent on its input's first line, then reads the job on the next.
BOOT = 'import sys,base64,zlib;g={"__name__":"transfer"};exec(zlib.decompress(base64.b64decode(sys.stdin.buffer.readline())),g);g["serve"]()'
SHORT = {"r": "recursive", "t": "times", "c": "checksum", "n": "dry"}
LONG = {"recursive": "recursive", "times": "times", "checksum": "checksum", "dry-run": "dry", "delete": "delete", "delay-updates": "delay", "update": "update", "itemize-changes": "itemize", "backup": "backup"}


def command() -> list:
    """rsync where it is installed, else this stand-in, run as a file: the package's start (`git_check`) is not needed."""
    return ["rsync"] if shutil.which("rsync") else [sys.executable, os.path.abspath(__file__)]


def local(argv: list) -> list:
    """An rsync command line run by `command()`."""
    return [*command(), *argv[1:]] if argv and argv[0] == "rsync" else argv


class Failure(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def glob(pattern: str) -> str:
    """rsync's wildcards as a regular expression."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        end = pattern.find("]", i + 2) if c == "[" else -1
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif end > 0:
            body = pattern[i + 1 : end]
            out.append("[" + ("^" + body[1:] if body.startswith("!") else body).replace("\\", "\\\\") + "]")
            i = end + 1
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


class Rules:
    """--include and --exclude, in their order."""

    def __init__(self, rules: list):
        self.rules = []
        for sign, pattern in rules:
            folders = pattern.endswith("/")
            pattern = pattern.rstrip("/")
            anchored = pattern.startswith("/")
            pattern = pattern.lstrip("/")
            whole = anchored or "/" in pattern or "**" in pattern
            start = "(?:^|/)" if whole and not anchored else "^"
            self.rules.append((sign == "+", re.compile(start + glob(pattern) + "$", re.S), folders, whole))

    def out(self, rel: str, folder: bool) -> bool:
        for keep, rx, folders, whole in self.rules:
            if folders and not folder:
                continue
            if rx.search(rel if whole else rel.rsplit("/", 1)[-1]):
                return not keep
        return False


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def walk(base: str, start: str, rules: Rules, checksum: bool, files: dict, folders: set) -> None:
    """The files and folders of `base`'s `start` (all of `base` for ""), by their names from `base`; files[name] is
    [size, time in ns, md5 or None, path]. Links are left, as rsync -r does without -l."""

    def add(path: str, rel: str, stat: os.stat_result) -> None:
        files[rel] = [stat.st_size, stat.st_mtime_ns, md5(path) if checksum else None, path]

    def down(path: str, rel: str) -> None:
        try:
            with os.scandir(path) as found:
                entries = sorted(found, key=lambda e: e.name)
        except (FileNotFoundError, NotADirectoryError):
            return
        for e in entries:
            name = f"{rel}/{e.name}" if rel else e.name
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if not rules.out(name, True):
                        folders.add(name)
                        down(e.path, name)
                elif e.is_file() and not rules.out(name, False):
                    add(e.path, name, e.stat())
            except FileNotFoundError:
                pass

    if not start:
        down(base, "")
        return
    path = os.path.join(base, *start.split("/"))
    if os.path.islink(path):
        return
    if os.path.isdir(path):
        if not rules.out(start, True):
            folders.add(start)
            down(path, start)
    elif os.path.isfile(path) and not rules.out(start, False):
        add(path, start, os.stat(path))


def trimmed(spec: str) -> tuple:
    """`spec` without its trailing slashes, and whether it had one."""
    slashes = "/\\" if WINDOWS else "/"
    path = spec.rstrip(slashes) or spec[:1]
    return path, path != spec


def listing(specs: list, rules: list, checksum: bool) -> dict:
    """What the sources `specs` hold, named as they go: a folder's contents with a trailing slash, the folder itself
    without; `starts` each source's first name ("" for a folder's contents) and kind, `missing` the ones absent."""
    files, folders, starts, missing = {}, set(), [], []
    for spec in specs:
        path, trailing = trimmed(spec)
        kind = None if os.path.islink(path) else "dir" if os.path.isdir(path) else "file" if os.path.isfile(path) else None
        if kind is None:
            missing.append(spec)
            continue
        base, start = (path, "") if trailing and kind == "dir" else (os.path.dirname(path) or ".", os.path.basename(path))
        walk(base, start, Rules(rules), checksum, files, folders)
        starts.append([start, kind])
    return {"files": files, "folders": sorted(folders), "starts": starts, "missing": missing}


def look(dest: str, starts: list, rules: list, checksum: bool) -> dict:
    """What the destination holds where the sources' `starts` go; one file going to a path that is no folder is
    written at that path, under its `name`."""
    path, trailing = trimmed(dest)
    files, folders = {}, set()
    if len(starts) == 1 and starts[0][1] == "file" and not trailing and not os.path.isdir(path):
        root, name = os.path.dirname(path) or ".", os.path.basename(path)
        walk(root, name, Rules([]), checksum, files, folders)
        return {"root": root, "name": name, "files": files, "folders": [], "exists": True}
    for start, _ in starts:
        walk(path, start, Rules(rules), checksum, files, folders)
    return {"root": path, "name": None, "files": files, "folders": sorted(folders), "exists": os.path.isdir(path)}


def plan(sent: dict, have: dict, o: Options) -> tuple:
    """The folders to make, the files to send (their name there and here, their path, rsync's flags) and the names to
    delete (a folder's with its slash, after its files)."""
    there = (lambda rel: have["name"]) if have["name"] else (lambda rel: rel)
    make = [d for d in sent["folders"] if d not in have["folders"]]
    send = []
    for rel in sorted(sent["files"]):
        size, mtime, digest, path = sent["files"][rel]
        name = there(rel)
        old = have["files"].get(name)
        if old is None:
            flags = "+++++++++"
        else:
            # To the microsecond: Windows keeps 100 ns.
            late = old[1] // 1000 != mtime // 1000
            if o.update and old[1] // 1000 > mtime // 1000:
                continue
            content = old[0] != size or (old[2] != digest if o.checksum else late)
            if not content:
                continue
            flags = ("c" if o.checksum and old[2] != digest else ".") + ("s" if old[0] != size else ".") + (("t" if late else ".") if o.times else "T") + "......"
        send.append((name, rel, path, flags))
    gone = []
    if o.delete and not have["name"]:
        scopes = [s for s, kind in sent["starts"] if kind == "dir"]
        inside = lambda rel: any(not s or rel == s or rel.startswith(s + "/") for s in scopes)  # noqa: E731
        gone = [r for r in have["files"] if inside(r) and r not in sent["files"]]
        gone += [r + "/" for r in have["folders"] if inside(r) and r not in sent["folders"]]
        # Inside first, as rsync.
        gone.sort(key=lambda r: (r.rstrip("/").split("/"), r.endswith("/")), reverse=True)
    return make, send, gone


class Exact:
    """A file read as `size` bytes, cut or padded: it may change while it goes (the next copy takes it right)."""

    def __init__(self, f, size: int):
        self.f, self.left = f, size

    def read(self, n: int = -1) -> bytes:
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.f.read(n)
        self.left -= n
        return data + b"\0" * (n - len(data))


def opened(items: list, vanished: list):
    """Each (name, path) of `items` as (name, its bytes, its time in ns); the ones gone since, in `vanished`."""
    for name, path in items:
        try:
            f = open(path, "rb")
        except FileNotFoundError:
            vanished.append(name)
            continue
        with f:
            stat = os.fstat(f.fileno())
            yield name, Exact(f, stat.st_size), stat.st_mtime_ns, stat.st_size


def pack(out, items: list, told=lambda name: None) -> list:
    """`items` as a tar stream written to `out`; the names vanished."""
    vanished = []
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for name, data, mtime, size in opened(items, vanished):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.pax_headers = size, mtime / 1e9, {MTIME: str(mtime)}
            tar.addfile(info, data)
            told(name)
    return vanished


def unpacked(stream):
    """A tar stream's files as (name, its bytes, its time in ns)."""
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            parts = member.name.split("/")
            if not member.isfile() or member.name.startswith("/") or ".." in parts:
                continue
            yield member.name, tar.extractfile(member), int(member.pax_headers.get(MTIME, int(member.mtime * 1e9)))


def aside(path: str, folder: str, rel: str) -> None:
    """The file `path` moved to its place in the backup `folder`."""
    to = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(to), exist_ok=True)
    if os.path.isdir(to):
        shutil.rmtree(to)
    os.replace(path, to)


def replace(temp: str, target: str) -> None:
    """`temp` renamed onto `target`; on Windows again a moment later while another program holds `target` open."""
    for attempt in range(50):
        try:
            os.replace(temp, target)
            return
        except PermissionError:
            if not WINDOWS or attempt == 49:
                raise
            time.sleep(0.1)


def receive(job: dict, entries, told=lambda name: None) -> None:
    """`job`'s folders made, its files written from `entries` ((name, bytes, time in ns)), its names deleted."""
    root = job["root"]
    at = lambda rel: os.path.join(root, *rel.rstrip("/").split("/"))  # noqa: E731
    backup = job["backup"] and os.path.join(root, job["backup"])

    def delete() -> None:
        for rel in job["gone"]:
            path = at(rel)
            try:
                if rel.endswith("/"):
                    os.rmdir(path)
                elif backup:
                    aside(path, backup, rel)
                else:
                    os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                # A folder still holding excluded files stays, as with rsync.
                if not rel.endswith("/"):
                    raise

    os.makedirs(root, exist_ok=True)
    for folder in job["folders"]:
        os.makedirs(at(folder), exist_ok=True)
    if not job["delay"]:
        delete()
    waiting = []
    for name, data, mtime in entries:
        target = at(name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp = os.path.join(os.path.dirname(target), f".{os.path.basename(target)}.{os.getpid()}.tmp")
        with open(temp, "wb") as out:
            shutil.copyfileobj(data, out, CHUNK)
        if job["times"]:
            os.utime(temp, ns=(mtime, mtime))
        waiting.append((temp, target, name))
        if not job["delay"]:
            put(*waiting.pop(), backup)
        told(name)
    for one in waiting:
        put(*one, backup)
    if job["delay"]:
        delete()


def put(temp: str, target: str, name: str, backup) -> None:
    if backup and os.path.lexists(target):
        aside(target, backup, name)
    elif os.path.isdir(target):
        shutil.rmtree(target)
    replace(temp, target)


def write(stream, text: str) -> None:
    stream.buffer.write((text + "\n").encode("utf-8", "replace"))
    stream.buffer.flush()


def serve() -> None:
    """The far side: the job on its input's next line, its answer on its output."""
    job = json.loads(sys.stdin.buffer.readline())
    op = job.pop("op")
    if op == "list":
        answer = listing(job["specs"], job["rules"], job["checksum"])
    elif op == "look":
        answer = look(job["dest"], job["starts"], job["rules"], job["checksum"])
    elif op == "send":
        vanished = pack(sys.stdout.buffer, job["items"])
        sys.stdout.buffer.flush()
        for name in vanished:
            write(sys.stderr, f'file has vanished: "{name}"')
        sys.exit(VANISHED if vanished else 0)
    else:
        receive(job, unpacked(sys.stdin.buffer))
        return
    sys.stdout.buffer.write(json.dumps(answer).encode("utf-8", "surrogateescape"))


class Far:
    """The other side, this file's python3 there reached by ssh."""

    def __init__(self, shell: str, host: str):
        self.command = [*shlex.split(shell, posix=True), host, shlex.join(["python3", "-c", BOOT])]

    @staticmethod
    def head(job: dict) -> bytes:
        with open(__file__, "rb") as f:
            code = base64.b64encode(zlib.compress(f.read(), 9))
        return code + b"\n" + json.dumps(job).encode("utf-8", "surrogateescape") + b"\n"

    def ask(self, job: dict) -> dict:
        done = subprocess.run(self.command, input=self.head(job), stdout=subprocess.PIPE)
        if done.returncode:
            raise Failure(f"the server's side failed ({done.returncode})", done.returncode)
        return json.loads(done.stdout.decode("utf-8", "surrogateescape"))

    def start(self, job: dict, output: bool) -> subprocess.Popen:
        process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE if output else subprocess.DEVNULL)
        process.stdin.write(self.head(job))
        return process


class Options:
    def __init__(self, argv: list):
        for flag in set(LONG.values()):
            setattr(self, flag, False)
        self.backup_dir, self.shell, self.rules, paths = None, "ssh", [], []
        args = iter(argv)
        for a in args:
            if a == "-e":
                self.shell = next(args, "ssh")
            elif a.startswith("--"):
                name, _, value = a[2:].partition("=")
                if name in ("include", "exclude"):
                    self.rules.append(("+" if name == "include" else "-", value))
                elif name == "backup-dir":
                    self.backup, self.backup_dir = True, value
                elif name == "rsh":
                    self.shell = value
                elif name in LONG:
                    setattr(self, LONG[name], True)
                else:
                    raise Failure(f"--{name}: unknown option")
            elif a.startswith("-") and len(a) > 1:
                for c in a[1:]:
                    if c not in SHORT:
                        raise Failure(f"-{c}: unknown option")
                    setattr(self, SHORT[c], True)
            else:
                paths.append(a)
        if len(paths) < 2:
            raise Failure("a source and a destination are needed")
        self.sources, self.dest = paths[:-1], paths[-1]


def place(spec: str) -> tuple:
    """`[user@]host:path` as (host, path), a path here as (None, path); `C:\\…` is a drive, not a host."""
    found = re.match(r"([^/\\:]+):(.*)\Z", spec, re.S)
    if found and len(found[1]) > 1:
        return found[1], found[2] or "."
    return None, spec


def run(o: Options) -> int:
    places = [place(s) for s in o.sources]
    hosts = {host for host, _ in places}
    dest_host, dest = place(o.dest)
    if len(hosts) > 1 or (dest_host and hosts != {None}):
        raise Failure("one side here, the other here or on one server")
    source_host = next(iter(hosts))
    sender = Far(o.shell, source_host) if source_host else None
    receiver = Far(o.shell, dest_host) if dest_host else None
    specs = [path for _, path in places]
    job = {"specs": specs, "rules": o.rules, "checksum": o.checksum}
    sent = sender.ask({"op": "list", **job}) if sender else listing(**job)
    code = 0
    for spec in sent["missing"]:
        write(sys.stderr, f'rsync: link_stat "{spec}" failed: No such file or directory (2)')
        code = PARTIAL
    if not sent["starts"]:
        return code
    far_abs = receiver is not None
    rules = list(o.rules)
    if o.backup_dir and not (o.backup_dir.startswith("/") if far_abs else os.path.isabs(o.backup_dir)):
        # The backup folder inside the destination is never deleted.
        rules.insert(0, ("-", "/" + o.backup_dir.strip("/")))
    job = {"dest": dest, "starts": sent["starts"], "rules": rules, "checksum": o.checksum}
    have = receiver.ask({"op": "look", **job}) if receiver else look(**job)
    make, send, gone = plan(sent, have, o)
    # Named as on the sending side, as rsync does.
    lines = {name: f"{f} {rel}" for name, rel, _, f in send}
    arrow = "<" if receiver else ">"
    say = (lambda text: write(sys.stdout, text)) if o.itemize else (lambda text: None)
    if not have["exists"] and not have["name"]:
        say("cd+++++++++ ./")
    for rel in gone:
        say(f"*deleting   {rel}")
    for folder in make:
        say(f"cd+++++++++ {folder}/")
    told = lambda name: say(f"{arrow}f{lines[name]}")  # noqa: E731
    if o.dry:
        for name, _, _, _ in send:
            told(name)
        return code
    if o.backup and not o.backup_dir:
        raise Failure("--backup needs --backup-dir here")
    task = {"root": have["root"], "folders": make, "gone": gone, "backup": o.backup_dir if o.backup else None, "delay": o.delay, "times": o.times}
    items = [(name, path) for name, _, path, _ in send]
    vanished = []
    if receiver:
        process = receiver.start({"op": "receive", **task}, output=False)
        try:
            vanished = pack(process.stdin, items, told)
        except BrokenPipeError:
            pass
        process.stdin.close()
        if process.wait():
            raise Failure(f"the server's side failed ({process.returncode})", process.returncode)
    elif sender:
        process = sender.start({"op": "send", "items": items}, output=True)
        process.stdin.close()
        receive(task, unpacked(process.stdout), told)
        process.stdout.close()
        if process.wait() not in (0, VANISHED):
            raise Failure(f"the server's side failed ({process.returncode})", process.returncode)
        code = code or process.returncode
    else:
        receive(task, ((n, data, mtime) for n, data, mtime, _ in opened(items, vanished)), told)
    for name in vanished:
        write(sys.stderr, f'file has vanished: "{name}"')
    return code or (VANISHED if vanished else 0)


def main(argv: list | None = None) -> int:
    try:
        return run(Options(sys.argv[1:] if argv is None else argv))
    except Failure as error:
        write(sys.stderr, f"rsync: {error}")
        return error.code
    except OSError as error:
        write(sys.stderr, f"rsync: {error}")
        return PARTIAL


if __name__ == "__main__":
    sys.exit(main())
