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
import hashlib
import json
import queue
import re
import threading
import time
import webbrowser
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import cv2
import numpy as np

from volleyball_stats import attribution, files, identity, jerseys, matches, web
from volleyball_stats.teams import parse_colour

# Frames between two boxes of a question's outline, pictures shown per piece and per identity, and
# frames looked at for the clearest picture of a piece.
BOX_STEP, PIECE_CROPS, IDENTITY_CROPS, CANDIDATES = 2, 3, 8, 12
# A player is alone in a frame where no other box covers ALONE of theirs.
ALONE = 0.05
CROP_PX, CROP_MARGIN = 448, 0.15
READERS = 4
KINDS = ("same", "different", "not_player", "cut", "touch", "rally", "receiver")
# Named players on court during more than TOGETHER of a card's time are not suggested for it: on
# the first ASPOM match, the right name overlapped 0-7%, the others 18-99%.
TOGETHER = 0.15
# Pieces looking most like a player offered to confirm at once, at least MORE_S long.
MORE, MORE_S = 24, 1.0
# Pictures spread over a piece in a conflict, to see whether the tracking swapped players.
STRIP = 24
# Doubts under MIN_IMPACT (seconds of play, a touch counting as 10, times the doubt: identity.doubts)
# are not asked: their answers barely move the numbers, and there are always more.
MIN_IMPACT = 10.0
# Doubtful touches (`doubtful`) are asked first, each clip TOUCH_AROUND_S on both sides of the touch,
# zoomed on where it happens, outlined and slowed to TOUCH_SLOW only TOUCH_SHOWN_S on both sides of
# it (a contact found up to a few frames off): only that moment is asked about.
TOUCH_AROUND_S, TOUCH_SHOWN_S, TOUCH_SLOW = 1.5, 0.25, 0.25
UNKNOWN = ("", "0")
# An ace's receiver is asked on its flight, slowed from the serve to its landing (ACE_FLIGHT_S after
# the serve when unseen), zoomed out to ACE_ZOOM players' height around the landing.
ACE_FLIGHT_S, ACE_ZOOM = 1.5, 4
# Touches not doubted asked too, the same ones each time: how many wrong picks the doubts miss.
SPOT_CHECKS = 20
# A rally window asked about is played whole with RALLY_AROUND_S on both sides, unzoomed.
RALLY_AROUND_S = 1.0
ROSTER = Path("outputs/roster.json")
# What the identities were last computed from (`state`), to tell what an apply would change.
APPLIED = "identity_applied.json"
# Undo takes back the UNDOS latest of the CHANGES whole, then drops the last answer. Request bodies
# are at most MAX_BODY bytes.
UNDOS, MAX_BODY = 100, 1 << 20
# Where the review's copy of the match page keeps the reports of what is wrong in a moment.
FEEDBACK = "feedback.log"
CHANGES = ("/answer", "/odd", "/more", "/repin", "/forget", "/cut")


def with_review(html: str) -> str:
    """The page loading review.js right after data.js (its build hash in the query or not), before
    the app that reads both."""
    return re.sub(r'(<script defer src="data\.js[^"]*"></script>)', r'\1<script defer src="review.js"></script>', html, count=1)
# Matches of a player the roster keeps (the latest), and names suggested per identity.
ROSTER_MATCHES, SUGGESTIONS = 5, 3

Ref = dict


def mid(start: int, end: int) -> int:
    return (start + end) // 2


