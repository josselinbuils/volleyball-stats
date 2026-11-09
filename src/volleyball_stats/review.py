"""Review, on the video, the player identities the identity step is least sure of.

    uv run python -m volleyball_stats.review outputs/matches/VIDEO --video VIDEO --court COURT_JSON [--squad N[,N]] [--theme NAME] [--roster PATH] [--port PORT]

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
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import cv2
import numpy as np

from volleyball_stats import app, attribution, backup, contacts, decode, feedback, film, files, git_check, identity, jerseys, matches, rallies, rename, scoreboard, sync, timeouts, web
from volleyball_stats.court import Calibration
from volleyball_stats.teams import given_end, match_end, parse_colour, seconds

# Frames between two boxes of a question's outline, pictures shown per piece and per identity, and
# frames looked at for the clearest picture of a piece.
BOX_STEP, PIECE_CROPS, IDENTITY_CROPS, CANDIDATES = 2, 3, 8, 12
# A player is alone in a frame where no other box covers ALONE of theirs.
ALONE = 0.05
CROP_PX, CROP_MARGIN = 448, 0.15
READERS = 4
KINDS = ("same", "different", "not_player", "cut", "team", "touch", "rally", "receiver", "action", "winner", "added", "end", "join", "split", "pinned", "locked", "redo", "referee")
# Named players on court during more than TOGETHER of a card's time are not suggested for it: on
# the first ASPOM match, the right name overlapped 0-7%, the others 18-99%.
TOGETHER = 0.15
# Pieces looking most like a player offered to confirm at once, at least MORE_S long and as like
# the card as MORE_LIKE (cosine): on the 6 batches answered over both ASPOM matches, 56 of the 70
# right and 8 of the 70 wrong reach it (4 right and 0 wrong of 48 on a mixed card).
MORE, MORE_S, MORE_LIKE = 24, 1.0, 0.90
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
# the serve when unseen), the whole picture shown: the landing found can be the ball leaving it.
ACE_FLIGHT_S = 1.5
# Touches not doubted asked too, the same ones each time: how many wrong picks the doubts miss.
SPOT_CHECKS = 20
# A rally window asked about is played whole with RALLY_AROUND_S on both sides, unzoomed.
RALLY_AROUND_S = 1.0
ROSTER = Path("outputs/roster.json")
PORT = 8765
# Beside a match's outputs: when its hosted page was last uploaded, and what it then showed (`page_stamp`).
HOSTED = "hosted.json"
# The page data and code the last upload sent (`page_content`): what changed since, when the online page is late.
HOSTED_PAGE = "hosted_page.json"
# What the identities were last computed from (`state`), to tell what an apply would change.
APPLIED = "identity_applied.json"
# Undo takes back the UNDOS latest of the CHANGES whole, then drops the last answer. Request bodies
# are at most MAX_BODY bytes.
UNDOS, MAX_BODY = 100, 1 << 20
# Where the review's copy of the match page keeps the reports of what is wrong in a moment.
FEEDBACK = "feedback.log"
BACKUP_EVERY_S = 600
CHANGES = ("/answer", "/odd", "/more", "/repin", "/forget", "/cut", "/separate")


def with_review(html: str) -> str:
    """The page loading review.js right after data.js (its build hash in the query or not), before
    the app that reads both."""
    return re.sub(r'(<script defer [^>]*src="data\.js[^"]*"></script>)', r'\1<script defer src="review.js"></script>', html, count=1)
# Matches of a player the roster keeps (the latest), and names suggested per identity.
ROSTER_MATCHES, SUGGESTIONS = 5, 3
# Readings of a number from which it is a player's: on the second match, 102-616 for the players' own,
# 44 at most for a number on a player who has another.
CARD_READINGS = 20
# Marks a review page waiting for its players' pictures, for after a restart.
STALE_PHOTOS = "photos_stale"
PICTURE_READINGS = 2

Ref = dict


def mid(start: int, end: int) -> int:
    return (start + end) // 2


class Questions:
    """The review's questions from a match folder's identities, candidates and player tracks."""

    def __init__(self, match: Path, fps: float, pitch: Path | None = None):
        self.match, self.fps = match, fps
        # Where the court is in the picture, for the moments that may be a missed point.
        self.calibration = Calibration.load(pitch) if pitch else None
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
        self.lost, self.double = untaught(self.match, self.table)
        self.candidates = json.loads((self.match / "identity_candidates.json").read_text())
        self.vectors = prototypes(self.match / "embeddings.npz", self.table)
        self.read = card_numbers(self.table, jerseys.load(self.match, rare=True), self.picture_counts())
        actions = web.read_csv(self.match / "actions.csv") if (self.match / "actions.csv").exists() else []
        rallies, _ = web.rally_table(self.match) if (self.match / "rallies.csv").exists() else ([], [])
        lead = round(web.LEAD_S * self.fps)
        windows, actions = web.with_added(
            web.ended([(int(r["start_frame"]), int(r["end_frame"])) for r in rallies], web.answers(self.match, "end")), rallies, actions, web.answers(self.match, "added"), self.match / "ball.csv",
            round(web.ADDED_NEAR_S * self.fps), round(web.ADDED_SAME_S * self.fps), round(web.ADDED_FLOOR_S * self.fps), lead, web.said_teams(self.match), web.said_types(self.match), web.said_players(self.match),
        )
        self.touches = doubtful(actions, [(a - lead, b) for a, b in windows], unnamed(self.match / "review", self.fps))
        # Each rally's window by its key: a rally checked answers the questions about it.
        self.window_of = {int(r["start_frame"]): (a - lead, b) for (a, b), r in zip(windows, rallies)}
        self.page = page_data(self.match / "review")
        texts = scoreboard.load(self.match)
        missed = missed_points(self.page, texts) if self.page else []
        board = board_off(self.page, texts) if self.page else []
        done = set(checked(load_log(self.match / "identity_answers.json")))
        still = board_still(self.page, texts, done) if self.page else []
        over = not_over(self.page, crossings(self.match, self.calibration, self.fps), done) if self.page and self.calibration else []
        self.reports = sorted(reports(self.match) + (unusual(self.page) if self.page else []) + missed + board + still + over, key=lambda r: r.get("time") or 0)
        answers = self.match / "identity_answers.json"
        nothing = {str(a["frame"]) for a in (json.loads(answers.read_text()).get("touch", []) if answers.exists() else []) if a["identity"] is None}
        self.empty = [(w, r.get("set"), int(r["start_frame"])) for w, r in zip(windows, rallies) if all(row["frame"] in nothing for row in touches_in(actions, w))]
        self.aces = aces(self.page)

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

    def page_index(self) -> tuple[dict[int, int], list[tuple[int, int]], list[int]]:
        """The review page's touches' teams by frame, its rally windows (start, end frames) and the
        keys the answers name them by."""
        page = self.page or {"contacts": [], "rallies": []}
        teams = {c.get("f", round(c["t"] * self.fps)): c["team"] for c in page["contacts"] if c["type"] not in web.NO_PLAYER and c.get("team")}
        windows = [(round(r["start"] * self.fps), round(r["end"] * self.fps)) for r in page["rallies"]]
        return teams, windows, [r.get("key", start) for r, (start, _) in zip(page["rallies"], windows)]

    def touch_clip(self, frame: int, x: float | None, y: float | None) -> dict:
        """The clip around a touch at `frame`, its place (the ball then, at `x`, `y`) outlined, if known."""
        half, at = self.touch_side / 2, frame / self.fps
        return {
            "start": round(at - TOUCH_SHOWN_S, 2),
            "end": round(at + TOUCH_SHOWN_S, 2),
            "around": TOUCH_AROUND_S - TOUCH_SHOWN_S,
            "slow": TOUCH_SLOW,
            "boxes": [] if x is None or y is None else [[round(at, 3), round(x - half), round(y - half), round(x + half), round(y + half)]],
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

    def joining(self, log: list[dict], names: list[dict]) -> tuple[dict, dict, dict]:
        """The "same" links between pieces ({piece: [(piece, answer id or None for a name)]}), each
        name's pieces and the names each identity holds."""
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
        return links, pins, held

    def card_pictures(self) -> dict[tuple[int, int], list[tuple[int, tuple[int, ...]]]]:
        """The (frame, box) of the pictures the review shows of each (team, identity): its card's,
        and those offered for its card on the match page."""
        offered = self.match / web.PHOTO_CANDIDATES
        photos = json.loads(offered.read_text()) if offered.exists() else {}
        out = {}
        for team, number in sorted({(r[3], r[4]) for r in self.table if r[4]}):
            shown = re.findall(r"crop\?f=(\d+)&b=([\d,-]+)", json.dumps(self.faces(team, number)["crops"]))
            out[team, number] = [(int(f), tuple(int(v) for v in b.split(","))) for f, b in shown] + [(m["frame"], tuple(m["box"])) for m in photos.get(f"{team}:{number}", [])]
        return out

    def picture_stamp(self) -> str:
        """What the numbers read on pictures depend on: the video, the reader and how pictures are cut."""
        source = self.match / "source.json"
        video = json.loads(source.read_text()).get("video") if source.exists() else None
        return files.cache_stamp(Path(video) if video else None, [Path(jerseys.__file__)], f"{CROP_PX}:{CROP_MARGIN}")

    def picture_counts(self) -> dict[tuple[int, int], Counter]:
        """The numbers read so far on each (team, identity)'s pictures."""
        seen = jerseys.pictures_read(self.match, self.picture_stamp())
        return {card: Counter(n for f, b in dict.fromkeys(found) if (n := seen.get(jerseys.picture_key(f, b))) is not None) for card, found in self.card_pictures().items()}

    def read_pictures(self, image) -> None:
        """Reads the jersey numbers on the review's pictures not read yet, for the cards no track reading gives one."""
        jerseys.read_pictures(self.match, [p for found in self.card_pictures().values() for p in found], image, self.picture_stamp())
        self.read = card_numbers(self.table, jerseys.load(self.match, rare=True), self.picture_counts())

    def past_end(self, until: int) -> dict[tuple[int, int, int], dict]:
        """Each piece from frame `until` on (the end of the match) to the longest piece before it of
        the same player, for their pins to move to: `reanchor`'s `moved`."""
        moved = {}
        for track, start, end, team, number in self.table:
            keep = next((p for p in self.pieces(team, number) if p[2] < until), None) if start >= until and number else None
            if keep:
                moved[track, start, end] = {"track": keep[0], "frame": (keep[1] + keep[2]) // 2}
        return moved

    def to_other_team(self, team: int, number: int) -> dict:
        """The answer giving identity `number`'s pieces the other team."""
        pieces = self.pieces(team, number)
        return {"id": f"team:{pieces[0][0]}:{pieces[0][1]}", "choice": "team", "team": [{"track": t, "frame": (a + b) // 2, "team": 3 - team} for t, a, b, _, _ in pieces], "applied": False}

    def separated(self, log: list[dict], names: list[dict], team: int, number: int) -> list[dict]:
        """`log` without what joins the names of identity `number`: the piece a "more" answer took
        for that player, now said not to be them, and any other answer whole."""
        while True:
            links, pins, held = self.joining(log, names)
            first, *rest = sorted(held[team, number]) or [None]
            steps = path(links, set(pins[first]), {s for n in rest for s in pins[n]})
            edge = next(((a[0], b[0], b[1]) for a, b in zip(steps, steps[1:]) if b[1]), None)
            if edge is None:
                return log
            one, other, answer_id = edge
            entry = next(e for e in log if e["id"] == answer_id)
            if entry.get("choice") != "more":
                log = [e for e in log if e["id"] != answer_id]
                continue
            group_ = next(g for g in entry["same"] if {one, other} <= {self.segment_of(r) for r in g})
            gone = [r for r in group_[1:] if self.segment_of(r) in (one, other)]
            kept = {**entry, "same": [[r for r in g if r not in gone] for g in entry["same"]], "different": entry.get("different", []) + [[group_[0], r] for r in gone]}
            log = [kept if e is entry else e for e in log]

    def conflicts(self, log: list[dict], names: list[dict]) -> list[dict]:
        """The identities of the last run holding two names or more, each with the answers that
        chain the names' pieces through "same" links: most likely a piece showing two people. A
        piece answer comes with its clip and pictures, marked pictures with theirs."""
        links, pins, held = self.joining(log, names)
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
                    others = [r for g in by_id[answer_id].get("same", []) for r in g if not (r["track"] == track and a <= r["frame"] <= b)]
                    claim = self.claim(others[0], named, names) if others else None
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
        ranked = [r for r in ranked if r[0] >= MORE_LIKE]
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
        """Every identity but the `leftovers`, longest on court first, with pictures, seconds of play,
        touches, the name and jersey number given and the roster's players of its team (`teams`'
        names) who look most like it."""
        names = identity.named(self.table, identity.read_names(self.match))
        with open(self.match / "actions.csv") as f:
            touches = Counter((int(r["team"]), int(r["identity"])) for r in csv.DictReader(f) if r.get("identity"))
        seconds: dict[tuple[int, int], float] = {}
        for _, start, end, team, number in self.table:
            if number:
                seconds[team, number] = seconds.get((team, number), 0.0) + (end - start + 1) / self.fps
        out, left = [], leftovers(seconds, names)
        for (team, number), played in sorted(seconds.items(), key=lambda kv: -kv[1]):
            if (team, number) in left:
                continue
            given = names.get((team, number), {})
            out.append({
                "team": team, "identity": number, "seconds": round(played, 1), "contacts": touches[team, number],
                **self.faces(team, number), "name": given.get("name"), "jersey": given.get("jersey"),
                "read": self.read.get((team, number)),
                "suggestions": suggest(self.vectors.get((team, number)), roster, teams[team - 1], self.together(team, number, names), self.read.get((team, number))),
            })
        return out

    def build(self, asked: set[str]) -> tuple[list[dict], dict[str, dict]]:
        """The questions not asked yet, most at stake first, and what each answer means (the refs).
        None that a rally checked answers: who made a touch it shows a named player for, whether it is a rally;
        nor who made a touch already answered elsewhere (the match tab, a rally checked)."""
        out, refs = [], {}
        log = load_log(self.match / "identity_answers.json")
        checked_keys = set(checked(log))
        # A match whose every rally is checked asks only what teaches the next ones: who made a touch,
        # a piece or two players whose answer may change a touch the learned attribution trains on.
        done = reviewed(self.page, log)
        validated = [self.window_of[k] for k in checked_keys if k in self.window_of]
        said = {a["frame"] for a in web.answers(self.match, "touch")}
        for c in self.candidates["segments"]:
            qid = f"piece:{c['track']}:{c['start_frame']}"
            options = [n for n in (c["identity"], c["runner_up"]) if n]
            if qid in asked or not options or c["track"] not in self.rows or c["impact"] < MIN_IMPACT:
                continue
            if done and not teaches(self.lost, self.double, c["team"], c["start_frame"], c["end_frame"], c["runner_up"], c["identity"]):
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
            if qid in asked or c["impact"] < MIN_IMPACT or (done and not joins(self.lost, team, a, b)):
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
            if qid in asked or frame in said or (reason not in ("unknown", "brief") and any(a <= frame <= b for a, b in validated)):
                continue
            touches.append({
                "id": qid, "kind": "touch", "team": team, "identity": None, "impact": identity.CONTACT_S, "seconds": 0, "contacts": 1,
                "action": r["type"], "time": round(frame / self.fps, 2), "clip": self.touch_clip(frame, *((float(r["x"]), float(r["y"])) if r["x"] != "" else (None, None))), "crops": [], "choices": [],
                "reason": reason, "proposed": None if r["identity"] in UNKNOWN else int(r["identity"]),
            })
            refs[qid] = {"touch": {"frame": frame, "team": team}}
        # One question per rally reported, with every report about it; answered reports are not
        # asked again (a question's id joins their keys).
        told, groups = [], {}
        reported = {k for qid in asked if qid.startswith("report:") for k in qid.removeprefix("report:").split("+")}
        for r in self.reports:
            if r["key"] in reported or not self.page:
                continue
            question, ref = report_question(r, self.page, self.fps)
            group = groups.setdefault(r["key"] if ref["start"] is None else ref["start"], [question, [], ref])
            if group[1]:
                group[0]["reports"] += question["reports"]
            group[1].append(r["key"])
        for question, keys, ref in groups.values():
            qid = "report:" + "+".join(keys)
            told.append({"id": qid, **question})
            refs[qid] = {"report": ref}
        missed = []
        for serve, landing, key in self.aces:
            # The team where the ball lands: a window starting late takes a touch for its serve.
            frame = int(serve["frame"])
            team = int(landing["team"]) if landing and landing.get("team") else 3 - int(serve["team"])
            qid = f"receiver:{frame}"
            if qid in asked or done:
                continue
            at = int(landing["frame"]) if landing else frame + round(ACE_FLIGHT_S * self.fps)
            missed.append({
                "id": qid, "kind": "touch", "team": team, "identity": None, "impact": identity.CONTACT_S, "seconds": 0, "contacts": 1,
                "action": "serve", "time": round(frame / self.fps, 2), "reason": "ace", "proposed": None, "crops": [], "choices": [],
                "clip": {"start": round(frame / self.fps, 2), "end": round(at / self.fps, 2), "around": TOUCH_AROUND_S, "slow": TOUCH_SLOW, "boxes": []},
            })
            refs[qid] = {"receiver": {"frame": frame, "team": team}, "start": key}
        found = []
        for (start, end), number, key in self.empty:
            qid = f"rally:{start}"
            if qid in asked or key in checked_keys or done:
                continue
            found.append({
                "id": qid, "kind": "rally", "team": 1, "identity": None, "impact": 0, "seconds": round((end - start) / self.fps, 1), "contacts": 0,
                "set": int(number) if number else None, "time": round(start / self.fps, 2), "crops": [], "choices": [],
                "clip": {"start": round(start / self.fps, 2), "end": round(end / self.fps, 2), "around": RALLY_AROUND_S, "boxes": []},
            })
            refs[qid] = {"rally": {"start": key}}
        return told + found + missed + touches + sorted(out, key=lambda q: -q["impact"]), refs


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


def aces(page: dict | None) -> list[tuple[dict, dict | None, int]]:
    """The aces of the page no touch follows in their rally, those its stats count as missed
    receptions (stats.ts), each with the contact after it (the landing, None when unseen) and its
    rally's key (an ace may be no play at all); a contact as {"frame", "team"}."""
    if page is None:
        return []
    contacts = page["contacts"]
    touches = set(TOUCH_TYPES) - {"fault"}
    place = lambda c: {"frame": c.get("f", round(c["t"] * page["fps"])), "team": c.get("team")}  # noqa: E731
    out = []
    for k, c in enumerate(contacts):
        if c["type"] != "serve" or c["result"] != "point":
            continue
        after = [n for n in contacts[k + 1 :] if n["rally"] == c["rally"]]
        if not any(n["type"] in touches for n in after):
            out.append((place(c), place(after[0]) if after else None, page["rallies"][c["rally"]]["key"]))
    return out


def receiver_answer(ace: dict, choice: str, given: dict[tuple[int, int], dict], start: int | None = None) -> dict:
    """What an answer to an ace's receiver question adds to identity_answers.json: the player of
    "player:TEAM:IDENTITY" missed it, with their team (both teams are offered: one of the serve's own
    means the window took their touch for a serve) and the name `given` them, or no one ("nobody");
    "not_play": its rally (by its `start` key) is no play; nothing for another answer."""
    if choice == "not_play":
        return {} if start is None else rally_answer({"start": start}, choice)
    found = touch_answer(ace, choice, given).get("touch")
    return {"receiver": found} if found else {}


def rally_answer(rally: dict, choice: str) -> dict:
    """What an answer to a rally question adds to identity_answers.json: the window (by its start
    frame) is a rally ("rally") or no play ("not_play"); nothing for another answer."""
    return {"rally": [{**rally, "play": choice == "rally"}]} if choice in ("rally", "not_play") else {}


def pooled_runs(outputs: Path) -> list[dict]:
    """The analysis runs (learn.json) of all the matches in `outputs`, in time order, each scored on
    every match measured so far, at its latest run then: progress since the beginning, a match joining
    it adding its answers rather than starting a new curve."""
    runs = []
    for path in sorted(outputs.glob("*/learn.json")):
        runs += [(run["time"], path.parent.name, run) for run in json.loads(path.read_text())]
    latest: dict[str, dict] = {}
    out = []
    for _, name, run in sorted(runs, key=lambda r: r[:2]):
        latest[name] = run["scores"]
        scores: dict[str, list[int]] = {}
        for found in latest.values():
            for key, (right, total) in found.items():
                sums = scores.setdefault(key, [0, 0])
                sums[0], sums[1] = sums[0] + right, sums[1] + total
        out.append({"time": run["time"], "commit": run["commit"], "match": name, "scores": scores})
    return out


def last_comparison(match: Path) -> dict | None:
    """The scores of `match`'s last run (learn.json) and of the results it replaced, on the same
    answers; None if that run did not measure them."""
    path = match / "learn.json"
    last = json.loads(path.read_text())[-1] if path.exists() else {}
    return {"before": last["before"], "after": last["scores"]} if "before" in last else None


def page_data(site: Path) -> dict | None:
    """The data.js of the page at `site`, None without one."""
    path = site / "data.js"
    if not path.exists():
        return None
    text = path.read_text()
    return json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))


# Touches a report's corrections can give, and their results.
# "fault": a fault made without the ball (net, centre line, rotation), only the review adds it.
TOUCH_TYPES, RESULTS = ("serve", "pass", "set", "attack", "relance", "block", "dig", "fault"), ("play", "point", "error")
# A report outside every rally window is about the one starting up to REPORT_BEFORE_S after it or
# ending up to REPORT_AFTER_S before it (a viewer reports while it plays or just after).
REPORT_BEFORE_S, REPORT_AFTER_S = 3.0, 8.0


def reports(match: Path) -> list[dict]:
    """The viewers' reports about `match` (its folder's name) in the logs fetched beside it
    (outputs/feedback/*.log), each once with its `key`, by time."""
    found: dict[str, dict] = {}
    for log in sorted((files.root(match) / "feedback").glob("*.log")):
        for r in feedback.read(log):
            if r.get("match") in (match.name, *files.aliases(match)):
                # A report sent with its `id` (a one-tap flag, then maybe its details) is one, whichever log holds what.
                said = r["id"] if r.get("id") else [r.get("received"), r.get("time"), r.get("kind"), r.get("comment")]
                key = hashlib.sha256(json.dumps(said).encode()).hexdigest()[:12]
                found[key] = feedback.merge(found[key], r) if key in found else {**r, "key": key}
    return sorted(found.values(), key=lambda r: r.get("time") or 0)


# Over this long between two touches, in seconds, one is often missing (first match, before the review: 10 of 14 hid one).
GAP_S = 2.5
# A team's six players serve in turn: under this many turns apart, it is not the same player's turn.
ROTATION = 6
# A touch scoring has its ball cross the net from this many frames after it to this long after its rally's end.
OVER_FROM, OVER_AFTER_S = 2, 1.0


def rotation_slips(page: dict) -> set[int]:
    """The rallies, by index, served out of their team's order in their set: by a player back under ROTATION
    turns after their last, or by another one while their team kept the serve."""
    rallies = page["rallies"]
    serves: dict[int, dict] = {}
    for c in page["contacts"]:
        if c["type"] == "serve":
            serves.setdefault(c["rally"], c)
    people = page.get("people") or {}
    # A player with two tracking numbers is one by their name.
    who = lambda p: people.get(str(p), {}).get("name") or p  # noqa: E731
    turns: dict[tuple[int, int], list] = defaultdict(list)
    slips = set()
    last = None
    for k, r in enumerate(rallies):
        serve = serves.get(k)
        if not serve or serve.get("person") is None or not serve.get("team"):
            continue
        at, server = (r["set"], serve["team"]), who(serve["person"])
        if last and last[0] == at:
            if last[1] != server:
                slips.add(k)
                turns[at].append(server)
        else:
            if server in turns[at][-(ROTATION - 1) :]:
                slips.add(k)
            turns[at].append(server)
        last = (at, server)
    return slips


def unusual(page: dict) -> list[dict]:
    """The rallies of the review's `page` (its data.js) that do not look like one, as reports at
    their start (no winner and a set's final score: their end), `kind` "auto.REASON": no touch, not starting with a serve, two serves, a reception
    not right after a serve, a serve followed by something else than a reception, a team touching
    four times in a row (a block apart), a player touching twice in a row (after a block aside), a
    touch after a fault or a point (either ends the rally), served by the team that lost the set's point
    before (unless the referee got that point wrong: the serve may follow what really happened), no winner (with teams), a set's last rally ending off the final score given ("scoreOff",
    its id with the score: asked again once it moves), over GAP_S between two touches, a server out of their team's order
    (`rotation_slips`), and, on the first rally either plays, two players of a team with one jersey.
    A playing fault ("fault") is no touch of the ball in the order of touches; one ends the rally as a fault does. The same rally
    and reason keep the same id: one handled is not asked again. `shown` names who it is about."""
    out = []
    rallies = page["rallies"]
    people = page.get("people") or {}
    name = lambda c: people.get(str(c.get("person")), {}).get("name")  # noqa: E731
    slips = rotation_slips(page)
    for k, r in enumerate(rallies):
        touches = [c for c in page["contacts"] if c["rally"] == k and c["type"] not in web.NO_PLAYER]
        # The touches of the ball, playing faults aside.
        played = [c for c in touches if c["type"] != "fault"]
        serves = [c for c in played if c["type"] == "serve"]
        why = []
        if not touches:
            why.append("empty")
        elif played and played[0]["type"] != "serve":
            why.append("noServe")
        if len(serves) > 1:
            why.append("twoServes")
        pairs = list(zip(played, played[1:]))
        if any(b["type"] == "pass" and a["type"] != "serve" for a, b in pairs) or (played and played[0]["type"] == "pass"):
            why.append("passWithoutServe")
        if any(a["type"] == "serve" and b["type"] != "pass" for a, b in pairs):
            why.append("serveNotReceived")
        if any(a.get("person") is not None and a.get("person") == b.get("person") and a["type"] != "block" for a, b in pairs):
            why.append("samePlayer")
        if any(web.labelled(a) == "error" for a in touches[:-1]):
            why.append("afterFault")
        if any(web.labelled(a) == "point" for a in touches[:-1]):
            why.append("afterPoint")
        run, side = 0, None
        for c in played:
            who = c.get("team") or c["side"]
            run, side = (0 if c["type"] == "block" else run + 1 if who == side else 1), who
            if run > 3:
                why.append("fourTouches")
                break
        before = rallies[k - 1] if k else None
        if serves and serves[0].get("team") and before and before["set"] == r["set"] and before.get("winner") and not before.get("wrongCall") and serves[0]["team"] != before["winner"]:
            why.append("server")
        if page.get("teams") and r.get("winner") is None and not r.get("redo"):
            why.append("noWinner")
        given = dict(enumerate(page.get("scores") or [], 1)).get(r["set"])
        score = r.get("score") and f"{r['score'][0]}-{r['score'][1]}"
        if given and score and score != given and (k + 1 == len(rallies) or rallies[k + 1]["set"] != r["set"]):
            why.append("scoreOff")
        if any(b["t"] - a["t"] > GAP_S for a, b in pairs):
            why.append("gap")
        if k in slips:
            why.append("serverOrder")
        for reason in why:
            said = f"auto:{reason}:{r['start']}" + (f":{score}" if reason == "scoreOff" else "")
            about = {"shown": name(serves[0])} if reason == "serverOrder" and name(serves[0]) else {}
            out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": r["end"] if reason in ("noWinner", "scoreOff") else r["start"], "kind": f"auto.{reason}", "comment": None, **about})
    wearing: dict[tuple[int, int], set[int]] = defaultdict(set)
    for p, q in people.items():
        if q.get("jersey") is not None and q.get("name"):
            wearing[(q["team"], q["jersey"])].add(int(p))
    for (team, jersey), persons in wearing.items():
        names = sorted({people[str(p)]["name"] for p in persons})
        first = next((c["rally"] for c in page["contacts"] if c.get("person") in persons), None)
        if len(names) > 1 and first is not None:
            said = f"auto:sameJersey:{team}:{jersey}"
            out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": rallies[first]["start"], "kind": "auto.sameJersey", "comment": None, "shown": f"{jersey} · {', '.join(names)}"})
    return out


def missed_points(page: dict, texts: dict[int, list[str]]) -> list[dict]:
    """Where the score board (`scoreboard.load`'s texts) gains more points than rallies were played since its last reading, as
    reports at the end of the last of those rallies, kind "auto.missedPoint", `shown` the two readings and those rallies' numbers
    when several. A rally to replay gives no point but may explain one. The next reading has to keep that lead (a misread one
    goes) and it has to pass the one before last too (a board flipped late only catches up).
    First match: none; each of its 129 rallies hidden in turn, 26 found (20 readings)."""
    rallies = page["rallies"]
    played = np.cumsum([not r.get("redo") for r in rallies])
    found: dict[int, list] = defaultdict(list)
    for k, (left, a, b, right) in scoreboard.boards(texts, [(r["start"], r["end"], r["set"]) for r in rallies], page["fps"]):
        # Read in the next set, the board counts the set just ended: no score of this one to compare.
        if a + b == rallies[k]["set"] - 1:
            found[rallies[k]["set"]].append((k, left, right))
    out = []
    for number, readings in found.items():
        lead = [left + right - played[k] for k, left, right in readings]
        for i in range(1, len(readings) - 1):
            (j, a, b), (k, c, d) = readings[i - 1], readings[i]
            if max(lead[max(0, i - 2) : i]) < lead[i] <= lead[i + 1] and c + d - a - b > k - j:
                said = f"auto:missedPoint:{number}:{a}-{b}:{c}-{d}"
                span = f" ({j + 2}–{k + 1})" if k - j > 1 else ""
                out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": rallies[k]["end"], "kind": "auto.missedPoint", "comment": None, "shown": f"{a}-{b} → {c}-{d}{span}"})
    return out


def board_off(page: dict, texts: dict[int, list[str]]) -> list[dict]:
    """The rallies after which the running score parts from the score board's (`scoreboard.load`'s
    texts), as reports at their end, kind "auto.boardOff", `shown` the running score after the rally
    ≠ the board's: where the two first differ, or differ otherwise than before, and still do at the
    next reading (a board flipped late differs once). The board's left side is the team it fits best, set by set."""
    rallies = page["rallies"]
    found: dict[int, list] = defaultdict(list)
    for k, (left, a, b, right) in scoreboard.boards(texts, [(r["start"], r["end"], r["set"]) for r in rallies], page["fps"]):
        # Read in the next set, the board counts the set just ended: no score of this one to compare.
        if rallies[k].get("score") and a + b == rallies[k]["set"] - 1:
            found[rallies[k]["set"]].append((k, (left, right), tuple(rallies[k]["score"])))
    out = []
    for number, readings in found.items():
        flip = sum(b == s for _, b, s in readings) < sum(b[::-1] == s for _, b, s in readings)
        boards = [b[::-1] if flip else b for _, b, _ in readings]
        offs = [(s[0] - b[0], s[1] - b[1]) for b, (_, _, s) in zip(boards, readings)]
        last = (0, 0)
        for i, ((k, _, score), board, off) in enumerate(zip(readings, boards, offs)):
            if off != last and i + 1 < len(offs) and offs[i + 1] == off:
                said = f"auto:boardOff:{number}:{board[0]}-{board[1]}"
                out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": rallies[k]["end"], "kind": "auto.boardOff", "comment": None, "shown": f"{score[0]}-{score[1]} ≠ {board[0]}-{board[1]}"})
                last = off
    return out


def board_still(page: dict, texts: dict[int, list[str]], done: set[int] = frozenset()) -> list[dict]:
    """The rallies played between two equal readings of the score board (`scoreboard.load`'s texts), to replay or none, as reports
    at their end, kind "auto.boardStill", `shown` the reading; none on a rally to replay or one of `done` (checked, by key).
    Second match: 6 flags, 6 on a rally corrected; first match: none, its board rarely read."""
    rallies = page["rallies"]
    readings = scoreboard.boards(texts, [(r["start"], r["end"], r["set"]) for r in rallies], page["fps"])
    out = []
    for (j, (left, a, b, right)), (k, after) in zip(readings, readings[1:]):
        r = rallies[k]
        if k == j + 1 and after == (left, a, b, right) and a + b == r["set"] - 1 and not r.get("redo") and r.get("key") not in done:
            said = f"auto:boardStill:{r['set']}:{left}-{right}:{r['start']}"
            out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": r["end"], "kind": "auto.boardStill", "comment": None, "shown": f"{left}-{right}"})
    return out


def crossings(match: Path, calibration: Calibration, fps: float) -> list[int]:
    """Every net crossing of the match's ball track; net.csv holds only those of the rally windows, which may end too early."""
    track = rallies.load_track(match / "ball.csv")
    net_x = float(calibration.to_image(np.array([[0.0, 0.0]]))[0, 0])
    return contacts.detect_crossings(track, net_x, fps, contacts.MARGIN * rallies.court_scale(calibration))


def not_over(page: dict, crossed: list[int], done: set[int] = frozenset()) -> list[dict]:
    """The rallies whose last touch scores (a block apart, at the net) with no net crossing (`crossed`, frames) from it to OVER_AFTER_S
    after the rally's end, as reports on it, kind "auto.notOver"; none on a rally to replay or one of `done` (checked, by key).
    Second match: 17 flags, 16 on a correction; first match: 10, 10."""
    fps = page["fps"]
    at = np.array(crossed, dtype=int)
    last = {c["rally"]: c for c in page["contacts"] if c["type"] not in web.NO_PLAYER and c["type"] != "fault"}
    out = []
    for k, c in last.items():
        r = page["rallies"][k]
        frame = c.get("f", round(c["t"] * fps))
        if web.labelled(c) != "point" or c["type"] == "block" or r.get("redo") or r.get("key") in done:
            continue
        if not np.any((at > frame + OVER_FROM) & (at < round((r["end"] + OVER_AFTER_S) * fps))):
            said = f"auto:notOver:{frame}"
            out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": c["t"], "kind": "auto.notOver", "comment": None})
    return out


def report_question(report: dict, page: dict, fps: float) -> tuple[dict, dict]:
    """A viewer's `report` as a question on the rally of `page` (its data.js) it is about, by the time
    of the touch replayed then (`clip`) or of the report: what was reported (`reports`, more joined
    later by the rally's), the rally's clip, its
    touches (frame, time, type, team, player as "TEAM:IDENTITY", result) and winner; and its ref, the
    rally window's start frame and each touch's team, by frame."""
    at = float((report.get("clip") or {}).get("time") or report.get("time") or 0)
    rallies = page["rallies"]
    # The rally it falls in, else the one it falls near.
    k = next((k for k, r in enumerate(rallies) if r["start"] <= at <= r["end"]), None)
    if k is None:
        k = next((k for k, r in enumerate(rallies) if r["start"] - REPORT_BEFORE_S <= at <= r["end"] + REPORT_AFTER_S), None)
    people = page.get("people") or {}
    player = lambda p: (lambda q: f"{q['team']}:{q['number']}" if q and q.get("number") is not None else None)(people.get(str(p)) if p is not None else None)  # noqa: E731
    touches = [
        {"frame": c.get("f", round(c["t"] * fps)), "time": c["t"], "type": c["type"], "team": c["team"], "player": player(c.get("person")), "result": web.labelled(c)}
        for c in page["contacts"]
        if k is not None and c["rally"] == k and c["type"] not in web.NO_PLAYER
    ]
    rally = rallies[k] if k is not None else {"start": at - 4, "end": at + 4, "set": None, "winner": None}
    question = {
        "kind": "report", "team": 1, "identity": None, "impact": 0, "seconds": round(rally["end"] - rally["start"], 1), "contacts": len(touches),
        "set": rally.get("set"), "time": round(rally["start"], 2), "crops": [], "choices": [],
        "clip": {"start": round(rally["start"], 2), "end": round(rally["end"], 2), "around": RALLY_AROUND_S, "boxes": []},
        "reports": [{"kind": report.get("kind"), "shown": report.get("shown"), "comment": report.get("comment") or "", "time": round(at, 2), "received": report.get("received")}],
        "touches": touches, "winner": rally.get("winner"),
    }
    key = rally.get("key", round(rally["start"] * fps)) if k is not None else None
    return {**question, "rally": key}, {"start": key, "touches": {str(t["frame"]): t["team"] for t in touches}}


def report_answer(changes: dict, teams: dict[int, int], windows: list[tuple[int, int]], given: dict[tuple[int, int], dict], lead: int, keys: list[int] | None = None) -> dict:
    """What the corrections made in the review add to identity_answers.json, anywhere in the match
    (the page's touches' `teams` by frame, its rally `windows` and the `keys` naming them, their
    starts by default): a touch's player ("TEAM:IDENTITY") or none ("none", no touch) as `touch`
    answers, its type or result as `action` ones; a touch added (frame, team, type, result, player)
    as an `added` one with those, in its rally (`window_of`); a rally's (`rallies`, by its key) no
    play (`rally`), winner (`winner`), end frame (`end`), joining the next one (`join`) or being
    replayed, or no longer (`redo`), the referee giving the point to the wrong team, or no longer
    (`referee`: the true winner is the other team than the rally's); a rally
    starting at a frame (`splits`, `split`), its key that frame: one the pipeline missed, or the
    second of two it took for one."""
    keys = keys or [start for start, _ in windows]
    out: dict[str, list] = defaultdict(list)
    splits = sorted({int(f) for f in changes.get("splits", [])})
    if splits:
        out["split"] = [{"frame": f} for f in splits]
    pieces = web.split_at(windows, splits)
    keys = [keys[origin] if origin is not None and start == windows[origin][0] else start for start, _, origin in pieces]
    # A rally starts at a serve added before it: the touches added after that serve are its own.
    windows = [(start, end) for start, end, _ in pieces]
    for c in changes.get("added", []):
        if c.get("type") == "serve" and (k := window_of(int(c["frame"]), windows, lead, True)) is not None:
            windows[k] = (min(windows[k][0], int(c["frame"])), windows[k][1])
    for c in changes.get("added", []):
        frame, team = int(c["frame"]), int(c["team"])
        k = window_of(frame, windows, lead, c.get("type") == "serve")
        if k is None or team not in (1, 2) or c.get("type") not in TOUCH_TYPES or frame in teams:
            continue
        out["added"].append({"start": keys[k], "frame": frame, "team": team, "type": c["type"]})
        if c.get("result") in RESULTS:
            out["action"].append({"frame": frame, "result": c["result"]})
        if c.get("player"):
            t, i = (int(v) for v in str(c["player"]).split(":"))
            out["touch"] += touch_answer({"frame": frame, "team": t}, f"player:{t}:{i}", given)["touch"]
    for c in changes.get("touches", []):
        # A page without its touches' frames gives them from their time, a frame off at times.
        frame = next((f for f in (int(c["frame"]), int(c["frame"]) - 1, int(c["frame"]) + 1) if f in teams), int(c["frame"]))
        team = teams.get(frame)
        if team is None:
            continue
        if c.get("player") == "none":
            out["touch"] += touch_answer({"frame": frame, "team": team}, "nobody", given)["touch"]
        elif c.get("player"):
            t, i = (int(v) for v in str(c["player"]).split(":"))
            out["touch"] += touch_answer({"frame": frame, "team": t}, f"player:{t}:{i}", given)["touch"]
        fix = {k: c[k] for k, allowed in (("type", TOUCH_TYPES), ("result", RESULTS)) if c.get(k) in allowed}
        if fix:
            out["action"].append({"frame": frame, **fix})
    starts = set(keys)
    for r in changes.get("rallies", []):
        start = int(r["start"])
        if start not in starts:
            continue
        if r.get("play") is False:
            out["rally"].append({"start": start, "play": False})
        if r.get("winner") in (1, 2):
            out["winner"].append({"start": start, "winner": r["winner"]})
        # After where the rally starts, which an added serve puts before its key.
        if r.get("end") is not None and int(r["end"]) > windows[keys.index(start)][0]:
            out["end"].append({"start": start, "end": int(r["end"])})
        if r.get("join") is True:
            out["join"].append({"start": start})
        if r.get("redo") in (True, False):
            out["redo"].append({"start": start, "redo": r["redo"]})
        if r.get("wrong") in (True, False):
            out["referee"].append({"start": start, "wrong": r["wrong"]})
    return dict(out)


def window_of(frame: int, windows: list[tuple[int, int]], lead: int, serve: bool = False) -> int | None:
    """The index of the window a touch at `frame` belongs to: the one it falls in (from `lead`
    frames before it); else a `serve` the next one's (the rally missed it), another touch the last
    one started before it; before them all, the first. None without windows."""
    inside = next((k for k, (start, end) in enumerate(windows) if start - lead <= frame <= end), None)
    if inside is not None:
        return inside
    after = next((k for k, (start, _) in enumerate(windows) if start > frame), None)
    before = [k for k, (start, _) in enumerate(windows) if start <= frame]
    if serve and after is not None:
        return after
    return before[-1] if before else after


def unnamed(site: Path, fps: float) -> dict[int, str]:
    """The touches the page at `site` credits to no named player of their team, by frame: "brief"
    when its player was on the court only seconds in the set (web.brief), else "unknown". Asking them
    all leaves the page no unidentified player."""
    data = page_data(site)
    if data is None:
        return {}
    people = data.get("people") or {}
    out = {}
    for c in data["contacts"]:
        p = people.get(str(c["person"])) if c.get("person") is not None else None
        if c["type"] not in web.NO_PLAYER and c.get("team") and not (p and p["number"] is not None and p["team"] == c["team"]):
            out[c.get("f", round(c["t"] * fps))] = "brief" if c.get("brief") else "unknown"
    return out


def doubtful(actions: list[dict], windows: list[tuple[int, int]], unnamed: dict[int, str] | None = None) -> list[tuple[dict, str]]:
    """The touches of actions.csv's rows (frame order) to ask who made, with why, most at stake
    first: no player of the touch's team known for it ("unknown"), or none named on the page
    (`unnamed`, by frame, with its reason); one player touching twice in a
    row in a rally, blocks aside ("twice", the less sure touch of the two); SPOT_CHECKS of the others
    picked at random, the same each run ("check"); another player about as near the ball
    (attribution.DOUBT, "close", the nearest first)."""
    touch = lambda r: r["type"] not in web.NO_PLAYER and bool(r.get("team"))  # noqa: E731
    gap = lambda r: float(r["gap"]) if r.get("gap") else float("inf")  # noqa: E731
    rally = lambda r: next((k for k, (a, b) in enumerate(windows) if a <= int(r["frame"]) <= b), None)  # noqa: E731
    found = {r["frame"]: (r, "unknown") for r in actions if touch(r) and r.get("identity") in UNKNOWN}
    for r in actions:
        if touch(r) and int(r["frame"]) in (unnamed or {}):
            found.setdefault(r["frame"], (r, unnamed[int(r["frame"])]))
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
    of "player:TEAM:IDENTITY", of either team (the touch's team is often wrong; the page moves it to
    theirs), with the name `given` them, which outlives the identities' numbers;
    no touch at all for "nobody" (identity None), nor for "not_play", outside the play (also
    `play` false: where the rallies step went wrong); nothing for another answer."""
    if choice in ("nobody", "not_play"):
        return {"touch": [{**touch, "identity": None, "name": None, **({"play": False} if choice == "not_play" else {})}]}
    if not choice.startswith("player:"):
        return {}
    player = tuple(int(v) for v in choice.split(":")[1:3])
    return {"touch": [{**touch, "team": player[0], "identity": player[1], "name": (given.get(player) or {}).get("name")}]}


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


def let_go(log: list[dict], piece: Ref, segment_of) -> list[dict]:
    """`log` without what its answers said of `piece`, about to be answered again: the latest judgment
    wins, and two answers on one piece never join two players. Its marks go, the answers joining it
    to a player let go of it; the rest of each answer stays."""
    own = segment_of(piece)
    out = []
    for entry in log:
        if entry.get("choice") == "odd" and any(segment_of(o) == own for o in entry["odd"]):
            kept = [(o, t) for o, t in zip(entry["odd"], entry.get("to") or [None] * len(entry["odd"])) if segment_of(o) != own]
            if not kept:
                continue
            # Answers saved before "rest" was kept hold it in their pairs.
            others = entry.get("rest") or list({piece_key(r): r for _, r in entry["different"]}.values())
            entry = {**odd_entry(entry["id"], [o for o, _ in kept], others, [t for _, t in kept]), **({"applied": entry["applied"]} if "applied" in entry else {})}
        out.append(entry)
    return supersede(out, [piece], "", lambda _: True, segment_of)


def piece_conflict(log: list[dict], entry: dict, piece: Ref, names: list[dict], segment_of) -> tuple[list[dict], list[str]]:
    """`log` without what it says of `piece` (`let_go`), and the names `entry`, an answer about it,
    would join because of that: none if it joins nobody, or still would without those answers (a
    name is given on the piece itself: a real merge)."""
    freed = let_go(log, piece, segment_of)
    known = name_merges(log, names, segment_of)
    joined = name_merges([*log, entry], names, segment_of) - known
    if not joined or name_merges([*freed, entry], names, segment_of) - known:
        return freed, []
    return freed, sorted({name for group in joined for name in group})


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


def card_numbers(table: list[tuple[int, int, int, int, int]], read: dict[tuple[int, int], int] | None, pictures: dict[tuple[int, int], Counter] | None = None) -> dict[tuple[int, int], int]:
    """The jersey number read on each (team, identity): each number of a team on the identity with
    most of its readings, CARD_READINGS or more, and on no other; one reading of several numbers
    takes its most read. A card left without takes the number its `pictures` read most, on more than
    the others together and PICTURE_READINGS or more, if its team's other cards don't wear it."""
    by_track: dict[int, list] = {}
    for r in table:
        by_track.setdefault(r[0], []).append(r)
    counts: Counter = Counter()
    for (frame, track), number in (read or {}).items():
        card = next(((team, n) for _, start, end, team, n in by_track.get(track, []) if start <= frame <= end and n), None)
        if card:
            counts[card, number] += 1
    out: dict[tuple[int, int], int] = {}
    taken: set[tuple[int, int]] = set()
    for (card, number), count in counts.most_common():
        if count >= CARD_READINGS and card not in out and (card[0], number) not in taken:
            out[card] = number
            taken.add((card[0], number))
    for card, found in sorted((pictures or {}).items(), key=lambda c: -max(c[1].values(), default=0)):
        (number, count), *_ = found.most_common(1) or [(None, 0)]
        if card not in out and count >= PICTURE_READINGS and count > found.total() - count and (card[0], number) not in taken:
            out[card] = number
            taken.add((card[0], number))
    return out


def suggest(vector: np.ndarray | None, roster: list[dict], team: str | None, unless: set[str] = frozenset(), number: int | None = None) -> list[dict]:
    """The names and jersey numbers of the roster's players of `team` (every player for an unnamed
    team) who look most like `vector`, best first, but those in `unless`; those wearing the `number`
    read on the player come before them."""
    if vector is None:
        return []
    scored = []
    for player in roster:
        if team and player.get("team") and player["team"] != team or player["name"] in unless:
            continue
        mean = np.mean(list(player["vectors"].values()), axis=0)
        scored.append((float(mean @ vector) / max(float(np.linalg.norm(mean)), 1e-9), player))
    return [{"name": p["name"], "jersey": p.get("jersey")} for _, p in sorted(scored, key=lambda sp: (number is None or sp[1].get("jersey") != number, -sp[0]))[:SUGGESTIONS]]


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


def follow_teams(path: Path, outputs: Path) -> None:
    """The roster with each player's vector of a match under the name that match's teams.json now
    gives their team, however it changed (the review, a rename, by hand), joined to the player of
    that name it may hold there. A name given in both teams of a match says neither: it stays."""
    roster = load_roster(path)
    by_key = {(p.get("team"), p["name"].casefold()): p for p in roster}
    changed = False
    for name in sorted({m for p in roster for m in p["vectors"]}):
        folder = outputs / name
        if not (folder / "teams.json").exists() or not (folder / "identities.csv").exists():
            continue
        teams = [t.get("name") for t in json.loads((folder / "teams.json").read_text())["teams"]]
        sides: dict[str, set[int]] = {}
        for (team, _), given in identity.named(identity.read_identities(folder / "identities.csv"), identity.read_names(folder)).items():
            if given.get("name"):
                sides.setdefault(given["name"].strip().casefold(), set()).add(team)
        for player in list(roster):
            found = sides.get(player["name"].casefold(), set())
            if name not in player["vectors"] or len(found) != 1:
                continue
            team = teams[next(iter(found)) - 1]
            if team == player.get("team"):
                continue
            moved = by_key.get((team, player["name"].casefold()))
            if moved is None:
                moved = by_key[team, player["name"].casefold()] = {**player, "team": team, "vectors": {}}
                roster.append(moved)
            moved["vectors"][name] = player["vectors"].pop(name)
            changed = True
    if changed:
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
    `box`, by the player's name (it outlives the identities' numbers), else by their card."""
    who = (identity.named(table, identity.read_names(match)).get((team, number)) or {}).get("name")
    path = match / web.PHOTO_PICKED
    taken = json.loads(path.read_text()) if path.exists() else {}
    taken[who or f"{team}:{number}"] = {"frame": int(frame), "box": [int(v) for v in box]}
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


def set_end(match: Path, time: str | None) -> None:
    """teams.json with the end of the match at `time` (m:ss or h:mm:ss), none for None or empty.
    ValueError for anything else."""
    path = match / "teams.json"
    data = json.loads(path.read_text())
    text = (time or "").strip()
    if text:
        seconds(text)
        data["end"] = text
    else:
        data.pop("end", None)
    files.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_names(match: Path, entries: list[dict]) -> None:
    files.write_text(match / identity.NAMES, json.dumps({"players": entries}, indent=1, ensure_ascii=False) + "\n")


def load_log(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("log", []) if path.exists() else []


def state(match: Path, log: list[dict]) -> dict:
    """What the identities are computed from: the answers' constraints, the names and the date of
    the jersey numbers (to the second), as JSON gives them back; with the timeouts given, which
    the page shows."""
    read = match / jerseys.FILE
    # The winners pinned change no identity nor the page.
    found = {"answers": {kind: [x for e in log for x in e.get(kind, [])] for kind in KINDS if kind not in ("pinned", "locked")}, **({"end": match_end(match)} if match_end(match) is not None else {}), "names": identity.read_names(match), "jerseys": int(read.stat().st_mtime) if read.exists() else None, "timeouts": timeouts.read_answers(match)}
    # No "team" answer leaves the state of earlier applies as it was.
    if not found["answers"]["team"]:
        del found["answers"]["team"]
    return json.loads(json.dumps(found))


def waiting_reports(log: list[dict], shown: set[str] | frozenset[str]) -> list[dict]:
    """The report answers saved since the review's page was built (`shown`: the ids of the answers
    it was built with), with the corrections they were sent."""
    return [e for e in log if e.get("choice") == "report" and "changes" in e and e["id"] not in shown]


def superseded(log: list[dict], shown: set[str] | frozenset[str]) -> list[dict]:
    """`log` with the report answers saved since the review's page was built emptied of their
    corrections: the next one carries them all, as the page shows them (`corrections`). New entries,
    so that an undo gets the earlier ones back."""
    later = {id(e) for e in waiting_reports(log, shown)}
    return [{k: v for k, v in e.items() if k not in KINDS and k != "changes"} if id(e) in later else e for e in log]


def corrections(log: list[dict], shown: set[str] | frozenset[str]) -> dict:
    """The corrections of the report answers saved since the review's page was built (it shows the
    earlier ones), as the page sent them: the last one's, which carries the others."""
    return next((e["changes"] for e in reversed(waiting_reports(log, shown))), {})


# The owner's notes on the rallies, by key: outside the answers (no undo or apply touches them), and
# only review.js reads them, so no page holds them.
COMMENTS = "rally_comments.json"


def read_comments(match: Path) -> dict[int, str]:
    path = match / COMMENTS
    return {int(k): v for k, v in json.loads(path.read_text()).items()} if path.exists() else {}


def write_comments(match: Path, comments: dict[int, str]) -> None:
    files.write_text(match / COMMENTS, json.dumps({str(k): v for k, v in sorted(comments.items())}, ensure_ascii=False, indent=1) + "\n")


def commented(comments: dict[int, str], page: dict | None, log: list[dict]) -> dict[int, str]:
    """`comments` by the rallies `page` shows or a split not applied yet starts: one on a rally no
    longer there (joined to the one before, its split undone) goes to the rally holding its start;
    one in no rally (said no play) stays under its key, hidden."""
    rallies = (page or {}).get("rallies", [])
    known = {r.get("key") for r in rallies} | {a["frame"] for e in log for a in e.get("split", [])}
    out = {k: v for k, v in comments.items() if k in known}
    for key in sorted(set(comments) - known):
        holder = next((r["key"] for r in rallies if r["start"] * page["fps"] <= key <= r["end"] * page["fps"]), key)
        out[holder] = f"{out[holder]}\n{comments[key]}" if holder in out else comments[key]
    return out


def pinned(page: dict | None, keys: list[int]) -> list[dict]:
    """An answer pinning the winners `page` shows for the rallies checked (`keys`): they stay
    whatever the rallies around them become (`web.served_next`); a winner the review gives still
    wins. None without one to pin. The page shows them already: applied."""
    found = [{"start": r["key"], "winner": r["winner"]} for r in (page or {"rallies": []})["rallies"] if r.get("key") in set(keys) and r.get("winner")]
    return [{"id": "pin", "choice": "pinned", "pinned": found, "applied": True}] if found else []


def locked(page: dict | None, keys: list[int], given: dict[tuple[int, int], dict]) -> list[dict]:
    """An answer locking the rallies checked (`keys`) as `page` shows them: each touch's named
    player (`touch`), action and result (`action`), and the touches themselves (`locked`: the page
    keeps those, re-adds one a rerun loses and lets in no other but those the review adds). None
    without one to lock. The page shows them already: applied."""
    out: dict[str, list] = defaultdict(list)
    people = (page or {}).get("people") or {}
    for k, r in enumerate((page or {"rallies": []})["rallies"]):
        if r.get("key") not in set(keys):
            continue
        mine = []
        for c in page["contacts"]:
            if c["rally"] != k or c["type"] in web.NO_PLAYER or not c.get("team"):
                continue
            frame = c.get("f", round(c["t"] * page["fps"]))
            mine.append({"frame": frame, "team": c["team"], "type": c["type"]})
            out["action"].append({"frame": frame, "type": c["type"], "result": web.labelled(c)})
            # Keyed by text once read from data.js.
            p = people.get(str(c["person"]), people.get(c["person"])) if c.get("person") is not None else None
            if p and p.get("number") is not None and p["team"] == c["team"]:
                out["touch"] += touch_answer({"frame": frame, "team": c["team"]}, f"player:{p['team']}:{p['number']}", given)["touch"]
        out["locked"].append({"start": r["key"], "touches": mine})
    return [{"id": "lock", "choice": "locked", **out, "applied": True}] if out else []


def unlocked(keys: list[int]) -> list[dict]:
    """An answer unlocking the rallies unchecked (`keys`): their touches stay as answered."""
    return [{"id": "unlock", "choice": "unlocked", "locked": [{"start": k, "touches": None} for k in keys], "applied": True}] if keys else []


# Each step's and pipeline stage's duration in seconds before one is measured: the first ASPOM
# match, 4K, on the M4 (1 Nov).
TOOK = {
    "reports": 3.0, "training": 270.0, "pipeline": 2400.0, "players": 25.0, "questions": 3.0, "roster": 1.0, "review": 15.0, "page": 10.0, "hosting": 60.0, "hostingAll": 120.0, "copies": 3300.0, "films": 2400.0, "film": 180.0, "highlights": 300.0,
    "pipeline:tracking": 7200.0, "pipeline:rallies": 25.0, "pipeline:actions": 640.0, "pipeline:wrists": 790.0, "pipeline:teams": 880.0, "pipeline:jerseys": 2400.0, "pipeline:scoreboard": 360.0,
    "pipeline:identity": 20.0, "pipeline:jumps": 420.0, "pipeline:answers": 60.0,
}
# The pipeline's stages in order (match.stage): "tracking" only when the trackers run again.
STAGES = ("tracking", "rallies", "actions", "wrists", "teams", "jerseys", "scoreboard", "identity", "jumps", "answers")
TIMINGS = "review_timings.json"


def eta(progress: dict, took: dict[str, float], now: float) -> dict:
    """Where a run of steps (`progress`: their names, the one running since when, its stage since
    when) stands at `now`, from each one's last duration (`took`): the step and its stage, the time
    spent and left, and whether the stage or step running already takes longer than it did."""
    steps, done, stage = progress["steps"], progress["done"], progress.get("stage")
    step = steps[done]
    if stage:
        later = [s for s in STAGES[STAGES.index(stage) + 1 :] if s != "tracking"] if stage in STAGES else []
        spent, expected = now - progress["stage_since"], took.get(f"{step}:{stage}", 0.0)
        here = max(0.0, expected - spent) + sum(took.get(f"{step}:{s}", 0.0) for s in later)
    else:
        spent, expected = now - progress["since"], took.get(step, 1.0)
        here = max(0.0, expected - spent)
    left = here + sum(took.get(s, 1.0) for s in steps[done + 1 :])
    return {"steps": steps, "done": done, "stage": stage, "elapsed": now - progress["started"], "left": left, "late": 0 < expected < spent}


def checked(log: list[dict]) -> list[int]:
    """The rallies the user checked and did not uncheck since, by their key: they show green while
    no report is open on them."""
    out: set[int] = set()
    for e in log:
        out = (out | set(e.get("checked", []))) - set(e.get("unchecked", []))
    return sorted(out)


# An unnamed identity on court under this share of its team's median time.
LEFTOVER = 0.1


def leftovers(seconds: dict[tuple[int, int], float], names: dict[tuple[int, int], dict]) -> set[tuple[int, int]]:
    """The unnamed identities on court under LEFTOVER of their team's median time (`seconds`): what
    the tracking could not join to anyone, bits of several players that no name holds together.
    ponytail: a substitute playing under a tenth of the usual time goes too; tell them apart (one
    face, long pieces) if one goes missing."""
    teams = {team for team, _ in seconds}
    typical = {team: float(np.median([v for (t, _), v in seconds.items() if t == team])) for team in teams}
    return {k for k, v in seconds.items() if not (names.get(k) or {}).get("name") and v < LEFTOVER * typical[k[0]]}


def untaught(match: Path, table: list) -> tuple[dict[int, tuple[tuple[int, int], set[tuple[int, int]]]], dict[int, tuple[int, int]]]:
    """The answered touches the learned attribution trains on (ranker.py: the toucher by name, else
    identity) that the identities spoil, by frame: those no track of the toucher is at, with who is
    there, and those two are at, with the toucher."""
    given = identity.named(table, identity.read_names(match))
    by_name = {(team, g["name"]): n for (team, n), g in given.items() if g.get("name")}
    rows = np.array([r[1:5] for r in table], dtype=np.int64).reshape(-1, 4)
    lost, double = {}, {}
    for a in {a["frame"]: a for a in web.answers(match, "touch")}.values():
        if a["identity"] is None:
            continue
        f, who = a["frame"], (a["team"], by_name.get((a["team"], a.get("name")), a["identity"]))
        here = rows[(rows[:, 0] <= f) & (f <= rows[:, 1])]
        there = {(int(t), int(n)) for t, n in here[:, 2:]}
        count = int(((here[:, 2] == who[0]) & (here[:, 3] == who[1])).sum())
        if not count:
            lost[f] = (who, there)
        elif count > 1:
            double[f] = who
    return lost, double


def teaches(lost: dict, double: dict, team: int, start: int, end: int, gains: int | None, loses: int | None) -> bool:
    """Whether a piece of `team` from `start` to `end` going to identity `gains` (from `loses`) may
    mend a touch `untaught` found: one whose toucher is `gains` and no track, or `loses` and two."""
    return any(start <= f <= end and who == (team, gains) for f, (who, _) in lost.items()) or any(start <= f <= end and who == (team, loses) for f, who in double.items())


def joins(lost: dict, team: int, a: int, b: int) -> bool:
    """Whether identities `a` and `b` of `team` said one player may mend a touch `untaught` found:
    one's touch with no track of theirs where the other is."""
    return any(who == (team, x) and (team, y) in there for who, there in lost.values() for x, y in ((a, b), (b, a)))


def reviewed(page: dict | None, log: list[dict]) -> bool:
    """Whether every rally of the review's `page` is checked."""
    keys = {r["key"] for r in (page or {}).get("rallies", [])}
    return bool(keys) and keys <= set(checked(log))


def waiting(match: Path, log: list[dict], shown: set[str] | frozenset[str] = frozenset()) -> dict:
    """What an apply would take in: the answers saying something not applied yet (those saved
    before the flag were), whether the answers or the jersey numbers, and the names, differ from
    what the identities were computed from (APPLIED); the reports' `corrections` the review's
    page does not show yet (`shown`: the answers it was built with), the rallies `checked`, the
    `films` to make, players' and highlights, and whether the last learning run saw these answers."""
    computed = match / APPLIED
    now, then = state(match, log), json.loads(computed.read_text()) if computed.exists() else {}
    return {
        "pending": sum(not e.get("applied", True) and any(e.get(kind) for kind in KINDS) for e in log),
        # The jersey numbers' time to the second: a copy through the server (`sync`) keeps no less.
        "changed": (now["answers"], now["jerseys"], now["timeouts"]) != (then.get("answers"), None if then.get("jerseys") is None else int(then["jerseys"]), then.get("timeouts", [])),
        "namesPending": now["names"] != then.get("names"),
        "corrections": corrections(log, shown),
        "checked": checked(log),
        "films": film.status(match),
        "learned": learned(match, log),
    }


def answers_stamp(log: list[dict]) -> str:
    """What the answers say, applied or not: kept with each learning run (learn.json)."""
    said = [{k: v for k, v in e.items() if k != "applied"} for e in log]
    return hashlib.sha256(json.dumps(said, sort_keys=True).encode()).hexdigest()[:16]


def learned(match: Path, log: list[dict]) -> bool:
    """Whether the match's last learning run (learn.json) saw the answers as they stand."""
    path = match / "learn.json"
    runs = json.loads(path.read_text()) if path.exists() else []
    return bool(runs) and runs[-1].get("answers") == answers_stamp(log)


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


def page_stamp(match: Path) -> str:
    """What the hosted page would show: the review's page data, as content (its keys in any order), and the page's code. Not
    the data's `v`, its address for the browser's cache, which each patch of the pictures moves (`web.patch_people`): a
    restart rebuilding the same page then patching it gave another, and the online page looked late."""
    digest = hashlib.sha256(json.dumps(page_content(match)["data"], sort_keys=True, ensure_ascii=False).encode())
    for path in (matches.TEMPLATE / "matches.html", web.TEMPLATE / "index.html"):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def page_content(match: Path) -> dict:
    """The review's page data without its `v` (`page_stamp`), and its code's stamp."""
    data = page_data(match / "review") or {}
    data.pop("v", None)
    code = hashlib.sha256(b"".join(path.read_bytes() for path in (matches.TEMPLATE / "matches.html", web.TEMPLATE / "index.html"))).hexdigest()[:16]
    return {"data": data, "code": code}


def page_changes(sent: dict, now: dict) -> list[dict]:
    """What changed from the page content `sent` to `now` (`page_content`): each part of the data that differs, with how many of
    its items changed, added or went (a list's, a mapping's), then "code" when the page's code did."""
    out = []
    old, new = sent["data"], now["data"]
    for part in sorted(set(old) | set(new)):
        a, b = old.get(part), new.get(part)
        if a == b:
            continue
        if isinstance(a, list) and isinstance(b, list):
            texts = lambda items: Counter(json.dumps(x, sort_keys=True) for x in items)  # noqa: E731
            gone, came = texts(a) - texts(b), texts(b) - texts(a)
            count = max(sum(gone.values()), sum(came.values()))
        elif isinstance(a, dict) and isinstance(b, dict):
            count = sum(a.get(k) != b.get(k) for k in set(a) | set(b))
        else:
            count = None
        out.append({"part": part, "count": count})
    if sent["code"] != now["code"]:
        out.append({"part": "code", "count": None})
    return out


def hosted_state(saved: dict | None, stamp: str, today: date) -> dict:
    """Where the hosted page stands from `saved`, the last upload's HOSTED: behind unless it carried this `stamp`; `day` when
    it was not `today`."""
    if not saved:
        return {"at": None, "day": None, "error": None, "behind": True}
    at = datetime.fromisoformat(saved["at"])
    return {"at": at.strftime("%H:%M"), "day": None if at.date() == today else at.date().isoformat(), "error": None, "behind": saved["stamp"] != stamp}


def read_hosted(match: Path) -> dict:
    """`hosted_state`, with what changed since the last upload when the page is late and it kept what it sent (`changes`)."""
    path, sent = match / HOSTED, match / HOSTED_PAGE
    state = hosted_state(json.loads(path.read_text()) if path.exists() else None, page_stamp(match), date.today())
    state["changes"] = page_changes(json.loads(sent.read_text()), page_content(match)) if state["behind"] and sent.exists() else None
    return state


def record_hosted(match: Path) -> None:
    """The upload of `match`'s page just made: its time and stamp (HOSTED), and what it sent (HOSTED_PAGE)."""
    files.write_text(match / HOSTED_PAGE, json.dumps(page_content(match), ensure_ascii=False) + "\n")
    files.write_text(match / HOSTED, json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "stamp": page_stamp(match)}) + "\n")


