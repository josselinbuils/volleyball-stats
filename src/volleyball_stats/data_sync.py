"""The videos (`data/`) copied straight between two machines on the same network, no server between them: one waits,
showing its address and a code, the other connects with them. Each gets the files only the other has; a file both
have that differs is left as it is and named. A copy cut short resumes where it stopped, and each one is checked
against the sender's hash before it takes its name.

    uv run python -m volleyball_stats.data_sync                 # waits: run it on the Mac (WSL2 is not reachable)
    uv run python -m volleyball_stats.data_sync HOST:PORT CODE  # the other machine

While it waits, the folder is open to the network to whoever has the code, unencrypted: it stops after the copy, a
wrong code tried WRONG_CODES times, or Ctrl+C.
"""

import argparse
import hashlib
import http.client
import json
import os
import secrets
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PORT = 8766
# Letters and digits that cannot be misread for each other.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LENGTH = 8
WRONG_CODES = 5
CHUNK = 1 << 20
# Sampled at the start, middle and end to tell two files of the same size apart without reading them whole.
SAMPLE = 1 << 20


def part_of(path: Path) -> Path:
    """Where a file being received grows until it is whole."""
    return path.with_name(f".{path.name}.part")


def listed(root: Path) -> dict:
    """The files of `root` by their path in it, with their size and time; the parts being received apart."""
    found, parts = {}, {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            path = Path(folder) / name
            if path.is_symlink():
                continue
            if name.startswith(".") and name.endswith(".part"):
                parts[(path.parent / name[1:-5]).relative_to(root).as_posix()] = path.stat().st_size
            elif not name.startswith("."):
                stat = path.stat()
                found[path.relative_to(root).as_posix()] = {"size": stat.st_size, "mtime": stat.st_mtime}
    return {"files": found, "parts": parts}


def inside(root: Path, rel: str) -> Path:
    """`rel` under `root`; ValueError for anything that would leave it or name a hidden file."""
    parts = Path(rel).parts
    if not parts or any(p in ("", ".", "..") or p.startswith(".") for p in parts) or Path(rel).is_absolute():
        raise ValueError(rel)
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(rel)
    return path


def digest(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def sample(path: Path) -> str:
    """A hash of the size and three slices: equal for the same file, different for almost any two."""
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        for at in sorted({0, max(0, size // 2 - SAMPLE // 2), max(0, size - SAMPLE)}):
            f.seek(at)
            h.update(f.read(SAMPLE))
    return h.hexdigest()


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def address() -> str:
    """This machine's address on the local network (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def serving(root: Path, code: str, host: str = "0.0.0.0", port: int = PORT) -> ThreadingHTTPServer:
    """The waiting side's server for `root`, not started."""
    hashes: dict[str, tuple[int, float, str]] = {}
    wrong = [0]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_) -> None:
            pass

        def reply(self, status: int, body: bytes = b"", kind: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def allowed(self) -> bool:
            if secrets.compare_digest(self.headers.get("X-Code", ""), code):
                return True
            wrong[0] += 1
            self.reply(403)
            if wrong[0] >= WRONG_CODES:
                print("Too many wrong codes: stopped", flush=True)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return False

        def target(self) -> tuple[Path, dict]:
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            return inside(root, q.get("path", "")), q

        def do_GET(self) -> None:
            if not self.allowed():
                return
            route = urlparse(self.path).path
            try:
                if route == "/manifest":
                    return self.reply(200, json.dumps(listed(root)).encode())
                path, _ = self.target()
                if not path.is_file():
                    return self.reply(404)
                stat = path.stat()
                if route in ("/hash", "/sample"):
                    key = f"{route}:{path}"
                    if hashes.get(key, (None, None, None))[:2] != (stat.st_size, stat.st_mtime):
                        hashes[key] = (stat.st_size, stat.st_mtime, digest(path) if route == "/hash" else sample(path))
                    return self.reply(200, json.dumps(hashes[key][2]).encode())
                if route == "/file":
                    first = min(stat.st_size, int(self.headers.get("Range", "bytes=0-").removeprefix("bytes=").split("-")[0] or 0))
                    self.send_response(206 if first else 200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(stat.st_size - first))
                    self.end_headers()
                    with open(path, "rb") as f:
                        f.seek(first)
                        while chunk := f.read(CHUNK):
                            self.wfile.write(chunk)
                    return None
                return self.reply(404)
            except ValueError:
                return self.reply(400)
            except (BrokenPipeError, ConnectionResetError):
                return None

        def do_PUT(self) -> None:
            if not self.allowed():
                return
            try:
                path, q = self.target()
            except ValueError:
                return self.reply(400)
            if path.exists():
                return self.reply(409, json.dumps({"error": "exists"}).encode())
            part = part_of(path)
            have = part.stat().st_size if part.exists() else 0
            if int(q.get("offset", -1)) != have:
                return self.reply(409, json.dumps({"have": have}).encode())
            left = int(self.headers["Content-Length"])
            part.parent.mkdir(parents=True, exist_ok=True)
            with open(part, "ab") as f:
                while left > 0:
                    chunk = self.rfile.read(min(CHUNK, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            self.reply(200 if left == 0 else 400)

        def do_POST(self) -> None:
            if not self.allowed():
                return
            route = urlparse(self.path).path
            if route == "/bye":
                self.reply(200)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            try:
                path, q = self.target()
            except ValueError:
                return self.reply(400)
            part = part_of(path)
            if route != "/done" or path.exists() or not part.exists():
                return self.reply(409)
            if digest(part) != q.get("hash"):
                part.unlink()
                return self.reply(409, json.dumps({"error": "hash"}).encode())
            os.replace(part, path)
            os.utime(path, (float(q["mtime"]), float(q["mtime"])))
            self.reply(200)

    return ThreadingHTTPServer((host, port), Handler)


class Peer:
    """The waiting side, as the connecting side reaches it."""

    def __init__(self, where: str, code: str):
        host, _, port = where.rpartition(":")
        self.host, self.port, self.code = host or where, int(port) if host else PORT, code

    def request(self, method: str, route: str, path: str | None = None, body=None, headers: dict | None = None, **query) -> http.client.HTTPResponse:
        # Long enough for the other side to hash a whole match's video.
        connection = http.client.HTTPConnection(self.host, self.port, timeout=900, blocksize=CHUNK)
        params = "&".join(f"{k}={quote(str(v))}" for k, v in {**({"path": path} if path is not None else {}), **query}.items())
        connection.request(method, route + (f"?{params}" if params else ""), body=body, headers={"X-Code": self.code, **(headers or {})})
        response = connection.getresponse()
        if response.status == 403:
            raise PermissionError("wrong code")
        return response

    def json(self, method: str, route: str, path: str | None = None, **query):
        response = self.request(method, route, path, **query)
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"{route} {path}: {response.status} {body.decode(errors='replace')}")
        return json.loads(body) if body else None


def progress(name: str, size: int) -> Callable[[int], None]:
    """A line saying how far a file's copy is, every 2 s and at its end."""
    started, last = time.monotonic(), [0.0]

    def show(done: int) -> None:
        now = time.monotonic()
        if now - last[0] >= 2 or done >= size:
            last[0] = now
            rate = done / max(now - started, 1e-6) / 1e6
            print(f"\r{name}: {done / max(size, 1):.0%} ({rate:.0f} MB/s)", end="\n" if done >= size else "", flush=True)

    return show


def fetch(peer: Peer, root: Path, rel: str, meta: dict) -> None:
    """The peer's file `rel` copied here, from where an earlier copy stopped."""
    path = inside(root, rel)
    part = part_of(path)
    part.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    show = progress(f"<- {rel}", meta["size"])
    if have < meta["size"]:
        response = peer.request("GET", "/file", rel, headers={"Range": f"bytes={have}-"})
        if response.status not in (200, 206):
            raise RuntimeError(f"{rel}: {response.status}")
        if response.status == 200:
            have = 0
        with open(part, "ab" if have else "wb") as f:
            while chunk := response.read(CHUNK):
                f.write(chunk)
                have += len(chunk)
                show(have)
    if digest(part) != peer.json("GET", "/hash", rel):
        part.unlink()
        raise RuntimeError(f"{rel}: not the same once copied, removed: run again")
    os.replace(part, path)
    os.utime(path, (meta["mtime"], meta["mtime"]))
    show(meta["size"])


def send(peer: Peer, root: Path, rel: str, have: int) -> None:
    """This machine's file `rel` copied to the peer, from the `have` bytes it already holds."""
    path = inside(root, rel)
    size = path.stat().st_size
    show = progress(f"-> {rel}", size)
    if have > size:
        raise RuntimeError(f"{rel}: the other machine holds more of it than there is")
    if have < size:
        with open(path, "rb") as f:
            f.seek(have)

            class Reading:
                def read(self, n: int = CHUNK) -> bytes:
                    chunk = f.read(n)
                    show(f.tell())
                    return chunk

            response = peer.request("PUT", "/file", rel, body=Reading(), headers={"Content-Length": str(size - have)}, offset=have)
            body = response.read()
            if response.status != 200:
                raise RuntimeError(f"{rel}: {response.status} {body.decode(errors='replace')}")
    peer.json("POST", "/done", rel, hash=digest(path), mtime=path.stat().st_mtime)
    show(size)


def exchange(peer: Peer, root: Path) -> list[str]:
    """Each side given the files only the other has; the files both have that differ, left as they are."""
    theirs, mine = peer.json("GET", "/manifest"), listed(root)
    differ = []
    for rel in sorted(set(theirs["files"]) & set(mine["files"])):
        if theirs["files"][rel]["size"] != mine["files"][rel]["size"] or peer.json("GET", "/sample", rel) != sample(inside(root, rel)):
            differ.append(rel)
    for rel in sorted(set(theirs["files"]) - set(mine["files"])):
        fetch(peer, root, rel, theirs["files"][rel])
    for rel in sorted(set(mine["files"]) - set(theirs["files"])):
        send(peer, root, rel, theirs["parts"].get(rel, 0))
    return differ


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the videos straight between two machines on the same network.")
    parser.add_argument("peer", nargs="?", help="HOST:PORT the waiting machine shows; none to wait")
    parser.add_argument("code", nargs="?", help="The code it shows")
    parser.add_argument("--folder", type=Path, default=Path("data"))
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    args.folder.mkdir(parents=True, exist_ok=True)
    if args.peer is None:
        code = new_code()
        server = serving(args.folder, code, port=args.port)
        print(f"On the other machine, from the project's folder:\n  uv run python -m volleyball_stats.data_sync {address()}:{args.port} {code}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        print("Stopped", flush=True)
        return
    if not args.code:
        parser.error("the code the waiting machine shows")
    peer = Peer(args.peer, args.code)
    try:
        differ = exchange(peer, args.folder)
    finally:
        try:
            peer.request("POST", "/bye").read()
        except (OSError, PermissionError):
            pass
    for rel in differ:
        print(f"Different on each machine, left as it is: {rel}", flush=True)
    print("Done", flush=True)


if __name__ == "__main__":
    main()
