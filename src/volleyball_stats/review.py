"""Review, on the video, the player identities the identity step is least sure of.

    uv run python -m volleyball_stats.review outputs/VIDEO --video VIDEO --court COURT_JSON [--squad N[,N]] [--theme NAME] [--roster PATH] [--port PORT]

Builds the match page like web.py, with the video and every player's picture, into MATCH/review/,
apart from the page to publish (MATCH/site/, rebuilt with its own choices on "apply"), then serves
it on this machine only, with a review mode at /review: one question at a time from identity_candidates.json, the player outlined on the video
beside pictures of the identities they could be. Each answer is saved at once to
identity_answers.json as hard constraints (identity.py); "apply" and "undo" rerun the identity step
and rebuild the page, in seconds. The review also names the players: each identity's name and
jersey number go to player_names.json, applied likewise. Answers and names refer to pieces of
player tracks, so they hold until the players are tracked again.

The roster (--roster, outputs/roster.json by default, kept out of the repository: it names people)
remembers the named players across matches with their re-identification embedding of their last
ROSTER_MATCHES matches, and suggests the names of those who look most like each new identity.
"""

import argparse
import csv
import json
import threading
import webbrowser
from collections import Counter
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import cv2
import numpy as np

from volleyball_stats import identity, web

# Frames between two boxes of a question's outline, pictures shown per piece and per identity, and
# frames looked at for the clearest picture of a piece.
BOX_STEP, PIECE_CROPS, IDENTITY_CROPS, CANDIDATES = 2, 3, 4, 12
CROP_PX, CROP_MARGIN = 192, 0.15
KINDS = ("same", "different", "not_player")
ROSTER = Path("outputs/roster.json")
# Matches of a player the roster keeps (the latest), and names suggested per identity.
ROSTER_MATCHES, SUGGESTIONS = 5, 3

Ref = dict


def mid(start: int, end: int) -> int:
    return (start + end) // 2