def match_list(out: Path) -> list[dict]:
    """The matches of `out` that have a SOURCE, newest first, as the hosted list shows them, by their folder's name; `ready` once
    their pipeline has ended and their files are there."""
    found = []
    for source in out.glob(f"*/{files.SOURCE}"):
        folder, given = source.parent, json.loads(source.read_text())
        if (folder / "review" / "data.js").exists():
            item = matches.listed(folder / "review")
        else:
            saved = json.loads((folder / "teams.json").read_text()) if (folder / "teams.json").exists() else {}
            scores = saved.get("scores") or []
            item = {"name": folder.name, "date": saved.get("date"), "title": saved.get("title"), "teams": saved.get("teams"), "scores": scores, "sets": sum(map(bool, scores)), "rallies": 0}
        item["path"] = folder.name
        item["ready"] = all(p.exists() for p in (folder / "report.md", Path(given["video"]), Path(given["court"])))
        if not Path(given["video"]).exists():
            item["missing"] = "video"
        found.append(item)
    return sorted(found, key=lambda m: (m["date"] or "", m["path"]), reverse=True)


def on_server(out: Path, listed: list[dict]) -> list[dict]:
    """The matches with a copy on the server and none here, to download; none when the server cannot be reached."""
    try:
        found = sync.listing(out.parent)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return []
    here = {m["path"] for m in listed}
    dated = lambda name: name[:10] if re.match(r"\d{4}-\d{2}-\d{2}", name) else None  # noqa: E731
    return [{"name": n, "path": n, "date": dated(n), "title": None, "teams": None, "scores": [], "sets": 0, "rallies": 0, "ready": False, "remote": True} for n in sorted(found) if n not in here]