class Questions:
    """The review's questions from a match folder's identities, candidates and player tracks."""

    def __init__(self, match: Path, fps: float):
        self.match, self.fps = match, fps
        # Pieces marked as someone else: never a player's pin.
        self.avoid: set[tuple[int, int, int] | None] = set()
        # frame, track, x1, y1, x2, y2 of every player box, sorted by frame (players.csv's order):
        # compact arrays, a 2-hour match holds millions of boxes.
        table = np.loadtxt(match / "players.csv", delimiter=",", skiprows=1, usecols=(0, 1, 3, 4, 5, 6, 10, 11), ndmin=2)
        # Where each box's feet stand on the court, in meters.
        self.court_of = table[:, 6:]
        table = table[:, :6].round().astype(np.int32)
        self.frame_of, self.box_of = table[:, 0], table[:, 2:]
        by_track = np.lexsort((table[:, 0], table[:, 1]))
        tracks, firsts = np.unique(table[by_track, 1], return_index=True)
        self.rows = {int(t): by_track[a:b] for t, a, b in zip(tracks, firsts, [*firsts[1:], len(by_track)])}
        # A touch's place is outlined in a square a player's median height.
        self.touch_side = float(np.median(self.box_of[:, 3] - self.box_of[:, 1])) if len(self.box_of) else 200.0
        self.load()

    def load(self) -> None:
        self.table = identity.read_identities(self.match / "identities.csv")
        self.candidates = json.loads((self.match / "identity_candidates.json").read_text())
        self.vectors = prototypes(self.match / "embeddings.npz", self.table)
        actions = web.read_csv(self.match / "actions.csv") if (self.match / "actions.csv").exists() else []
        rallies = web.read_csv(self.match / "rallies.csv") if (self.match / "rallies.csv").exists() else []
        windows = [(int(r["start_frame"]) - round(web.LEAD_S * self.fps), int(r["end_frame"])) for r in rallies]
        self.touches = doubtful(actions, windows)
        answers = self.match / "identity_answers.json"
        nothing = {str(a["frame"]) for a in (json.loads(answers.read_text()).get("touch", []) if answers.exists() else []) if a["identity"] is None}
        self.empty = [(w, r.get("set")) for w, r in zip(windows, rallies) if all(row["frame"] in nothing for row in touches_in(actions, w))]
        points = web.read_csv(self.match / "points.csv") if (self.match / "points.csv").exists() else [{}] * len(rallies)
        gone = web.no_rallies(self.match)
        played = [(w, p.get("winner")) for w, r, p in zip(windows, rallies, points) if int(r["start_frame"]) not in gone]
        self.aces = aces([r for r in actions if r["frame"] not in nothing], [w for w, _ in played], [p for _, p in played])

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

    def covered(self, row: int) -> float:
        """The share of a row's box the most overlapping other box of its frame covers."""
        frame, (x1, y1, x2, y2) = self.frame_of[row], self.box_of[row]
        others = self.box_of[np.searchsorted(self.frame_of, frame) : np.searchsorted(self.frame_of, frame, side="right")]
        w = np.clip(np.minimum(x2, others[:, 2]) - np.maximum(x1, others[:, 0]), 0, None)
        h = np.clip(np.minimum(y2, others[:, 3]) - np.maximum(y1, others[:, 1]), 0, None)
        share = w * h / max(1, (x2 - x1) * (y2 - y1))
        # The box itself covers all of itself.
        return float(np.sort(share)[-2]) if len(share) > 1 else 0.0

    def clear(self, track: int, start: int, end: int) -> int:
        """The frame of a piece where the track's box overlaps the other boxes least, among
        CANDIDATES spread over it: a picture of the player alone."""
        rows = self.track_rows(track, start, end)
        if not len(rows):
            return mid(start, end)
        picks = rows[:: max(1, len(rows) // CANDIDATES)]
        return int(self.frame_of[min(picks, key=lambda r: (self.covered(r), abs(self.frame_of[r] - mid(start, end))))])

    def pieces(self, team: int, number: int) -> list[tuple[int, int, int, int, int]]:
        """An identity's pieces, longest first."""
        return sorted((r for r in self.table if r[3] == team and r[4] == number), key=lambda r: r[1] - r[2])

    def cut(self, track: int, start: int, end: int, seconds: float) -> tuple[Ref, Ref] | None:
        """The boxes of a piece on either side of `seconds`, where the user saw the tracked player
        change; None at its edges."""
        frames = self.frame_of[self.track_rows(track, start, end)]
        at = round(seconds * self.fps)
        before, after = frames[frames <= at], frames[frames > at]
        if not len(before) or not len(after):
            return None
        return {"track": track, "frame": int(before[-1])}, {"track": track, "frame": int(after[0])}

    def segment_of(self, ref: Ref) -> tuple[int, int, int] | None:
        """The piece (track, start, end) of the last identity run holding a ref's frame, else the
        nearest one of its track."""
        mine = [r for r in self.table if r[0] == ref["track"]]
        if not mine:
            return None
        track, start, end, _, _ = min(mine, key=lambda r: max(r[1] - ref["frame"], ref["frame"] - r[2], 0))
        return track, start, end

    def ref(self, team: int, number: int) -> Ref:
        """The piece standing for an identity in answers and names: where its name was given, the
        user's own pin (its longest piece may be someone else's, in an identity joining two
        people), else its longest piece not marked as someone else (`avoid`)."""
        entries = identity.read_names(self.match)
        name = (identity.named(self.table, entries).get((team, number)) or {}).get("name")
        pinned = next((e["ref"] for e in entries if name and e.get("name") == name and identity.lookup(self.table, e["ref"]["track"], e["ref"]["frame"]) == (team, number)), None)
        if pinned:
            return dict(pinned)
        pieces = self.pieces(team, number)
        track, start, end, _, _ = next((r for r in pieces if tuple(r[:3]) not in self.avoid), pieces[0])
        return {"track": track, "frame": mid(start, end)}

    def faces(self, team: int, number: int) -> dict:
        """Pictures of an identity's longest pieces, and those pieces as answers refer to them."""
        pieces = [{"track": track, "frame": self.clear(track, start, end)} for track, start, end, _, _ in self.pieces(team, number)[:IDENTITY_CROPS]]
        return {"crops": [self.crop(p["track"], p["frame"]) for p in pieces], "pieces": pieces}

    def clip(self, track: int, start: int, end: int) -> dict:
        rows = [r for r in self.track_rows(track, start, end) if (self.frame_of[r] - start) % BOX_STEP == 0]
        return {
            "start": round(start / self.fps, 2),
            "end": round(end / self.fps, 2),
            "boxes": [[round(int(self.frame_of[r]) / self.fps, 3), *(int(v) for v in self.box_of[r])] for r in rows],
        }

    def touch_clip(self, frame: int, x: float, y: float) -> dict:
        """The clip around a touch at `frame`, its place (the ball then, at `x`, `y`) outlined."""
        half, at = self.touch_side / 2, frame / self.fps
        return {
            "start": round(at - TOUCH_SHOWN_S, 2),
            "end": round(at + TOUCH_SHOWN_S, 2),
            "around": TOUCH_AROUND_S - TOUCH_SHOWN_S,
            "slow": TOUCH_SLOW,
            "boxes": [[round(at, 3), round(x - half), round(y - half), round(x + half), round(y + half)]],
        }

    def split(self, segment: tuple[int, int, int], log: list[dict], names: list[dict], named: dict) -> dict:
        """A piece where two answers of a conflict meet, to look at and cut: its clip, filmstrip and
        the moments the answers name."""
        track, a, b = segment
        return {
            "id": f"split:{track}:{a}", "kind": "split", "clip": self.clip(track, a, b), "crops": [], "strip": self.strip(track, a, b),
            "moments": self.moments(track, a, b, log, names, named, None), "claim": None,
        }

    def moments(self, track: int, a: int, b: int, log: list[dict], names: list[dict], named: dict, skip: str | None) -> list[dict]:
        """Where the answers (but `skip`) and the names put someone inside a piece, with whom."""
        moments: dict[int, str | None] = {}
        inside = lambda r: isinstance(r, dict) and r["track"] == track and a <= r["frame"] <= b  # noqa: E731
        for e in log:
            if e["id"] == skip:
                continue
            for o, t in zip(e.get("odd", []), e.get("to") or [None] * len(e.get("odd", []))):
                if inside(o):
                    moments[o["frame"]] = self.claim(t, named, names) if isinstance(t, dict) else None
            for g in e.get("same", []):
                for r in g:
                    others = [x for x in g if x is not r and not inside(x)]
                    if inside(r) and others:
                        moments.setdefault(r["frame"], self.claim(others[0], named, names))
        for n in names:
            r = n["ref"]
            if n.get("name") and inside(r):
                moments[r["frame"]] = n["name"]
        return [{"time": round(f / self.fps, 2), "name": who, "crop": self.crop(track, f)} for f, who in sorted(moments.items())]

    def strip(self, track: int, start: int, end: int) -> list[dict]:
        """STRIP of a piece's boxes evenly spread over it, with their time and picture."""
        rows = self.track_rows(track, start, end)
        picks = rows[np.linspace(0, len(rows) - 1, min(STRIP, len(rows))).astype(int)] if len(rows) else []
        return [{"time": round(int(self.frame_of[r]) / self.fps, 2), "crop": self.crop(track, int(self.frame_of[r]))} for r in picks]

    def claim(self, ref: dict, named: dict, names: list[dict]) -> str:
        """Who a pin stands for: the name pinned on its piece, else its identity's name (identities
        joined by a conflict hold several), else its number."""
        piece = self.segment_of(ref)
        pinned = next((n["name"] for n in names if n.get("name") and self.segment_of(n["ref"]) == piece), None)
        who = identity.lookup(self.table, ref["track"], ref["frame"])
        return pinned or (named.get(who) or {}).get("name") or (f"#{who[1]}" if who else "?")

    def conflicts(self, log: list[dict], names: list[dict]) -> list[dict]:
        """The identities of the last run holding two names or more, each with the answers that
        chain the names' pieces through "same" links: most likely a piece showing two people. A
        piece answer comes with its clip and pictures, marked pictures with theirs."""
        pins: dict[str, list] = defaultdict(list)
        held: dict[tuple[int, int], set[str]] = defaultdict(set)
        for n in names:
            who = n.get("name") and identity.lookup(self.table, n["ref"]["track"], n["ref"]["frame"])
            if who:
                held[who].add(n["name"])
                pins[n["name"]].append(self.segment_of(n["ref"]))
        links: dict = defaultdict(list)
        for e in log:
            for g in e.get("same", []):
                for r in g[1:]:
                    a, b = self.segment_of(g[0]), self.segment_of(r)
                    links[a].append((b, e["id"]))
                    links[b].append((a, e["id"]))
        for segments in pins.values():
            for other in segments[1:]:
                links[segments[0]].append((other, None))
                links[other].append((segments[0], None))
        by_id = {e["id"]: e for e in log}
        named = identity.named(self.table, names)
        out = []
        for (team, number), together in held.items():
            if len(together) < 2:
                continue
            first, *rest = sorted(together)
            steps = path(links, set(pins[first]), {s for n in rest for s in pins[n]})
            ids = list(dict.fromkeys(a for _, a in steps if a))
            answers = [self.split(segment, log, names, named) for segment in meeting(steps) if segment]
            for answer_id in ids:
                if answer_id.startswith("piece:"):
                    track, start = (int(v) for v in answer_id.split(":")[1:3])
                    _, a, b = self.segment_of({"track": track, "frame": start})
                    cuts = [a + (b - a) * k // PIECE_CROPS for k in range(PIECE_CROPS + 1)]
                    crops = [self.crop(track, self.clear(track, x, y)) for x, y in zip(cuts, cuts[1:])]
                    shown = self.moments(track, a, b, log, names, named, answer_id)
                    # The player the answer joined the piece to: the other member of its "same" group.
                    piece = {"track": track, "frame": (a + b) // 2}
                    pins = [r for g in by_id[answer_id].get("same", []) for r in g if not (r["track"] == track and a <= r["frame"] <= b)]
                    claim = self.claim(pins[0], named, names) if pins else None
                    answers.append({
                        "id": answer_id, "kind": "piece", "clip": self.clip(track, a, b), "crops": crops, "moments": shown, "claim": claim,
                        "strip": self.strip(track, a, b), "piece": piece,
                    })
                elif by_id[answer_id].get("choice") == "odd":
                    entry = by_id[answer_id]
                    to = entry.get("to") or [None] * len(entry["odd"])
                    claims = [self.claim(t, named, names) if isinstance(t, dict) else None for t in to]
                    answers.append({"id": answer_id, "kind": "odd", "crops": [self.crop(o["track"], o["frame"]) for o in entry["odd"]], "claims": claims})
            out.append({"team": team, "identity": number, "names": sorted(together), "answers": answers, "pinned": self.pinned(log, names, together, named)})
        return out

    def pinned(self, log: list[dict], names: list[dict], together: set[str], named: dict) -> list[dict]:
        """The question answers pinning a piece on one of `together`'s names: an answer given while
        the names shared one player was pinned on that player's longest piece, whoever it showed.
        Each with a picture of its own piece and who it says the piece is."""
        pins = {self.segment_of(n["ref"]): n["name"] for n in names if n.get("name") in together}
        out = []
        for e in log:
            if not e["id"].startswith("piece:"):
                continue
            track, start = (int(v) for v in e["id"].split(":")[1:3])
            own = self.segment_of({"track": track, "frame": start})
            said = next((pins[self.segment_of(r)] for g in e.get("same", []) for r in g if self.segment_of(r) != own and self.segment_of(r) in pins), None)
            if said:
                _, a, b = own
                out.append({"id": e["id"], "crop": self.crop(track, self.clear(track, a, b)), "claim": said, "time": round(a / self.fps, 2)})
        return out

    def more(self, team: int, number: int, seen: set) -> list[dict]:
        """The MORE pieces of the team's other identities (or none) looking most like identity
        `number`'s card: its IDENTITY_CROPS longest pieces not marked as someone else, which the
        user sees and fixes, where all its pieces may mix people. MORE_S or longer, seen at no
        moment a card piece is (nobody is in two places), neither in `seen` nor marked. Raw
        embeddings rank better here than the identity step's whitened ones, which magnify faint
        directions: 23 of 24 right against 15 on two players of the first ASPOM match."""
        vectors = piece_vectors(self.match / "embeddings.npz")
        card = [tuple(r[:3]) for r in self.pieces(team, number) if tuple(r[:3]) not in self.avoid and tuple(r[:3]) in vectors][:IDENTITY_CROPS]
        if not card:
            return []
        unit = {c: vectors[c] / max(float(np.linalg.norm(vectors[c])), 1e-9) for c in card}
        look = np.average([unit[c] for c in card], axis=0, weights=[c[2] - c[1] + 1 for c in card])
        look /= max(float(np.linalg.norm(look)), 1e-9)
        starts, ends = np.array([c[1] for c in card]), np.array([c[2] for c in card])
        ranked = []
        for track, start, end, t, n in self.table:
            key = (track, start, end)
            if t != team or n == number or key not in vectors or (end - start + 1) < MORE_S * self.fps or key in seen | self.avoid or np.any((starts <= end) & (start <= ends)):
                continue
            ranked.append((float(vectors[key] @ look) / max(float(np.linalg.norm(vectors[key])), 1e-9), track, start, end))
        out = []
        for _, track, start, end in sorted(ranked, reverse=True)[:MORE]:
            frame = self.clear(track, start, end)
            out.append({"track": track, "frame": frame, "crop": self.crop(track, frame)})
        return out

    def together(self, team: int, number: int, names: dict) -> set[str]:
        """The names of this match's named players on court during more than TOGETHER of identity
        `number`'s card (its IDENTITY_CROPS longest pieces): not them, nobody being in two places. A
        share, not any overlap: a named player's pieces may still hold a few of someone else's."""
        card = self.pieces(team, number)[:IDENTITY_CROPS]
        length = sum(b - a + 1 for _, a, b, _, _ in card)
        out = set()
        for (t, n), given in names.items():
            if t != team or n == number or not given.get("name"):
                continue
            theirs = self.pieces(t, n)
            over = 0
            for _, a, b, _, _ in card:
                covered = np.zeros(b - a + 1, bool)
                for _, c, d, _, _ in theirs:
                    if max(a, c) <= min(b, d):
                        covered[max(a, c) - a : min(b, d) - a + 1] = True
                over += int(covered.sum())
            if over > TOGETHER * length:
                out.add(given["name"])
        return out

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
                **self.faces(team, number), "name": given.get("name"), "jersey": given.get("jersey"),
                "suggestions": suggest(self.vectors.get((team, number)), roster, teams[team - 1], self.together(team, number, names)),
            })
        return out

    def build(self, asked: set[str]) -> tuple[list[dict], dict[str, dict]]:
        """The questions not asked yet, most at stake first, and what each answer means (the refs)."""
        out, refs = [], {}
        for c in self.candidates["segments"]:
            qid = f"piece:{c['track']}:{c['start_frame']}"
            options = [n for n in (c["identity"], c["runner_up"]) if n]
            if qid in asked or not options or c["track"] not in self.rows or c["impact"] < MIN_IMPACT:
                continue
            track, start, end = c["track"], c["start_frame"], c["end_frame"]
            cuts = [start + (end - start) * k // PIECE_CROPS for k in range(PIECE_CROPS + 1)]
            picks = sorted({self.clear(track, a, b) for a, b in zip(cuts, cuts[1:])})
            out.append({
                "id": qid, "kind": "piece", "team": c["team"], "identity": c["identity"], "impact": c["impact"],
                "seconds": c["seconds"], "contacts": c["contacts"], "clip": self.clip(track, start, end),
                "crops": [self.crop(track, f) for f in picks],
                "choices": [{"identity": n, **self.faces(c["team"], n)} for n in options],
            })
            refs[qid] = {"piece": {"track": track, "frame": mid(start, end)}, "choices": [self.ref(c["team"], n) for n in options]}
        for c in self.candidates["merges"]:
            team, (a, b) = c["team"], c["identities"]
            qid = f"merge:{team}:{a}:{b}"
            if qid in asked or c["impact"] < MIN_IMPACT:
                continue
            examples = [self.clip(e["track"], e["start_frame"], e["end_frame"]) for e in c["examples"]]
            out.append({
                "id": qid, "kind": "merge", "team": team, "identity": a, "impact": c["impact"], "seconds": sum(c["seconds"]),
                "contacts": sum(c["contacts"]), "clip": examples[0], "other": examples[1],
                "crops": [], "choices": [{"identity": n, **self.faces(team, n)} for n in (a, b)],
            })
            refs[qid] = {"choices": [self.ref(team, a), self.ref(team, b)]}
        touches = []
        for r, reason in self.touches:
            frame, team = int(r["frame"]), int(r["team"])
            qid = f"touch:{frame}"
            if qid in asked:
                continue
            touches.append({
                "id": qid, "kind": "touch", "team": team, "identity": None, "impact": identity.CONTACT_S, "seconds": 0, "contacts": 1,
                "action": r["type"], "time": round(frame / self.fps, 2), "clip": self.touch_clip(frame, float(r["x"]), float(r["y"])), "crops": [], "choices": [],
                "reason": reason, "proposed": None if r["identity"] in UNKNOWN else int(r["identity"]),
            })
            refs[qid] = {"touch": {"frame": frame, "team": team}}
        missed = []
        for serve, landing in self.aces:
            frame, team = int(serve["frame"]), 3 - int(serve["team"])
            qid = f"receiver:{frame}"
            if qid in asked:
                continue
            at, side = (int(landing["frame"]) if landing else frame + round(ACE_FLIGHT_S * self.fps)), ACE_ZOOM * self.touch_side / 2
            box = [[round(at / self.fps, 3), *(round(float(landing[k]) + d * side) for d, k in ((-1, "x"), (-1, "y"), (1, "x"), (1, "y")))]] if landing else []
            missed.append({
                "id": qid, "kind": "touch", "team": team, "identity": None, "impact": identity.CONTACT_S, "seconds": 0, "contacts": 1,
                "action": "serve", "time": round(frame / self.fps, 2), "reason": "ace", "proposed": None, "crops": [], "choices": [],
                "clip": {"start": round(frame / self.fps, 2), "end": round(at / self.fps, 2), "around": TOUCH_AROUND_S, "slow": TOUCH_SLOW, "boxes": box},
            })
            refs[qid] = {"receiver": {"frame": frame, "team": team}}
        found = []
        for (start, end), number in self.empty:
            qid = f"rally:{start}"
            if qid in asked:
                continue
            found.append({
                "id": qid, "kind": "rally", "team": 1, "identity": None, "impact": 0, "seconds": round((end - start) / self.fps, 1), "contacts": 0,
                "set": int(number) if number else None, "time": round(start / self.fps, 2), "crops": [], "choices": [],
                "clip": {"start": round(start / self.fps, 2), "end": round(end / self.fps, 2), "around": RALLY_AROUND_S, "boxes": []},
            })
            refs[qid] = {"rally": {"start": start + round(web.LEAD_S * self.fps)}}
        return found + missed + touches + sorted(out, key=lambda q: -q["impact"]), refs


def constraints(choice: str, refs: dict, player: Ref | None = None, cut: tuple[Ref, Ref] | None = None) -> dict[str, list]:
    """What an answer adds to identity_answers.json. A piece is one of its `choices` (index) and not
    the other, someone else ("other"), not a player, the identity of the `player` piece said by
    name ("player:TEAM:IDENTITY", that player first so the piece takes their team) and none of the
    other choices, or two players: cut between the boxes of `cut` ("cut"), two different people;
    two identities are one player ("same") or two ("different"); "skip" adds nothing."""
    piece, options = refs.get("piece"), refs["choices"]
    if choice == "cut" and cut is not None:
        return {"cut": [cut[0]], "different": [list(cut)]}
    if player is not None:
        rest = [r for r in options if r != player]
        return {"same": [[player, piece]], **({"different": [[piece, *rest]]} if rest else {})}
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


def touches_in(actions: list[dict], window: tuple[int, int]) -> list[dict]:
    """actions.csv's touches inside `window` (its lead included)."""
    return [r for r in actions if r["type"] not in web.NO_PLAYER and window[0] <= int(r["frame"]) <= window[1]]


def aces(actions: list[dict], windows: list[tuple[int, int]], winners: list[str | None]) -> list[tuple[dict, dict | None]]:
    """The serves of actions.csv's rows (frame order) that the page makes aces as their window's
    (lead included) last touch, their team its winner (`winners`, points.csv's by window), each with
    the row after it in the window (the landing), None when unseen."""
    out = []
    for (start, end), winner in zip(windows, winners):
        rows = [r for r in actions if start <= int(r["frame"]) <= end]
        touches = [r for r in rows if r["type"] not in web.NO_PLAYER]
        if winner and touches and touches[-1]["type"] == "serve" and touches[-1].get("team") == winner:
            out.append((touches[-1], next((r for r in rows if int(r["frame"]) > int(touches[-1]["frame"])), None)))
    return out


def receiver_answer(ace: dict, choice: str, given: dict[tuple[int, int], dict]) -> dict:
    """What an answer to an ace's receiver question adds to identity_answers.json: the player of
    "player:TEAM:IDENTITY" missed it, with the name `given` them, or no one ("nobody"); nothing for
    another answer."""
    if choice == "not_play":
        return {}
    return {"receiver": found} if (found := touch_answer(ace, choice, given).get("touch")) else {}


def rally_answer(rally: dict, choice: str) -> dict:
    """What an answer to a rally question adds to identity_answers.json: the window (by its start
    frame) is a rally ("rally") or no play ("not_play"); nothing for another answer."""
    return {"rally": [{**rally, "play": choice == "rally"}]} if choice in ("rally", "not_play") else {}


def doubtful(actions: list[dict], windows: list[tuple[int, int]]) -> list[tuple[dict, str]]:
    """The touches of actions.csv's rows (frame order) to ask who made, with why, most at stake
    first: no player of the touch's team known for it ("unknown"); one player touching twice in a
    row in a rally, blocks aside ("twice", the less sure touch of the two); SPOT_CHECKS of the others
    picked at random, the same each run ("check"); another player about as near the ball
    (attribution.DOUBT, "close", the nearest first)."""
    touch = lambda r: r["type"] not in web.NO_PLAYER and bool(r.get("team"))  # noqa: E731
    gap = lambda r: float(r["gap"]) if r.get("gap") else float("inf")  # noqa: E731
    rally = lambda r: next((k for k, (a, b) in enumerate(windows) if a <= int(r["frame"]) <= b), None)  # noqa: E731
    found = {r["frame"]: (r, "unknown") for r in actions if touch(r) and r.get("identity") in UNKNOWN}
    for a, b in zip(actions, actions[1:]):
        same = touch(a) and touch(b) and a.get("identity") not in UNKNOWN and (a["team"], a["identity"]) == (b["team"], b["identity"])
        if same and "block" not in (a["type"], b["type"]) and rally(a) is not None and rally(a) == rally(b):
            r = min(a, b, key=gap)
            found.setdefault(r["frame"], (r, "twice"))
    close = sorted((r for r in actions if touch(r) and gap(r) < attribution.DOUBT and r["frame"] not in found), key=gap)
    rest = [r for r in actions if touch(r) and r["frame"] not in found and gap(r) >= attribution.DOUBT]
    checks = sorted(rest, key=lambda r: hashlib.sha256(r["frame"].encode()).hexdigest())[:SPOT_CHECKS]
    return list(found.values()) + [(r, "check") for r in checks] + [(r, "close") for r in close]


def touch_answer(touch: dict, choice: str, given: dict[tuple[int, int], dict]) -> dict:
    """What an answer to a touch question adds to identity_answers.json: the touch is the player's
    of "player:TEAM:IDENTITY", with the name `given` them, which outlives the identities' numbers;
    no touch at all for "nobody" (identity None), nor for "not_play", outside the play (also
    `play` false: where the rallies step went wrong); nothing for another answer."""
    if choice in ("nobody", "not_play"):
        return {"touch": [{**touch, "identity": None, "name": None, **({"play": False} if choice == "not_play" else {})}]}
    if not choice.startswith("player:"):
        return {}
    player = tuple(int(v) for v in choice.split(":")[1:3])
    return {"touch": [{**touch, "identity": player[1], "name": (given.get(player) or {}).get("name")}]}


def piece_key(ref: Ref) -> str:
    return f"{ref['track']}:{ref['frame']}"


def odd_entry(entry_id: str, odd: list[Ref], rest: list[Ref], to: list[Ref | str | None]) -> dict:
    """An answer marking the `odd` pictures of a player against the `rest`, with whom each one is
    (`to`, see `mark_odd`)."""
    same = [[t, o] for o, t in zip(odd, to) if isinstance(t, dict)]
    gone = [o for o, t in zip(odd, to) if t == "not_player"]
    return {
        "id": entry_id, "choice": "odd", "odd": odd, "to": to, "rest": rest, "different": [[o, r] for o in odd for r in rest],
        **({"same": same} if same else {}), **({"not_player": gone} if gone else {}), "applied": False,
    }


def mark_odd(log: list[dict], odd: list[Ref], rest: list[Ref], to: list[Ref | str | None] | None = None, keep: frozenset[str] = frozenset()) -> list[dict]:
    """`log` with one identity's pictures marked: the `odd` pieces show other people than the
    `rest`, each a different player from each of them, and the player of `to`'s piece when given
    (`to` aligned with `odd`; that player first, so the piece takes their team), or no player
    ("not_player"). Kept with every picture odd too, for their players and the marks; replaces the
    earlier marks of these pictures, also those made among other pictures (before an apply changed
    them), and removes them when none is odd; but the earlier marks of `keep`'s pieces."""
    shown = {piece_key(r) for r in odd + rest}
    entry_id = "odd:" + ",".join(sorted(shown))
    replaced = shown - keep
    out = []
    for entry in log:
        if entry["id"] == entry_id:
            continue
        if entry.get("choice") == "odd" and any(piece_key(o) in replaced for o in entry["odd"]):
            kept = [(o, t) for o, t in zip(entry["odd"], entry.get("to") or [None] * len(entry["odd"])) if piece_key(o) not in replaced]
            if not kept:
                continue
            # Answers saved before "rest" was kept hold it in their pairs.
            others = entry.get("rest") or list({piece_key(r): r for _, r in entry["different"]}.values())
            entry = odd_entry(entry["id"], [o for o, _ in kept], others, [t for _, t in kept])
        out.append(entry)
    if odd:
        out.append(odd_entry(entry_id, odd, rest, to or [None] * len(odd)))
    return out


def settled(log: list[dict], where) -> set[str]:
    """Pieces marked as someone else that an apply moved as marked: to the player they were said to
    be, or, said to be no one in particular, away from the pictures they were marked among. `where`
    gives a ref's (team, identity)."""
    out = set()
    for e in log:
        among = {where(r) for r in e.get("rest", [])}
        for o, t in zip(e.get("odd", []), e.get("to") or [None] * len(e.get("odd", []))):
            now = where(o)
            if now is not None and (now == where(t) if isinstance(t, dict) else t is None and among and now not in among):
                out.add(piece_key(o))
    return out


def supersede(log: list[dict], odd: list[Ref], keep: str, belongs, segment_of) -> list[dict]:
    """`log` with the earlier answers joining one of the `odd` pieces (marked in a card) to the card's
    player (`belongs` tells their pins) letting go of that piece: the latest judgment wins.
    `keep` is the marking answer itself."""
    gone = {segment_of(o) for o in odd}
    out = []
    for e in log:
        if e["id"] != keep and e.get("same"):
            same = []
            for g in e["same"]:
                if any(segment_of(r) in gone for r in g) and any(belongs(r) and segment_of(r) not in gone for r in g):
                    g = [r for r in g if segment_of(r) not in gone]
                if len(g) > 1:
                    same.append(g)
            e = {**e, "same": same}
        out.append(e)
    return out


def name_merges(log: list[dict], names: list[dict], segment_of) -> set[frozenset[str]]:
    """The sets of different names the answers' "same" links join into one player, each name's pins
    being one player: what an apply would merge whatever the looks."""
    parent: dict = {}

    def root(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a, b) -> None:
        parent[root(a)] = root(b)

    for e in log:
        for g in e.get("same", []):
            for r in g[1:]:
                join(segment_of(g[0]), segment_of(r))
    first: dict[str, object] = {}
    for n in names:
        if n.get("name"):
            join(first.setdefault(n["name"], segment_of(n["ref"])), segment_of(n["ref"]))
    held: dict = {}
    for n in names:
        if n.get("name"):
            held.setdefault(root(segment_of(n["ref"])), set()).add(n["name"])
    return {frozenset(v) for v in held.values() if len(v) > 1}


def path(links: dict, starts: set, goals: set) -> list[tuple]:
    """The steps (node, answer id or None leading to it) of the shortest path of `links` ({node:
    [(node, answer id or None)]}) from one of `starts` to one of `goals`; none without a path."""
    seen = {s: None for s in starts}
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        if node in goals:
            steps = []
            while seen[node]:
                before, answer_id = seen[node]
                steps.append((node, answer_id))
                node = before
            return [(node, None), *steps[::-1]]
        for other, answer_id in links[node]:
            if other not in seen:
                seen[other] = (node, answer_id)
                queue.append(other)
    return []


def chain(links: dict, starts: set, goals: set) -> list[str]:
    """The answers (ids, in order) along the shortest path of `links` between `starts` and `goals`."""
    return list(dict.fromkeys(a for _, a in path(links, starts, goals) if a))


def meeting(steps: list[tuple]) -> list:
    """The nodes of a path where two different answers meet: a piece each says is someone, most
    likely showing both."""
    return [steps[k][0] for k in range(1, len(steps) - 1) if steps[k][1] and steps[k + 1][1] and steps[k][1] != steps[k + 1][1]]


def reanchor(log: list[dict], names: list[dict], moved: dict, segment_of) -> tuple[list[dict], list[dict]]:
    """Answers and names with their pins (the piece standing for a player: a name, a "C'est…"
    choice, the players a question offered) that lie in a piece of `moved`, shown as someone else,
    moved to the piece given there: a pin follows the person, not a picture of someone else.
    `segment_of` gives a ref's piece."""

    def fix(ref):
        return moved.get(segment_of(ref), ref) if isinstance(ref, dict) else ref

    out = []
    for e in log:
        choice = str(e.get("choice"))
        if choice == "odd":
            to = [fix(t) for t in e.get("to") or [None] * len(e["odd"])]
            if to != e.get("to"):
                # Answers saved before "rest" was kept hold it in their pairs.
                rest = e.get("rest") or list({piece_key(r): r for _, r in e["different"]}.values())
                e = odd_entry(e["id"], e["odd"], rest, to)
        elif e["id"].startswith("merge:"):
            e = {**e, **{k: [[fix(r) for r in g] for g in e[k]] for k in ("same", "different") if k in e}}
        elif choice == "more":
            # The player's pin first in "same", second in each "different" pair.
            e = {**e, **({"same": [[fix(g[0]), *g[1:]] for g in e["same"]]} if "same" in e else {}), **({"different": [[g[0], fix(g[1])] for g in e["different"]]} if "different" in e else {})}
        elif choice.isdigit() or choice == "other" or choice.startswith("player:"):
            # The question's piece comes first in each group, but after the player said by name.
            same = [[fix(g[0]), *g[1:]] if choice.startswith("player:") else [g[0], *map(fix, g[1:])] for g in e.get("same", [])]
            e = {**e, **({"same": same} if "same" in e else {}), **({"different": [[g[0], *map(fix, g[1:])] for g in e["different"]]} if "different" in e else {})}
        out.append(e)
    return out, [{**n, "ref": fix(n["ref"])} for n in names]


def save(path: Path, log: list[dict]) -> None:
    """identity_answers.json from the answers' `log`, the source of its constraint lists."""
    data = {kind: [x for entry in log for x in entry.get(kind, [])] for kind in KINDS}
    files.write_text(path, json.dumps({**data, "log": log}, indent=1) + "\n")


def piece_vectors(cache: Path) -> dict[tuple[int, int, int], np.ndarray]:
    """Each piece's (track, start, end) re-identification embedding from the embedding cache."""
    if not cache.exists():
        return {}
    data = np.load(cache)
    return {tuple(round(v) for v in k[:3]): x for k, x in zip(data["keys"].tolist(), data["vectors"].astype(float))}


def prototypes(cache: Path, table: list[tuple[int, int, int, int, int]]) -> dict[tuple[int, int], np.ndarray]:
    """Each identity's unit re-identification embedding, its pieces' (the embedding cache) averaged by
    length; not whitened, the roster compares them across matches."""
    vectors = piece_vectors(cache)
    sums: dict[tuple[int, int], np.ndarray] = {}
    for track, start, end, team, number in table:
        v = vectors.get((track, start, end))
        if number and v is not None:
            sums[team, number] = sums.get((team, number), 0.0) + (end - start + 1) * v / max(float(np.linalg.norm(v)), 1e-9)
    return {k: v / max(float(np.linalg.norm(v)), 1e-9) for k, v in sums.items()}


def load_roster(path: Path) -> list[dict]:
    return json.loads(path.read_text())["players"] if path.exists() else []


def suggest(vector: np.ndarray | None, roster: list[dict], team: str | None, unless: set[str] = frozenset()) -> list[dict]:
    """The names and jersey numbers of the roster's players of `team` (every player for an unnamed
    team) who look most like `vector`, best first, but those in `unless`."""
    if vector is None:
        return []
    scored = []
    for player in roster:
        if team and player.get("team") and player["team"] != team or player["name"] in unless:
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
    files.write_text(path, json.dumps({"players": [p for p in roster if p["vectors"]]}, ensure_ascii=False) + "\n")


def set_name(match: Path, questions: Questions, team: int, number: int, given: str | None, jersey: int | None) -> None:
    """player_names.json with identity `number` of `team` named `given` and its `jersey` number:
    the entries giving it its name renamed in place, the first holding the number; both None removes
    them. Entries of another name on it (two people joined) stay. A new entry refers to the
    identity's longest piece not marked as someone else."""
    entries = identity.read_names(match)
    shown = identity.named(questions.table, entries).get((team, number))
    mine = [e for e in entries if shown and identity.lookup(questions.table, e["ref"]["track"], e["ref"]["frame"]) == (team, number) and (e.get("name") or None) == shown["name"]]
    given = (given or "").strip() or None
    if not given and jersey is None:
        entries = [e for e in entries if not any(e is m for m in mine)]
    elif mine:
        for k, e in enumerate(mine):
            e.update(name=given, jersey=jersey if k == 0 else None)
    else:
        entries.append({"ref": questions.ref(team, number), "name": given, "jersey": jersey})
    write_names(match, entries)


def set_photo(match: Path, table: list, team: int, number: int, frame: int, box: list[int]) -> None:
    """web.PHOTO_PICKED with the card picture of identity `number` of `team` taken at `frame` in
    `box`, by the player's name (it outlives the identities' numbers); ValueError for an unnamed one."""
    who = (identity.named(table, identity.read_names(match)).get((team, number)) or {}).get("name")
    if not who:
        raise ValueError(f"player {team}:{number} has no name")
    path = match / web.PHOTO_PICKED
    taken = json.loads(path.read_text()) if path.exists() else {}
    taken[who] = {"frame": int(frame), "box": [int(v) for v in box]}
    files.write_text(path, json.dumps(taken, indent=1, ensure_ascii=False) + "\n")


def set_team(match: Path, team: int, name: str | None, colour: str | None) -> None:
    """teams.json with team `team` (1 or 2) named `name` (None: its default name) and shown in
    `colour` (#rrggbb or a colour's name; None: its jersey's). ValueError for anything else."""
    path = match / "teams.json"
    data = json.loads(path.read_text())
    read = parse_colour(colour) if colour else None
    if team not in (1, 2) or (colour and read is None):
        raise ValueError(f"team {team}, colour {colour!r}")
    data["teams"][team - 1].update(name=(name or "").strip() or None, colour=read)
    files.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_names(match: Path, entries: list[dict]) -> None:
    files.write_text(match / identity.NAMES, json.dumps({"players": entries}, indent=1, ensure_ascii=False) + "\n")


def load_log(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("log", []) if path.exists() else []


def state(match: Path, log: list[dict]) -> dict:
    """What the identities are computed from: the answers' constraints, the names and the date of
    the jersey numbers, as JSON gives them back."""
    read = match / jerseys.FILE
    found = {"answers": {kind: [x for e in log for x in e.get(kind, [])] for kind in KINDS}, "names": identity.read_names(match), "jerseys": read.stat().st_mtime if read.exists() else None}
    return json.loads(json.dumps(found))


def waiting(match: Path, log: list[dict]) -> dict:
    """What an apply would take in: the answers saying something not applied yet (those saved
    before the flag were), whether the answers or the jersey numbers, and the names, differ from
    what the identities were computed from (APPLIED)."""
    computed = match / APPLIED
    now, then = state(match, log), json.loads(computed.read_text()) if computed.exists() else {}
    return {
        "pending": sum(not e.get("applied", True) and any(e.get(kind) for kind in KINDS) for e in log),
        "changed": (now["answers"], now["jerseys"]) != (then.get("answers"), then.get("jerseys")),
        "namesPending": now["names"] != then.get("names"),
    }


def undo(log: list[dict], history: list[dict]) -> tuple[list[dict], list[dict] | None, str | None, bool]:
    """The answers as they were before the last change of `history` ({"log", "names": None unless
    it moved names, "applied": whether an apply followed it}, popped), else (`history` empty: the
    server restarted) without the last answer. With the names to write back (None to keep them),
    the id of the answer taken away, and whether the identities followed what is undone."""
    if history:
        last = history.pop()
        kept = {e["id"] for e in last["log"]}
        return last["log"], last["names"], next((e["id"] for e in reversed(log) if e["id"] not in kept), None), last["applied"]
    return log[:-1], None, log[-1]["id"], log[-1].get("applied", True)


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
    web.build(match, video, court, site, theme=theme, footage="full", pictured={1, 2}, feedback="feedback")
    cap = cv2.VideoCapture(str(video))
    fps, width, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    answers = match / "identity_answers.json"
    if not (match / "identity_candidates.json").exists():
        identity.rerun(match, video, squad)
    questions = Questions(match, fps)
    where = lambda r: identity.lookup(questions.table, r["track"], r["frame"])  # noqa: E731
    computed = match / APPLIED
    done = match / "identities.csv"
    if not computed.exists() and done.exists() and all(not f.exists() or f.stat().st_mtime < done.stat().st_mtime for f in (answers, match / identity.NAMES)):
        files.write_text(computed, json.dumps(state(match, load_log(answers))))
    # The answers and names before each change since the server started, for undo (see `undo`).
    history: list[dict] = []
    lock = threading.Lock()
    # Pictures are cut from the video by READERS at once, then kept on disk: a 4K seek costs 0.35 s.
    readers: queue.Queue = queue.Queue()
    for _ in range(READERS):
        readers.put(cv2.VideoCapture(str(video)))
    kept = match / "crops"

    def picture(frame: int, box: tuple[int, int, int, int]) -> bytes:
        path = kept / f"{CROP_PX}_{frame}_{'_'.join(map(str, box))}.jpg"
        if path.exists():
            return path.read_bytes()
        capture = readers.get()
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
            ok, image = capture.read()
        finally:
            readers.put(capture)
        if not ok:
            return b""
        x1, y1, x2, y2 = box
        mx, my = round((x2 - x1) * CROP_MARGIN), round((y2 - y1) * CROP_MARGIN)
        part = image[max(0, y1 - my) : max(0, y2 + my), max(0, x1 - mx) : max(0, x2 + mx)]
        if not part.size:
            return b""
        part = cv2.resize(part, (max(1, round(part.shape[1] * CROP_PX / part.shape[0])), CROP_PX), interpolation=cv2.INTER_CUBIC)
        body = cv2.imencode(".jpg", part, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
        kept.mkdir(exist_ok=True)
        files.write_bytes(path, body)
        return body

    # Where an apply stands, for the page's progress bar: the steps, the one running since when, and
    # each step's last duration (first guesses from the first ASPOM match).
    progress: dict = {}
    took = {"players": 30.0, "questions": 3.0, "roster": 1.0, "review": 10.0, "page": 10.0, "hosting": 60.0}
    # The last hosting (publish.json): when, and why it failed; the page says it.
    hosted: dict = {}

    def hosting() -> None:
        try:
            matches.host(match, video, court, theme, json.loads((match / matches.PUBLISH).read_text()))
            hosted.update(at=time.strftime("%H:%M"), error=None)
        except Exception as error:  # noqa: BLE001
            # The answers stay applied: only the hosted page is behind.
            hosted.update(at=time.strftime("%H:%M"), error=str(error) or type(error).__name__)

    def pages() -> list:
        """The steps rebuilding the review's page, the published one with its own choices, then the
        hosted ones when the match folder says how (publish.json)."""
        steps = [("review", lambda: web.build(match, video, court, site, theme=theme, footage="full", pictured={1, 2}, feedback="feedback"))]
        if (match / "page.json").exists():
            steps.append(("page", lambda: web.publish(match, video, court, theme, {})))
        if (match / matches.PUBLISH).exists():
            steps.append(("hosting", hosting))
        return steps

    def run_steps(steps: list) -> None:
        progress.update(steps=[name for name, _ in steps], took=took)
        try:
            for k, (name, work) in enumerate(steps):
                progress.update(done=k, since=time.time())
                work()
                took[name] = time.time() - progress["since"]
        finally:
            progress.clear()

    def warm() -> None:
        """Cuts the review's pictures ahead of the user, READERS at a time."""
        found, _ = questions.build(set())
        urls = re.findall(r"crop\?f=(\d+)&b=([\d,-]+)", json.dumps([found, questions.players([], team_names())]))
        with ThreadPoolExecutor(READERS) as pool:
            list(pool.map(lambda u: picture(int(u[0]), tuple(int(v) for v in u[1].split(","))), dict.fromkeys(urls)))

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
        # Each marked piece, with the player it was said to be, numbered as now; not those now there.
        odd, done = {}, settled(log, where)
        for entry in log:
            for o, t in zip(entry.get("odd", []), entry.get("to") or [None] * len(entry.get("odd", []))):
                if piece_key(o) in done:
                    continue
                who = t if t == "not_player" else t and identity.lookup(questions.table, t["track"], t["frame"])
                odd[piece_key(o)] = who if isinstance(who, str) or who is None else f"{who[0]}:{who[1]}"
        conflicts = questions.conflicts(log, identity.read_names(match))
        # Each player's card picture first, then the other best moments for one, as picked by web.photos.
        offered = match / web.PHOTO_CANDIDATES
        photos = {
            who: [{**m, "crop": f"crop?f={m['frame']}&b={','.join(map(str, m['box']))}"} for m in found]
            for who, found in (json.loads(offered.read_text()) if offered.exists() else {}).items()
        }
        data = {"width": width, "height": height, "answered": len(log), **waiting(match, log), "questions": found, "players": players, "roster": names, "odd": odd, "conflicts": conflicts, "photos": photos, "hosted": hosted or None}
        return f"window.REVIEW = {json.dumps(data, separators=(',', ':'))};\n".encode()

    class Handler(BaseHTTPRequestHandler):
        def send(self, body: bytes, kind: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def ours(self) -> bool:
            """Whether a request comes from the review itself: binding 127.0.0.1 keeps other machines
            out, not another site open in the same browser (its requests name another Origin or a
            cross-site Sec-Fetch-Site) nor one rebinding its domain to 127.0.0.1 (another Host)."""
            host = self.headers.get("Host", "")
            return (
                host in (f"127.0.0.1:{port}", f"localhost:{port}")
                and self.headers.get("Origin") in (None, f"http://{host}")
                and self.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")
            )

        def do_GET(self) -> None:
            self.answer(self.get)

        def do_POST(self) -> None:
            self.answer(self.post)

        def answer(self, handle) -> None:
            """`handle`'s response; 400 for a request it cannot read (a field missing or of the wrong type)."""
            try:
                handle()
            except (LookupError, TypeError, ValueError, AttributeError, StopIteration) as error:
                self.send(json.dumps({"error": repr(error)}).encode(), "application/json", 400)

        def get(self) -> None:
            if not self.ours():
                return self.send(b"", "text/plain", 403)
            url = urlparse(self.path)
            if url.path == "/review.js":
                with lock:
                    body = review_js()
                return self.send(body, "text/javascript")
            if url.path == "/progress":
                state = dict(progress)
                if state:
                    state["elapsed"] = time.time() - state.pop("since")
                return self.send(json.dumps(state).encode(), "application/json")
            if url.path == "/more":
                q = parse_qs(url.query)
                team, number = int(q["team"][0]), int(q["identity"][0])
                with lock:
                    log = load_log(answers)
                    questions.avoid = {questions.segment_of(o) for entry in log for o in entry.get("odd", [])}
                    seen = {questions.segment_of(r) for entry in log if entry.get("choice") == "more" for r in entry["pieces"]}
                    found = questions.more(team, number, seen)
                return self.send(json.dumps(found).encode(), "application/json")
            if url.path == "/crop":
                q = parse_qs(url.query)
                body = picture(int(q["f"][0]), tuple(int(v) for v in q["b"][0].split(",")))
                return self.send(body, "image/jpeg") if body else self.send(b"", "text/plain", 404)
            if url.path in ("/", "/review"):
                html = (site / "index.html").read_text()
                if url.path == "/review":
                    html = with_review(html)
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

        def post(self) -> None:
            # A JSON body: a page elsewhere can only send a form or plain text without asking.
            if not self.ours() or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.send(b"", "text/plain", 403)
            size = int(self.headers.get("Content-Length", 0))
            if not 0 <= size <= MAX_BODY:
                return self.send(b'{"error":"body too large"}', "application/json", 413)
            raw = self.rfile.read(size)
            # A report of what is wrong in a moment, from the review's copy of the match page: kept as
            # the hosting's nginx keeps the viewers' (volleyball_stats.feedback reads both).
            if self.path == "/feedback":
                with lock, open(match / FEEDBACK, "a") as f:
                    f.write(json.dumps({"received": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "report": raw.decode()}, ensure_ascii=False) + "\n")
                return self.send(b"", "text/plain", 204)
            body = json.loads(raw or b"{}")
            undone, undo_applied = None, False
            with lock:
                log = load_log(answers)
                before, renamed, names_before = list(log), None, None
                questions.avoid = {questions.segment_of(o) for entry in log for o in entry.get("odd", [])}
                if self.path == "/photo":
                    set_photo(match, questions.table, int(body["team"]), int(body["identity"]), int(body["frame"]), body["box"])
                    run_steps(pages())
                    return self.send(json.dumps(waiting(match, log)).encode(), "application/json")
                if self.path == "/team":
                    set_team(match, int(body["team"]), body.get("name"), body.get("colour"))
                    run_steps(pages())
                    return self.send(json.dumps(waiting(match, log)).encode(), "application/json")
                if self.path == "/name":
                    jersey = body.get("jersey")
                    set_name(match, questions, int(body["team"]), int(body["identity"]), body.get("name"), None if jersey in (None, "") else int(jersey))
                    # Undo leaves the names as typed since.
                    for change in history:
                        change["names"] = None
                    return self.send(json.dumps(waiting(match, log)).encode(), "application/json")
                if self.path == "/answer":
                    _, refs = questions.build({entry["id"] for entry in log})
                    if body["id"] not in refs:
                        return self.send(b'{"error":"unknown question"}', "application/json", 400)
                    choice = str(body["choice"])
                    said = choice.split(":") if choice.startswith("player:") else None
                    player = said and questions.ref(int(said[1]), int(said[2]))
                    if "rally" in refs[body["id"]]:
                        log.append({"id": body["id"], "choice": choice, **rally_answer(refs[body["id"]]["rally"], choice), "applied": False})
                    elif "receiver" in refs[body["id"]]:
                        given = identity.named(questions.table, identity.read_names(match))
                        log.append({"id": body["id"], "choice": choice, **receiver_answer(refs[body["id"]]["receiver"], choice, given), "applied": False})
                    elif "touch" in refs[body["id"]]:
                        given = identity.named(questions.table, identity.read_names(match))
                        log.append({"id": body["id"], "choice": choice, **touch_answer(refs[body["id"]]["touch"], choice, given), "applied": False})
                    else:
                        cut = None
                        if choice == "cut":
                            c = next(c for c in questions.candidates["segments"] if f"piece:{c['track']}:{c['start_frame']}" == body["id"])
                            cut = questions.cut(c["track"], c["start_frame"], c["end_frame"], float(body["at"]))
                            if cut is None:
                                return self.send(b'{"error":"cut at the edge of the piece"}', "application/json", 400)
                        log.append({"id": body["id"], "choice": choice, **constraints(choice, refs[body["id"]], player, cut), "applied": False})
                elif self.path == "/odd":
                    refs = [[{"track": int(r["track"]), "frame": int(r["frame"])} for r in body[k]] for k in ("odd", "rest")]
                    to = [t if t == "not_player" else t and questions.ref(int(t["team"]), int(t["identity"])) for t in body.get("to") or [None] * len(refs[0])]
                    # Pictures left unmarked that an earlier mark moved here stay marked as moved.
                    log = mark_odd(log, *refs, to, frozenset(settled(log, where) & {piece_key(r) for r in refs[1]}))
                    marking = log[-1]["id"] if refs[0] else None
                    # The player's pins on the pictures marked move to their first picture left; then
                    # the earlier answers giving them those pieces let go: the latest judgment wins.
                    if refs[0] and refs[1]:
                        moved = {questions.segment_of(o): refs[1][0] for o in refs[0]}
                        names_before = identity.read_names(match)
                        log, renamed = reanchor(log, names_before, moved, questions.segment_of)
                    if marking and body.get("owner"):
                        owner = (int(body["owner"]["team"]), int(body["owner"]["identity"]))
                        belongs = lambda r: where(r) == owner  # noqa: E731
                        log = supersede(log, refs[0], marking, belongs, questions.segment_of)
                elif self.path == "/more":
                    # Pieces looking like a player: those kept are them, the others someone else.
                    team, number = int(body["team"]), int(body["identity"])
                    yes, no = ([{"track": int(r["track"]), "frame": int(r["frame"])} for r in body[k]] for k in ("yes", "no"))
                    pin = questions.ref(team, number)
                    log.append({
                        "id": f"more:{team}:{number}:{len(log)}", "choice": "more", "pieces": yes + no,
                        **({"same": [[pin, *yes]]} if yes else {}), **({"different": [[r, pin] for r in no]} if no else {}), "applied": False,
                    })
                elif self.path == "/repin":
                    # A question answer said again: its piece is `who`'s, pinned where they are.
                    track, start = (int(v) for v in str(body["id"]).split(":")[1:3])
                    own = questions.segment_of({"track": track, "frame": start})
                    team, number = (int(v) for v in str(body["who"]).split(":"))
                    pin = questions.ref(team, number)
                    log = [
                        {**e, "same": [[r if questions.segment_of(r) == own else pin for r in g] for g in e.get("same", [])], "applied": False} if e["id"] == body["id"] else e
                        for e in log
                    ]
                elif self.path == "/forget":
                    log = [e for e in log if e["id"] != body["id"]]
                elif self.path == "/cut":
                    # A piece answer in a conflict, cut where the person changes, in place of the answer.
                    track, start = (int(v) for v in str(body["id"]).split(":")[1:3])
                    _, a, b = questions.segment_of({"track": track, "frame": start})
                    cut = questions.cut(track, a, b, float(body["at"]))
                    if cut is None:
                        return self.send(b'{"error":"cut at the edge of the piece"}', "application/json", 400)
                    log = [e for e in log if e["id"] != body["id"]]
                    log.append({"id": f"cut:{track}:{cut[0]['frame']}", "choice": "cut", **constraints("cut", {"choices": []}, cut=cut), "applied": False})
                elif self.path == "/undo" and (history or log):
                    log, renamed, undone, undo_applied = undo(log, history)
                # An answer joining two players of different names waits for the user's go.
                if self.path in ("/answer", "/odd", "/more", "/repin") and not body.get("force"):
                    names = identity.read_names(match)
                    new = name_merges(log, renamed or names, questions.segment_of) - name_merges(before, names, questions.segment_of)
                    if new:
                        return self.send(json.dumps({"merges": sorted(sorted(m) for m in new)}).encode(), "application/json", 409)
                if self.path in CHANGES and (log != before or renamed is not None):
                    history.append({"log": before, "names": names_before if renamed is not None else None, "applied": False})
                    del history[:-UNDOS]
                if renamed is not None:
                    write_names(match, renamed)
                save(answers, log)
                # A change not applied yet is only in the log; undoing one an apply followed (`undo`)
                # recomputes, as applying does.
                rebuilt = self.path == "/apply" or undo_applied
                if rebuilt:
                    steps = [("players", lambda: identity.rerun(match, video, squad)), ("questions", questions.load)]
                    if self.path == "/apply":
                        steps.append(("roster", lambda: remember(roster, match.name, identity.named(questions.table, identity.read_names(match)), questions.vectors, team_names())))
                    run_steps(steps + pages())
                    for entry in log:
                        entry["applied"] = True
                    for change in history:
                        change["applied"] = True
                    save(answers, log)
                    files.write_text(computed, json.dumps(state(match, log)))
            self.send(json.dumps({"answered": len(log), **waiting(match, log), "rebuilt": rebuilt, "undone": undone}).encode(), "application/json")

        def log_message(self, *args) -> None:
            pass

    # The footage shows minors: this machine only.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/review"
    threading.Thread(target=warm, daemon=True).start()
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