class Questions:
    """The review's questions from a match folder's identities, candidates and player tracks."""

    def __init__(self, match: Path, fps: float):
        self.match, self.fps = match, fps
        # frame, track, x1, y1, x2, y2 of every player box, sorted by frame (players.csv's order):
        # compact arrays, a 2-hour match holds millions of boxes.
        table = np.loadtxt(match / "players.csv", delimiter=",", skiprows=1, usecols=(0, 1, 3, 4, 5, 6), ndmin=2).round().astype(np.int32)
        self.frame_of, self.box_of = table[:, 0], table[:, 2:]
        by_track = np.lexsort((table[:, 0], table[:, 1]))
        tracks, firsts = np.unique(table[by_track, 1], return_index=True)
        self.rows = {int(t): by_track[a:b] for t, a, b in zip(tracks, firsts, [*firsts[1:], len(by_track)])}
        self.load()

    def load(self) -> None:
        self.table = identity.read_identities(self.match / "identities.csv")
        self.candidates = json.loads((self.match / "identity_candidates.json").read_text())
        self.vectors = prototypes(self.match / "embeddings.npz", self.table)

    def track_rows(self, track: int, start: int, end: int) -> np.ndarray:
        """Indices of a track's boxes from `start` to `end`, by frame."""
        rows = self.rows[track]
        frames = self.frame_of[rows]
        return rows[np.searchsorted(frames, start) : np.searchsorted(frames, end, side="right")]

    def box(self, track: int, frame: int) -> tuple:
        rows = self.rows[track]
        return tuple(int(v) for v in self.box_of[rows[np.argmin(np.abs(self.frame_of[rows] - frame))]])

    def crop(self, track: int, frame: int) -> str:
        return f"crop?f={frame}&b={','.join(map(str, self.box(track, frame)))}"

    def clear(self, track: int, start: int, end: int) -> int:
        """The frame of a piece where the track's box overlaps the other boxes least, among
        CANDIDATES spread over it: a picture of the player alone."""

        def covered(row: int) -> float:
            frame, (x1, y1, x2, y2) = self.frame_of[row], self.box_of[row]
            others = self.box_of[np.searchsorted(self.frame_of, frame) : np.searchsorted(self.frame_of, frame, side="right")]
            w = np.clip(np.minimum(x2, others[:, 2]) - np.maximum(x1, others[:, 0]), 0, None)
            h = np.clip(np.minimum(y2, others[:, 3]) - np.maximum(y1, others[:, 1]), 0, None)
            share = w * h / max(1, (x2 - x1) * (y2 - y1))
            # The box itself covers all of itself.
            return float(np.sort(share)[-2]) if len(share) > 1 else 0.0

        rows = self.track_rows(track, start, end)
        if not len(rows):
            return mid(start, end)
        picks = rows[:: max(1, len(rows) // CANDIDATES)]
        return int(self.frame_of[min(picks, key=lambda r: (covered(r), abs(self.frame_of[r] - mid(start, end))))])

    def pieces(self, team: int, number: int) -> list[tuple[int, int, int, int, int]]:
        """An identity's pieces, longest first."""
        return sorted((r for r in self.table if r[3] == team and r[4] == number), key=lambda r: r[1] - r[2])

    def ref(self, team: int, number: int) -> Ref:
        """The longest piece of an identity, as an answer refers to it."""
        track, start, end, _, _ = self.pieces(team, number)[0]
        return {"track": track, "frame": mid(start, end)}

    def faces(self, team: int, number: int) -> list[str]:
        return [self.crop(track, self.clear(track, start, end)) for track, start, end, _, _ in self.pieces(team, number)[:IDENTITY_CROPS]]

    def clip(self, track: int, start: int, end: int) -> dict:
        rows = [r for r in self.track_rows(track, start, end) if (self.frame_of[r] - start) % BOX_STEP == 0]
        return {
            "start": round(start / self.fps, 2),
            "end": round(end / self.fps, 2),
            "boxes": [[round(int(self.frame_of[r]) / self.fps, 3), *(int(v) for v in self.box_of[r])] for r in rows],
        }

    def players(self, roster: list[dict], teams: list[str | None]) -> list[dict]:
        """Every identity, longest on court first, with pictures, seconds of play, touches, the name
        and jersey number given and the roster's players of its team (`teams`' names) who look most
        like it."""
        names = identity.named(self.table, identity.read_names(self.match))
        with open(self.match / "actions.csv") as f:
            touches = Counter((int(r["team"]), int(r["identity"])) for r in csv.DictReader(f) if r.get("identity"))
        seconds: dict[tuple[int, int], float] = {}
        for _, start, end, team, number in self.table:
            if number:
                seconds[team, number] = seconds.get((team, number), 0.0) + (end - start + 1) / self.fps
        out = []
        for (team, number), played in sorted(seconds.items(), key=lambda kv: -kv[1]):
            given = names.get((team, number), {})
            out.append({
                "team": team, "identity": number, "seconds": round(played, 1), "contacts": touches[team, number],
                "crops": self.faces(team, number), "name": given.get("name"), "jersey": given.get("jersey"),
                "suggestions": suggest(self.vectors.get((team, number)), roster, teams[team - 1]),
            })
        return out

    def build(self, asked: set[str]) -> tuple[list[dict], dict[str, dict]]:
        """The questions not asked yet, most at stake first, and what each answer means (the refs)."""
        out, refs = [], {}
        for c in self.candidates["segments"]:
            qid = f"piece:{c['track']}:{c['start_frame']}"
            options = [n for n in (c["identity"], c["runner_up"]) if n]
            if qid in asked or not options or c["track"] not in self.rows:
                continue
            track, start, end = c["track"], c["start_frame"], c["end_frame"]
            cuts = [start + (end - start) * k // PIECE_CROPS for k in range(PIECE_CROPS + 1)]
            picks = sorted({self.clear(track, a, b) for a, b in zip(cuts, cuts[1:])})
            out.append({
                "id": qid, "kind": "piece", "team": c["team"], "identity": c["identity"], "impact": c["impact"],
                "seconds": c["seconds"], "contacts": c["contacts"], "clip": self.clip(track, start, end),
                "crops": [self.crop(track, f) for f in picks],
                "choices": [{"identity": n, "crops": self.faces(c["team"], n)} for n in options],
            })
            refs[qid] = {"piece": {"track": track, "frame": mid(start, end)}, "choices": [self.ref(c["team"], n) for n in options]}
        for c in self.candidates["merges"]:
            team, (a, b) = c["team"], c["identities"]
            qid = f"merge:{team}:{a}:{b}"
            if qid in asked:
                continue
            examples = [self.clip(e["track"], e["start_frame"], e["end_frame"]) for e in c["examples"]]
            out.append({
                "id": qid, "kind": "merge", "team": team, "identity": a, "impact": c["impact"], "seconds": sum(c["seconds"]),
                "contacts": sum(c["contacts"]), "clip": examples[0], "other": examples[1],
                "crops": [], "choices": [{"identity": n, "crops": self.faces(team, n)} for n in (a, b)],
            })
            refs[qid] = {"choices": [self.ref(team, a), self.ref(team, b)]}
        return sorted(out, key=lambda q: -q["impact"]), refs


def constraints(choice: str, refs: dict) -> dict[str, list]:
    """What an answer adds to identity_answers.json. A piece is one of its `choices` (index) and not
    the other, someone else ("other"), or not a player; two identities are one player ("same") or
    two ("different"); "skip" adds nothing."""
    piece, options = refs.get("piece"), refs["choices"]
    if choice == "same":
        return {"same": [options]}
    if choice == "different":
        return {"different": [options]}
    if choice == "other":
        return {"different": [[piece, *options]]}
    if choice == "not_player":
        return {"not_player": [piece]}
    if choice.isdigit() and int(choice) < len(options):
        k = int(choice)
        rest = [r for i, r in enumerate(options) if i != k]
        return {"same": [[piece, options[k]]], **({"different": [[piece, *rest]]} if rest else {})}
    return {}


def save(path: Path, log: list[dict]) -> None:
    """identity_answers.json from the answers' `log`, the source of its constraint lists."""
    data = {kind: [x for entry in log for x in entry.get(kind, [])] for kind in KINDS}
    path.write_text(json.dumps({**data, "log": log}, indent=1) + "\n")


def prototypes(cache: Path, table: list[tuple[int, int, int, int, int]]) -> dict[tuple[int, int], np.ndarray]:
    """Each identity's unit re-identification embedding, its pieces' (the embedding cache) averaged by
    length; not whitened, the roster compares them across matches."""
    if not cache.exists():
        return {}
    data = np.load(cache)
    vectors = {tuple(round(v) for v in k[:3]): x for k, x in zip(data["keys"].tolist(), data["vectors"].astype(float))}
    sums: dict[tuple[int, int], np.ndarray] = {}
    for track, start, end, team, number in table:
        v = vectors.get((track, start, end))
        if number and v is not None:
            sums[team, number] = sums.get((team, number), 0.0) + (end - start + 1) * v / max(float(np.linalg.norm(v)), 1e-9)
    return {k: v / max(float(np.linalg.norm(v)), 1e-9) for k, v in sums.items()}


def load_roster(path: Path) -> list[dict]:
    return json.loads(path.read_text())["players"] if path.exists() else []


def suggest(vector: np.ndarray | None, roster: list[dict], team: str | None) -> list[dict]:
    """The names and jersey numbers of the roster's players of `team` (every player for an unnamed
    team) who look most like `vector`, best first."""
    if vector is None:
        return []
    scored = []
    for player in roster:
        if team and player.get("team") and player["team"] != team:
            continue
        mean = np.mean(list(player["vectors"].values()), axis=0)
        scored.append((float(mean @ vector) / max(float(np.linalg.norm(mean)), 1e-9), player))
    return [{"name": p["name"], "jersey": p.get("jersey")} for _, p in sorted(scored, key=lambda sp: -sp[0])[:SUGGESTIONS]]


def remember(path: Path, match: str, names: dict[tuple[int, int], dict], vectors: dict[tuple[int, int], np.ndarray], teams: list[str | None]) -> None:
    """The roster with this match's named players (`names` by (team, identity)) in place of the
    ones it held for it: their name, latest jersey number and embedding."""
    roster = load_roster(path)
    for player in roster:
        player["vectors"].pop(match, None)
    by_key = {(p.get("team"), p["name"].casefold()): p for p in roster}
    for (team, number), given in names.items():
        if not given.get("name") or (team, number) not in vectors:
            continue
        name = given["name"].strip()
        player = by_key.get((teams[team - 1], name.casefold()))
        if player is None:
            player = by_key[teams[team - 1], name.casefold()] = {"name": name, "team": teams[team - 1], "jersey": None, "vectors": {}}
            roster.append(player)
        player["name"] = name
        player["jersey"] = given["jersey"] if given.get("jersey") is not None else player["jersey"]
        player["vectors"][match] = [round(float(x), 4) for x in vectors[team, number]]
        while len(player["vectors"]) > ROSTER_MATCHES:
            player["vectors"].pop(next(iter(player["vectors"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"players": [p for p in roster if p["vectors"]]}, ensure_ascii=False) + "\n")


def set_name(match: Path, questions: Questions, team: int, number: int, given: str | None, jersey: int | None) -> None:
    """player_names.json with identity `number` of `team` named `given` and its `jersey` number,
    in place of the entries naming it; both None unnames it. A new entry refers to the identity's
    longest piece."""
    entries = identity.read_names(match)
    mine = [e for e in entries if identity.lookup(questions.table, e["ref"]["track"], e["ref"]["frame"]) == (team, number)]
    entries = [e for e in entries if e not in mine]
    given = (given or "").strip() or None
    if given or jersey is not None:
        entries.append({"ref": mine[0]["ref"] if mine else questions.ref(team, number), "name": given, "jersey": jersey})
    (match / identity.NAMES).write_text(json.dumps({"players": entries}, indent=1, ensure_ascii=False) + "\n")


def load_log(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("log", []) if path.exists() else []


def range_of(header: str | None, size: int) -> tuple[int, int] | None:
    """(first, last) byte of a "bytes=a-b" Range header, None without one or when unsatisfiable."""
    if not header or not header.startswith("bytes="):
        return None
    a, _, b = header[6:].split(",")[0].partition("-")
    first, last = (size - int(b), size - 1) if not a else (int(a), int(b) if b else size - 1)
    return (max(0, first), min(last, size - 1)) if first < size else None


def serve(match: Path, video: Path, court: Path, squad, theme: str, port: int, browser: bool = True, roster: Path = ROSTER) -> None:
    # Its own page, with the video and every picture: the published one stays as it was built.
    site = match / "review"
    web.build(match, video, court, site, theme=theme, footage="full", pictured={1, 2})
    cap = cv2.VideoCapture(str(video))
    fps, width, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    answers = match / "identity_answers.json"
    if not (match / "identity_candidates.json").exists():
        identity.rerun(match, video, squad)
    questions = Questions(match, fps)
    lock = threading.Lock()
    capture = cv2.VideoCapture(str(video))

    @lru_cache(maxsize=512)
    def picture(frame: int, box: tuple[int, int, int, int]) -> bytes:
        with lock:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
            ok, image = capture.read()
        if not ok:
            return b""
        x1, y1, x2, y2 = box
        mx, my = round((x2 - x1) * CROP_MARGIN), round((y2 - y1) * CROP_MARGIN)
        part = image[max(0, y1 - my) : y2 + my, max(0, x1 - mx) : x2 + mx]
        part = cv2.resize(part, (max(1, round(part.shape[1] * CROP_PX / part.shape[0])), CROP_PX), interpolation=cv2.INTER_CUBIC)
        return cv2.imencode(".jpg", part, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()

    def team_names() -> list[str | None]:
        teams = web.read_teams(match)
        return [t["name"] for t in teams["teams"]] if teams else [None, None]

    def review_js() -> bytes:
        log = load_log(answers)
        found, _ = questions.build({entry["id"] for entry in log})
        known, teams = load_roster(roster), team_names()
        players = questions.players(known, teams)
        # The roster's players of each team, for typing names: all of them for an unnamed team.
        names = [[{"name": p["name"], "jersey": p.get("jersey")} for p in known if not team or not p.get("team") or p["team"] == team] for team in teams]
        data = {"width": width, "height": height, "answered": len(log), "questions": found, "players": players, "roster": names}
        return f"window.REVIEW = {json.dumps(data, separators=(',', ':'))};\n".encode()

    class Handler(BaseHTTPRequestHandler):
        def send(self, body: bytes, kind: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/review.js":
                return self.send(review_js(), "text/javascript")
            if url.path == "/crop":
                q = parse_qs(url.query)
                body = picture(int(q["f"][0]), tuple(int(v) for v in q["b"][0].split(",")))
                return self.send(body, "image/jpeg") if body else self.send(b"", "text/plain", 404)
            if url.path in ("/", "/review"):
                html = (site / "index.html").read_text()
                if url.path == "/review":
                    html = html.replace('<script defer src="data.js"></script>', '<script defer src="data.js"></script><script defer src="review.js"></script>')
                return self.send(html.encode(), "text/html; charset=utf-8")
            parts = Path(unquote(url.path).lstrip("/")).parts
            path = site.joinpath(*parts)
            if ".." in parts or not path.is_file():
                return self.send(b"Not found", "text/plain", 404)
            self.file(path)

        def file(self, path: Path) -> None:
            """A static file, by byte ranges for the video to seek."""
            size = path.stat().st_size
            span = range_of(self.headers.get("Range"), size)
            first, last = span or (0, size - 1)
            kinds = {".js": "text/javascript", ".css": "text/css", ".mp4": "video/mp4", ".webp": "image/webp", ".png": "image/png"}
            self.send_response(206 if span else 200)
            self.send_header("Content-Type", kinds.get(path.suffix.lower(), "application/octet-stream"))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(last - first + 1))
            if span:
                self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(first)
                left = last - first + 1
                try:
                    while left > 0:
                        chunk = f.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with lock:
                log = load_log(answers)
                if self.path == "/name":
                    jersey = body.get("jersey")
                    set_name(match, questions, int(body["team"]), int(body["identity"]), body.get("name"), None if jersey in (None, "") else int(jersey))
                    return self.send(b"{}", "application/json")
                if self.path == "/answer":
                    _, refs = questions.build({entry["id"] for entry in log})
                    if body["id"] not in refs:
                        return self.send(b'{"error":"unknown question"}', "application/json", 400)
                    log.append({"id": body["id"], "choice": body["choice"], **constraints(str(body["choice"]), refs[body["id"]])})
                elif self.path == "/undo" and log:
                    log.pop()
                save(answers, log)
                # Undoing an answer may undo an applied one: both recompute.
                if self.path in ("/apply", "/undo"):
                    identity.rerun(match, video, squad)
                    questions.load()
                    if self.path == "/apply":
                        remember(roster, match.name, identity.named(questions.table, identity.read_names(match)), questions.vectors, team_names())
                    web.build(match, video, court, site, theme=theme, footage="full", pictured={1, 2})
                    # The published page follows, with its own choices.
                    if (match / "page.json").exists():
                        web.publish(match, video, court, theme, {})
            self.send(json.dumps({"answered": len(log)}).encode(), "application/json")

        def log_message(self, *args) -> None:
            pass

    # The footage shows minors: this machine only.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/review"
    print(f"Review: {url} (Ctrl+C to stop)", flush=True)
    if browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Review the doubtful player identities on the video, in the browser.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO), run with --players")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--court", type=Path, required=True, help="Court calibration JSON the match was run with")
    parser.add_argument("--squad", type=identity.parse_squad, help="Players per team, N or N1,N2")
    parser.add_argument("--theme", default="aspom", help="Club theme of the match page (web.py)")
    parser.add_argument("--roster", type=Path, default=ROSTER, help=f"The club's named players across matches (default: {ROSTER})")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the page in the browser")
    args = parser.parse_args()
    serve(args.match, args.video, args.court, args.squad, args.theme, args.port, not args.no_browser, args.roster)


if __name__ == "__main__":
    main()