def list_page(path: str, out: Path, theme: str) -> tuple[bytes, str] | None:
    """The response to `path` under /matches/, the hosted list's page for the matches of `out`; None when there is no such file."""
    site = out / ".review_matches"
    if path == "/matches/":
        shutil.rmtree(site, ignore_errors=True)
        shutil.copytree(matches.TEMPLATE, site)
        club = matches.brand(theme, site)
        if club:
            club.pop("sponsors")
        # The server's matches come after (`/matches/remote.json`): reaching it takes a second, or ssh's timeout.
        listed = match_list(out)
        (site / "matches.js").write_text(f"window.MATCHES = {json.dumps({'matches': listed, 'brand': club, 'review': True}, ensure_ascii=False)};\n")
        return (site / "matches.html").read_bytes(), "text/html; charset=utf-8"
    if path == "/matches/remote.json":
        found = on_server(out, match_list(out)) if sync.active(out.parent) else []
        return json.dumps(found, ensure_ascii=False).encode(), "application/json"
    parts = Path(unquote(path).removeprefix("/matches/")).parts
    file = site.joinpath(*parts)
    # The season reads each match's data.
    if len(parts) == 2 and parts[1] == "data.js" and (out / parts[0] / files.SOURCE).exists():
        file = out / parts[0] / "review" / "data.js"
    if ".." in parts or not file.is_file():
        return None
    kinds = {".js": "text/javascript", ".css": "text/css", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml"}
    return file.read_bytes(), kinds.get(file.suffix.lower(), "application/octet-stream")


def reopening(name: str, out: Path, theme: str, port: int, roster: Path) -> list[str]:
    """The command opening the review on the match `name`, one of `match_list`'s ready ones; LookupError otherwise."""
    if not any(m["path"] == name and m["ready"] for m in match_list(out)):
        raise LookupError(name)
    return [sys.executable, "-m", "volleyball_stats.review", str(out / name), "--outputs", str(out), "--theme", theme, "--port", str(port), "--roster", str(roster), "--no-browser"]


class Server(ThreadingHTTPServer):
    """The review's server, quiet when a page goes before its answer (a reload, a closed tab)."""

    def handle_error(self, request, client_address) -> None:
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


def switch(command: list[str], lock: threading.Lock) -> None:
    """Replaces this server by `command`, once the response on its way has left and no answer is being saved."""

    def replace() -> None:
        time.sleep(0.2)
        lock.acquire()
        os.execv(command[0], command)

    threading.Thread(target=replace, daemon=True).start()


def pulled(body, out: Path) -> tuple[bytes, str, int]:
    """The response to the list's /pull: the match `name` brought from the server."""
    try:
        sync.pull(str(body["name"]), out.parent)
    except (LookupError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        return json.dumps({"error": str(error) or type(error).__name__}).encode(), "application/json", 400
    return b"{}", "application/json", 200


def same_site(headers, port: int) -> bool:
    """Whether a request comes from this server's own pages."""
    host = headers.get("Host", "")
    return (
        host in (f"127.0.0.1:{port}", f"localhost:{port}")
        and headers.get("Origin") in (None, f"http://{host}")
        and headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")
    )


def serve_list(out: Path, theme: str, port: int, browser: bool, roster: Path) -> None:
    """Only the list of the matches, until one is opened."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_) -> None:
            pass

        def send(self, body: bytes, kind: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if not same_site(self.headers, port):
                return self.send(b"", "text/plain", 403)
            if url.path == "/current":
                return self.send(b'{"name":null}', "application/json")
            if url.path == "/git":
                return self.send(json.dumps(git_check.behind(git_check.ROOT)).encode(), "application/json")
            if url.path in ("/", "/review"):
                self.send_response(302)
                self.send_header("Location", "/matches/")
                self.end_headers()
                return
            page = list_page(url.path, out, theme) if url.path.startswith("/matches/") else app.handle("GET", url.path, url.query, {}, lambda: match_list(out))
            self.send(*(page or (b"Not found", "text/plain", 404)))

        def do_POST(self) -> None:
            known = self.path in ("/open", "/pull") or self.path.startswith("/app/")
            if not same_site(self.headers, port) or not known or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.send(b"", "text/plain", 403)
            size = int(self.headers.get("Content-Length", 0))
            if not 0 <= size <= MAX_BODY:
                return self.send(b'{"error":"body too large"}', "application/json", 413)
            try:
                body = json.loads(self.rfile.read(size) or b"{}")
            except ValueError:
                return self.send(b'{"error":"not json"}', "application/json", 400)
            if self.path.startswith("/app/"):
                answer = app.handle("POST", self.path, "", body, lambda: match_list(out)) or (b"Not found", "text/plain", 404)
                self.send(*answer)
                if self.path == "/app/update" and answer[2] == 200:
                    app.restart_after()
                return None
            if self.path == "/pull":
                return self.send(*pulled(body, out))
            try:
                command = reopening(body["name"], out, theme, port, roster)
            except (LookupError, TypeError, ValueError):
                return self.send(b'{"error":"no such match"}', "application/json", 400)
            self.send(b"{}", "application/json")
            switch(command, threading.Lock())

    server = Server(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/matches/"
    print(f"Review: {url} (Ctrl+C to stop)", flush=True)
    if browser:
        app.open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def serve(match: Path, video: Path, court: Path, squad, theme: str, port: int, browser: bool = True, roster: Path = ROSTER) -> None:
    # First the server's newer copy, if nothing changed here (`sync.check`); changed on both sides, the page asks which to keep.
    conflict = sync.check(match) if sync.active(files.root(match)) else None
    matches.ensure_publish(match, video, theme)
    site = match / "review"
    # Open at once: the pictures follow (`afterwards`), minutes if their scores are out of date.
    web.review_page(match, video, court, theme, pictures=False)
    (match / STALE_PHOTOS).touch()
    cap = cv2.VideoCapture(str(video))
    fps, width, height = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    answers = match / "identity_answers.json"
    # The answers the review's page was last built with: it shows their corrections.
    shown = {e["id"] for e in load_log(answers)}
    if not (match / "identity_candidates.json").exists():
        identity.rerun(match, video, squad)
    questions = Questions(match, fps, court)
    # The rallies checked before the winners were pinned: those their page shows. First in the log:
    # an undo after a restart takes away the last answer.
    log = load_log(answers)
    have = {p["start"] for e in log for p in e.get("pinned", [])}
    first = pinned(questions.page, [k for k in checked(log) if k not in have])
    if first:
        save(answers, first + log)
        print(f"{len(first[0]['pinned'])} winners of rallies checked pinned", flush=True)
        log = first + log
    have = {p["start"] for e in log for p in e.get("locked", [])}
    lock = locked(questions.page, [k for k in checked(log) if k not in have], identity.named(questions.table, identity.read_names(match)))
    if lock:
        save(answers, lock + log)
        print(f"{len(lock[0]['locked'])} rallies checked locked", flush=True)
    where = lambda r: identity.lookup(questions.table, r["track"], r["frame"])  # noqa: E731
    computed = match / APPLIED
    done = match / "identities.csv"
    if not computed.exists() and done.exists() and all(not f.exists() or f.stat().st_mtime < done.stat().st_mtime for f in (answers, match / identity.NAMES)):
        files.write_text(computed, json.dumps(state(match, load_log(answers))))
    # The answers and names before each change since the server started, for undo (see `undo`).
    history: list[dict] = []
    lock = threading.Lock()
    later = threading.Event()
    generation = [0]
    stale_photos = match / STALE_PHOTOS
    # Pictures are cut from the video by READERS at once, then kept on disk: a 4K seek costs 0.4 s.
    readers = threading.Semaphore(READERS)
    kept = match / "crops"

    def picture(frame: int, box: tuple[int, int, int, int]) -> bytes:
        path = kept / f"{CROP_PX}_{frame}_{'_'.join(map(str, box))}.jpg"
        if path.exists():
            return path.read_bytes()
        with readers:
            image = decode.frame_at(video, frame)
        if image is None:
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

    # Where an apply stands, for the page's progress bar: the steps, the one running since when and
    # its stage (the pipeline's). Each step's and stage's last duration ("STEP:STAGE"), kept per match
    # (TIMINGS) to outlive a restart, first guessed from the first ASPOM match.
    progress: dict = {}
    # The last run's failure until the user dismisses it: `step` and `error`.
    failure: dict = {}
    took = {**TOOK, **(json.loads((match / TIMINGS).read_text()) if (match / TIMINGS).exists() else {})}
    # The last hosting (publish.json): when, why it failed, and whether the page has changed since; the
    # page says it. The user puts the pages online ("/host"), an apply does not.
    hosted: dict = read_hosted(match)
    filmed: dict = {"error": None}
    # The last fetch of the viewers' reports from the hosting: when, and how many for this match.
    fetched_log: dict = {}
    # The last copy on the hosting server: when, why it failed.
    backed: dict = {"at": None, "error": None}
    outputs = files.root(match)
    publish = json.loads((match / matches.PUBLISH).read_text()) if (match / matches.PUBLISH).exists() else {}
    can_back_up = bool(publish.get("upload") and publish.get("key"))
    # The match changed both here and on another machine since this one's copy (`sync.check`, a push refused): the page
    # asks which to keep.
    elsewhere: dict = dict(conflict or {})

    backup_lock = threading.Lock()
    # The files' signature at the last copy made, and the timer woken when automatic copies are switched on.
    copied: list = [None]
    wake = threading.Event()

    def backup_state() -> dict | None:
        """What the page shows of the copies on the server; None without one."""
        return {**backed, "auto": sync.auto(outputs)} if can_back_up else None

    def back_up() -> bool:
        """A copy on the hosting server now, its time or failure for the page; whether it was made. One at a time: the page
        can ask for one while the timer makes another."""
        with backup_lock:
            try:
                now = backup.signature(backup.sources(match))
                sync.push(match)
                copied[0] = now
                backed.update(at=time.strftime("%H:%M"), error=None)
                return True
            except sync.Conflict as error:
                elsewhere.update(error.claim)
                backed.update(at=time.strftime("%H:%M"), error=str(error))
                return False
            except (OSError, RuntimeError, ValueError, LookupError, subprocess.SubprocessError) as error:
                backed.update(at=time.strftime("%H:%M"), error=str(error) or type(error).__name__)
                print(f"backup failed: {backed['error']}", flush=True)
                return False

    def backing() -> None:
        """A copy whenever something changed, while this machine wants them."""
        while True:
            if sync.auto(outputs):
                try:
                    now = backup.signature(backup.sources(match))
                except OSError:
                    # A file gone while it was read: the next round reads them again.
                    now = None
                if now is not None and now != copied[0]:
                    back_up()
            wake.wait(BACKUP_EVERY_S)
            wake.clear()


    def hosting(every: bool = False) -> None:
        """This match put online, or with `every` all the matches online, rebuilt then uploaded at once."""
        try:
            target = ["--all", str(match.parent)] if every else ["--host", str(match), "--video", str(video), "--court", str(court)]
            done = [m for m, *_ in matches.online(match.parent)] if every else [match]
            # Those newer on the server are left as they are online (`matches.main`).
            newer = sync.behind(done)
            done = [m for m in done if m.name not in newer]
            # In its own process, with the code as it now is, whenever this server started.
            run = subprocess.run([sys.executable, "-m", "volleyball_stats.matches", *target, "--theme", theme], capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError((run.stderr.strip().splitlines() or [f"exit {run.returncode}"])[-1])
            for m in done:
                if (m / "review" / "data.js").exists():
                    record_hosted(m)
            hosted.update(read_hosted(match))
        except Exception as error:  # noqa: BLE001
            # The answers stay applied: only the hosted page is behind.
            hosted.update(at=time.strftime("%H:%M"), day=None, error=str(error) or type(error).__name__)

    def filming(kind: str, names: list[str] | None = None) -> None:
        try:
            film.build(match, video, court, staged, names, kind)
            filmed["error"] = None
        except Exception as error:  # noqa: BLE001
            # The films made are kept: the next press makes those left.
            filmed["error"] = str(error) or type(error).__name__

    def pages(pictures: bool = True) -> list:
        """The steps rebuilding the review's page, its pictures later (`afterwards`) unless `pictures`,
        and the published one with its own choices."""
        def own() -> None:
            web.review_page(match, video, court, theme, pictures)
            generation[0] += 1
            if pictures:
                stale_photos.unlink(missing_ok=True)
            else:
                stale_photos.touch()
            shown.clear()
            shown.update(e["id"] for e in load_log(answers))
            hosted.update({k: v for k, v in read_hosted(match).items() if k in ("behind", "changes")})

        steps = [("review", own)]
        if (match / "page.json").exists():
            steps.append(("page", lambda: web.publish(match, video, court, theme, {})))
        return steps

    def afterwards() -> None:
        """What an apply leaves for later, one run at a time, once more when asked during one: the
        players' pictures, kept on the page if no build came since, then the numbers they read."""
        while True:
            later.wait()
            later.clear()
            try:
                built = generation[0]
                if stale_photos.exists():
                    people = web.refresh_photos(match, video, match / "review")
                    with lock:
                        if built == generation[0]:
                            web.patch_people(match / "review", people)
                            stale_photos.unlink(missing_ok=True)
                            hosted.update({k: v for k, v in read_hosted(match).items() if k in ("behind", "changes")})
                questions.read_pictures(picture)
            except Exception:
                traceback.print_exc()

    def run_steps(steps: list) -> None:
        progress.update(steps=[name for name, _ in steps], started=time.time())
        failure.clear()
        try:
            for k, (name, work) in enumerate(steps):
                progress.update(done=k, since=time.time(), stage=None)
                try:
                    work()
                except Exception as error:
                    failure.update(step=name, error=repr(error))
                    raise
                staged(None)
                took[name] = time.time() - progress["since"]
                files.write_text(match / TIMINGS, json.dumps(took, indent=1) + "\n")
        finally:
            progress.clear()

    def staged(name: str | None) -> None:
        """The running step's stage `name` starts (None: the step ends): the last one's time is kept."""
        now, step = time.time(), progress["steps"][progress["done"]]
        if progress.get("stage"):
            took[f"{step}:{progress['stage']}"] = now - progress["stage_since"]
        progress.update(stage=name, stage_since=now)

    def warm() -> None:
        """Cuts the review's pictures ahead of the user, READERS at a time."""
        found, _ = questions.build(set())
        urls = re.findall(r"crop\?f=(\d+)&b=([\d,-]+)", json.dumps([found, questions.players([], team_names())]))
        with ThreadPoolExecutor(READERS) as pool:
            list(pool.map(lambda u: picture(int(u[0]), tuple(int(v) for v in u[1].split(","))), dict.fromkeys(urls)))
        later.set()

    def team_names() -> list[str | None]:
        teams = web.read_teams(match)
        return [t["name"] for t in teams["teams"]] if teams else [None, None]

    def review_js() -> bytes:
        log = load_log(answers)
        found, _ = questions.build({entry["id"] for entry in log})
        follow_teams(roster, match.parent)
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
        data = {"width": width, "height": height, "matchEnd": given_end(match), "answered": len(log), **waiting(match, log, shown), "comments": commented(read_comments(match), questions.page, log), "picks": sorted(film.read_picks(match)), "timeouts": timeouts.shown(match, questions.fps), "questions": found, "players": players, "roster": names, "odd": odd, "conflicts": conflicts, "photos": photos, "hosted": {**hosted, "chosen": "video" in json.loads((match / matches.PUBLISH).read_text())} if (match / matches.PUBLISH).exists() else None,
            "learning": pooled_runs(match.parent),
            "comparison": last_comparison(match),
            "fetched": fetched_log or None,
            "backup": backup_state(),
            "filmsError": filmed["error"],
        }
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
            return same_site(self.headers, port)

        def do_GET(self) -> None:
            self.answer(self.get)

        def do_POST(self) -> None:
            self.answer(self.post)

        def answer(self, handle) -> None:
            """`handle`'s response; 400 for a request it cannot read (a field missing or of the wrong type)."""
            try:
                handle()
            except (LookupError, TypeError, ValueError, AttributeError, StopIteration) as error:
                traceback.print_exc()
                self.send(json.dumps({"error": repr(error)}).encode(), "application/json", 400)

        def get(self) -> None:
            if not self.ours():
                return self.send(b"", "text/plain", 403)
            url = urlparse(self.path)
            if url.path == "/current":
                return self.send(json.dumps({"name": match.name}).encode(), "application/json")
            found = app.handle("GET", url.path, url.query, {}, lambda: match_list(match.parent))
            if found:
                return self.send(*found)
            if url.path == "/matches.json":
                return self.send(json.dumps(match_list(match.parent)).encode(), "application/json")
            if url.path.startswith("/matches/"):
                page = list_page(url.path, match.parent, theme)
                return self.send(*page) if page else self.send(b"Not found", "text/plain", 404)
            if url.path == "/review.js":
                with lock:
                    body = review_js()
                return self.send(body, "text/javascript")
            if url.path == "/progress":
                state = dict(progress)
                return self.send(json.dumps(eta(state, took, time.time()) if state else {}).encode(), "application/json")
            if url.path == "/failure":
                return self.send(json.dumps(failure).encode(), "application/json")
            if url.path == "/sync":
                return self.send(json.dumps(elsewhere or None).encode(), "application/json")
            if url.path == "/git":
                return self.send(json.dumps(git_check.behind(git_check.ROOT)).encode(), "application/json")
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
            # An apply rewrites the page's data under the same names.
            if path.suffix.lower() == ".js":
                self.send_header("Cache-Control", "no-cache")
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
            if self.path.startswith("/app/"):
                answer = app.handle("POST", self.path, "", body, lambda: match_list(match.parent), lambda: bool(progress)) or (b"Not found", "text/plain", 404)
                self.send(*answer)
                if self.path == "/app/update" and answer[2] == 200:
                    app.restart_after(lock)
                return None
            if self.path == "/failure":
                failure.clear()
                return self.send(b"{}", "application/json")
            if self.path == "/backup":
                if not can_back_up:
                    return self.send(b'{"error":"no server"}', "application/json", 400)
                back_up()
                return self.send(json.dumps(backup_state()).encode(), "application/json")
            if self.path == "/autoBackup":
                if not can_back_up or not isinstance(body.get("on"), bool):
                    return self.send(b'{"error":"no server"}', "application/json", 400)
                sync.set_auto(outputs, body["on"])
                wake.set()
                return self.send(json.dumps(backup_state()).encode(), "application/json")
            if self.path == "/pull":
                return self.send(*pulled(body, match.parent))
            if self.path == "/sync/take":
                # The server's copy kept, this machine's set aside.
                if progress:
                    return self.send(b'{"error":"busy"}', "application/json", 409)
                with lock, backup_lock:
                    try:
                        sync.take(match)
                    except (LookupError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                        return self.send(json.dumps({"error": str(error) or type(error).__name__}).encode(), "application/json", 502)
                self.send(b"{}", "application/json")
                # Everything read from the match's files again.
                switch([sys.executable, "-m", "volleyball_stats.review", *[a for a in sys.argv[1:] if a != "--no-browser"], "--no-browser"], lock)
                return None
            if self.path == "/sync/keep":
                # This machine's copy kept, the server's set aside there.
                if progress:
                    return self.send(b'{"error":"busy"}', "application/json", 409)
                with lock, backup_lock:
                    try:
                        sync.keep(match)
                    except (LookupError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                        return self.send(json.dumps({"error": str(error) or type(error).__name__}).encode(), "application/json", 502)
                elsewhere.clear()
                backed.update(at=time.strftime("%H:%M"), error=None)
                return self.send(b"{}", "application/json")
            if self.path == "/open":
                if progress:
                    return self.send(b'{"error":"busy"}', "application/json", 409)
                command = reopening(body["name"], match.parent, theme, port, roster)
                self.send(b"{}", "application/json")
                if body["name"] != match.name:
                    switch(command, lock)
                return None
            undone, undo_applied = None, False
            with lock:
                log = load_log(answers)
                before, renamed, names_before = list(log), None, None
                questions.avoid = {questions.segment_of(o) for entry in log for o in entry.get("odd", [])}
                if self.path == "/photo":
                    set_photo(match, questions.table, int(body["team"]), int(body["identity"]), int(body["frame"]), body["box"])
                    run_steps(pages())
                    return self.send(json.dumps(waiting(match, log, shown)).encode(), "application/json")
                if self.path == "/end":
                    set_end(match, body.get("time"))
                    end = match_end(match)
                    if end is not None:
                        log, moved_names = reanchor(log, identity.read_names(match), questions.past_end(round(end * questions.fps)), questions.segment_of)
                        write_names(match, moved_names)
                        save(answers, log)
                    for change in history:
                        change["names"] = None
                    return self.send(json.dumps(waiting(match, log, shown)).encode(), "application/json")
                if self.path == "/team":
                    set_team(match, int(body["team"]), body.get("name"), body.get("colour"))
                    # Its name follows its teams, the folders and the video with it: the server restarts on them.
                    new = rename.target_name(match)
                    if new and new != match.name and not progress and not (match.parent / new).exists():
                        # In its own process, with the code as it now is, whenever this server started.
                        run = subprocess.run([sys.executable, "-m", "volleyball_stats.rename", str(match), new, "--from-review"], capture_output=True, text=True)
                        if run.returncode:
                            raise ValueError(run.stderr.strip())
                        self.send(json.dumps({"renamed": new}).encode(), "application/json")
                        switch(reopening(new, match.parent, theme, port, roster), threading.Lock())
                        return None
                    run_steps(pages(pictures=False))
                    later.set()
                    return self.send(json.dumps(waiting(match, log, shown)).encode(), "application/json")
                if self.path == "/name":
                    jersey = body.get("jersey")
                    set_name(match, questions, int(body["team"]), int(body["identity"]), body.get("name"), None if jersey in (None, "") else int(jersey))
                    # Undo leaves the names as typed since.
                    for change in history:
                        change["names"] = None
                    # A player of the other team: the card goes there, undone like an answer.
                    if body.get("moved"):
                        entry = questions.to_other_team(int(body["team"]), int(body["identity"]))
                        history.append({"log": before, "names": None, "applied": False})
                        del history[:-UNDOS]
                        log = [*(e for e in log if e["id"] != entry["id"]), entry]
                        save(answers, log)
                    return self.send(json.dumps(waiting(match, log, shown)).encode(), "application/json")
                if self.path == "/comment":
                    comments = commented(read_comments(match), questions.page, log)
                    key, text = int(body["rally"]), str(body["text"]).strip()
                    if text:
                        comments[key] = text
                    else:
                        comments.pop(key, None)
                    write_comments(match, comments)
                    return self.send(b"{}", "application/json")
                if self.path == "/pick":
                    picks, frame = film.read_picks(match), int(body["frame"])
                    film.write_picks(match, picks | {frame} if body["picked"] else picks - {frame})
                    return self.send(b"{}", "application/json")
                if self.path == "/timeout":
                    # The page shows them: an apply takes them in.
                    return self.send(json.dumps({"timeouts": timeouts.answer(match, questions.fps, body), **waiting(match, log, shown)}).encode(), "application/json")
                if self.path == "/answer":
                    _, refs = questions.build({entry["id"] for entry in log})
                    # Corrections saved from the match tab, about no question.
                    edit = str(body["id"]).startswith("edit:")
                    if body["id"] not in refs and not edit:
                        return self.send(b'{"error":"unknown question"}', "application/json", 400)
                    choice = "report" if edit else str(body["choice"])
                    said = choice.split(":") if choice.startswith("player:") else None
                    player = said and questions.ref(int(said[1]), int(said[2]))
                    if edit or "report" in refs[body["id"]]:
                        given = identity.named(questions.table, identity.read_names(match))
                        # An edit sent without corrections only checks or unchecks rallies: the corrections stay.
                        sent = choice == "report" and "changes" in body
                        changes = body.get("changes") or {}
                        teams, windows, keys = questions.page_index()
                        fixes = report_answer(changes, teams, windows, given, round(web.LEAD_S * questions.fps), keys) if sent else {}
                        if sent:
                            log[:] = superseded(log, shown)
                        ok = [int(k) for k in body.get("checked") or []] if edit else []
                        off = [int(k) for k in body.get("unchecked") or []] if edit else []
                        asked = {entry["id"] for entry in log}
                        # Before the answer: an undo after a restart takes that one away.
                        log += pinned(questions.page, ok) + locked(questions.page, ok, given) + unlocked(off)
                        log.append({"id": body["id"], "choice": choice, **fixes, **({"changes": changes} if sent else {}), **({"checked": ok} if ok else {}), **({"unchecked": off} if off else {}), "applied": False})
                        # The reports on a rally checked are handled with it.
                        log += [{"id": qid, "choice": "checked", "applied": False} for qid, ref in refs.items() if "report" in ref and ref["report"]["start"] in ok and qid not in asked]
                    elif "rally" in refs[body["id"]]:
                        log.append({"id": body["id"], "choice": choice, **rally_answer(refs[body["id"]]["rally"], choice), "applied": False})
                    elif "receiver" in refs[body["id"]]:
                        given = identity.named(questions.table, identity.read_names(match))
                        log.append({"id": body["id"], "choice": choice, **receiver_answer(refs[body["id"]]["receiver"], choice, given, refs[body["id"]].get("start")), "applied": False})
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
                        entry = {"id": body["id"], "choice": choice, **constraints(choice, refs[body["id"]], player, cut), "applied": False}
                        # Said to be a player when earlier answers say another: the user settles it.
                        if player or choice.isdigit():
                            names = identity.read_names(match)
                            freed, earlier = piece_conflict(log, entry, refs[body["id"]]["piece"], names, questions.segment_of)
                            if earlier and not body.get("replace") and not body.get("force"):
                                return self.send(json.dumps({"conflict": earlier}).encode(), "application/json", 409)
                            if earlier and body.get("replace"):
                                log = freed
                        log.append(entry)
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
                elif self.path == "/separate":
                    log = questions.separated(log, identity.read_names(match), body["team"], body["identity"])
                elif self.path == "/cut":
                    # A piece answer in a conflict, cut where the person changes, in place of the answer.
                    track, start = (int(v) for v in str(body["id"]).split(":")[1:3])
                    _, a, b = questions.segment_of({"track": track, "frame": start})
                    cut = questions.cut(track, a, b, float(body["at"]))
                    if cut is None:
                        return self.send(b'{"error":"cut at the edge of the piece"}', "application/json", 400)
                    log = [e for e in log if e["id"] != body["id"]]
                    log.append({"id": f"cut:{track}:{cut[0]['frame']}", "choice": "cut", **constraints("cut", {"choices": []}, cut=cut), "applied": False})
                elif self.path == "/reports" and (match / matches.PUBLISH).exists():
                    config = json.loads((match / matches.PUBLISH).read_text())

                    def fetched() -> None:
                        try:
                            got = feedback.fetch(files.root(match) / "feedback", config["upload"], config["key"])
                            fetched_log.update(at=time.strftime("%H:%M"), count=len([r for r in feedback.read(got) if r.get("match") in (match.name, *files.aliases(match))]) if got else 0, error=None)
                        except Exception as error:  # noqa: BLE001
                            fetched_log.update(at=time.strftime("%H:%M"), count=0, error=str(error) or type(error).__name__)

                    run_steps([("reports", fetched), ("questions", questions.load)])
                    return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": False, "undone": None, "fetched": fetched_log}).encode(), "application/json")
                elif self.path == "/host" and (match / matches.PUBLISH).exists():
                    config = json.loads((match / matches.PUBLISH).read_text())
                    if "video" not in config:
                        config = matches.choose(match, bool(body["video"]), body.get("password"))
                    # Hours of encoding only for a match that goes online with its video.
                    copies = [("copies", lambda: matches.add_copies(match, video))] if config["video"] and matches.copies_missing(config) else []
                    run_steps([*copies, ("hosting", hosting)])
                    return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": False, "undone": None}).encode(), "application/json")
                elif self.path == "/hostAll" and (match / matches.PUBLISH).exists():
                    run_steps([("hostingAll", lambda: hosting(every=True))])
                    return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": False, "undone": None}).encode(), "application/json")
                elif self.path in ("/films", "/film", "/highlights"):
                    # The page then shows them, the hosted one on its next upload; "/film" makes the player `name`'s alone.
                    names = [str(body["name"])] if self.path == "/film" else None
                    step, kind = ("highlights", "highlights") if self.path == "/highlights" else (self.path[1:], "players")
                    run_steps([(step, lambda: filming(kind, names)), *pages()])
                    return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": False, "undone": None}).encode(), "application/json")
                elif self.path == "/rerun":
                    from volleyball_stats import learn

                    # A match whose every rally is checked only teaches the next ones: it stays as reviewed.
                    if reviewed(questions.page, log):
                        run_steps([("training", lambda: learn.retrain(match, video, court))])
                        return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": False, "undone": None}).encode(), "application/json")
                    # The pipeline again, its identities with every answer: an apply too. Undo
                    # stops here: the answers moved onto the new rallies.
                    own, *published = pages()
                    run_steps([("training", lambda: learn.train(match, video, court)), ("pipeline", lambda: learn.rerun(match, video, court, staged)), own, ("questions", questions.load), *published])
                    history.clear()
                    log = load_log(answers)
                    for entry in log:
                        entry["applied"] = True
                    save(answers, log)
                    files.write_text(computed, json.dumps(state(match, log)))
                    return self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": True, "undone": None}).encode(), "application/json")
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
                    # The review's own page first: the questions ask what it leaves unidentified.
                    own, *published = pages(pictures=False)
                    steps = [("players", lambda: identity.rerun(match, video, squad)), own, ("questions", questions.load)]
                    if self.path == "/apply":
                        steps.append(("roster", lambda: remember(roster, match.name, identity.named(questions.table, identity.read_names(match)), questions.vectors, team_names())))
                    run_steps(steps + published)
                    later.set()
                    for entry in log:
                        entry["applied"] = True
                    for change in history:
                        change["applied"] = True
                    save(answers, log)
                    files.write_text(computed, json.dumps(state(match, log)))
            self.send(json.dumps({"answered": len(log), **waiting(match, log, shown), "rebuilt": rebuilt, "undone": undone}).encode(), "application/json")

        def log_message(self, *args) -> None:
            pass

    # The footage shows real people: this machine only.
    server = Server(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/review"
    threading.Thread(target=warm, daemon=True).start()
    threading.Thread(target=afterwards, daemon=True).start()
    if can_back_up:
        threading.Thread(target=backing, daemon=True).start()
    print(f"Review: {url} (Ctrl+C to stop)", flush=True)
    if browser:
        app.open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Review the doubtful player identities on the video, in the browser.")
    parser.add_argument("match", type=Path, nargs="?", help="The match's outputs directory (outputs/matches/VIDEO), run with --players. Default: the list of the matches")
    parser.add_argument("--outputs", type=Path, default=Path("outputs/matches"), help="Where the list of the matches looks")
    parser.add_argument("--video", type=Path, help="Default: the match's source.json")
    parser.add_argument("--court", type=Path, help="Court calibration JSON the match was run with. Default: the match's source.json")
    parser.add_argument("--squad", type=identity.parse_squad, help="Players per team, N or N1,N2")
    parser.add_argument("--theme", default="aspom", help="Club theme of the match page (web.py)")
    parser.add_argument("--roster", type=Path, default=ROSTER, help=f"The club's named players across matches (default: {ROSTER})")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the page in the browser")
    args = parser.parse_args()
    if args.match is None:
        return serve_list(args.outputs, args.theme, args.port, not args.no_browser, args.roster)
    source = args.match / files.SOURCE
    given = json.loads(source.read_text()) if source.exists() else {}
    video, court = args.video or given.get("video"), args.court or given.get("court")
    if not video or not court:
        parser.error(f"--video and --court: {source} does not say them")
    squad = args.squad or (identity.parse_squad(given["squad"]) if given.get("squad") else None)
    files.write_source(args.match, video, court, squad)
    serve(args.match, Path(video), Path(court), squad, args.theme, args.port, not args.no_browser, args.roster)


if __name__ == "__main__":
    main()
