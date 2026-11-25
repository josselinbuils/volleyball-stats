"""The review's questions (the answers and names are review_answers.py, the server review_server.py): `Questions`, the
player identities the identity step is least sure of (identity_candidates.json), each piece outlined on the video beside
pictures of the identities it could be; then the touches, aces, rallies, viewers' reports, scoreboard moments and odd
values worth asking about.
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from volleyball_stats import attribution, contacts, feedback, files, identity, jerseys, rallies, scoreboard, tables, web
from volleyball_stats.court import Calibration
from volleyball_stats.players import Row
from volleyball_stats.review_answers import TOUCH_TYPES, Ref, card_numbers, checked, log_of, meeting, path, piece_vectors, propose, prototypes, read_absent, reviewed, suggest


# Frames between two boxes of a question's outline, pictures shown per piece and per identity, and
# frames looked at for the clearest picture of a piece.
BOX_STEP, PIECE_CROPS, IDENTITY_CROPS, CANDIDATES = 2, 3, 8, 12
# A player is alone in a frame where no other box covers ALONE of theirs.
ALONE = 0.05
# A touch added in the review is looked for near the ball seen up to BALL_NEAR frames from it (`Questions.nearest`).
BALL_NEAR = 12
CROP_PX, CROP_MARGIN = 448, 0.15
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
# are not asked: about a touch each, a rally checked in the Match tab answers them faster, in their
# play (13 Nov, last match: 225 questions over 10 for 193 touches, 32 over 20 for 30).
MIN_IMPACT = 20.0
# Doubtful touches (`doubtful`) are asked first, each clip TOUCH_AROUND_S on both sides of the touch,
# zoomed on where it happens, outlined and slowed to TOUCH_SLOW only TOUCH_SHOWN_S on both sides of
# it (a contact found up to a few frames off): only that moment is asked about.
TOUCH_AROUND_S, TOUCH_SHOWN_S, TOUCH_SLOW = 1.5, 0.25, 0.5
UNKNOWN = ("", "0")
# An ace's receiver is asked on its flight, slowed from the serve to its landing (ACE_FLIGHT_S after
# the serve when unseen), the whole picture shown: the landing found can be the ball leaving it.
ACE_FLIGHT_S = 1.5
# Touches not doubted asked too, the same ones each time: how many wrong picks the doubts miss.
SPOT_CHECKS = 20
# A rally window asked about is played whole with RALLY_AROUND_S on both sides, unzoomed.
RALLY_AROUND_S = 1.0


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
        t = tables.players(match / "players.csv")
        table = np.column_stack([t[k] for k in ("frame", "track", "x1", "y1", "x2", "y2", "court_x", "court_y")]).astype(float).reshape(-1, 8)
        # Where each box's feet stand on the court, in meters; which side of the net its track plays.
        self.court_of = table[:, 6:]
        self.left_of = t["team"] == "left"
        self.ball: tuple[np.ndarray, np.ndarray] | None = None
        table = table[:, :6].round().astype(np.int32)
        self.frame_of, self.track_of, self.box_of = table[:, 0], table[:, 1], table[:, 2:]
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
        self.page = web.page_data(self.match / "review")
        texts = scoreboard.load(self.match)
        missed = missed_points(self.page, texts) if self.page else []
        board = board_off(self.page, texts) if self.page else []
        done = set(checked(log_of(self.match)))
        still = board_still(self.page, texts, done) if self.page else []
        over = not_over(self.page, crossings(self.match, self.calibration, self.fps), done) if self.page and self.calibration else []
        best = records(self.page) if self.page else []
        self.reports = sorted(reports(self.match) + (unusual(self.page, done) if self.page else []) + missed + board + still + over + best, key=lambda r: r.get("time") or 0)
        answers = self.match / files.ANSWERS
        nothing = {str(a["frame"]) for a in (files.read_json(answers, {}).get("touch", [])) if a["identity"] is None}
        self.empty = [(w, r.get("set"), int(r["start_frame"])) for w, r in zip(windows, rallies) if all(row["frame"] in nothing for row in touches_in(actions, w))]
        self.aces = aces(self.page)

    def track_rows(self, track: int, start: int, end: int) -> np.ndarray:
        """Indices of a track's boxes from `start` to `end`, by frame."""
        rows = self.rows[track]
        frames = self.frame_of[rows]
        return rows[np.searchsorted(frames, start) : np.searchsorted(frames, end, side="right")]

    def track_at(self, frame: int, box: tuple) -> int | None:
        """The track of the box `box` at `frame`, None for none."""
        lo, hi = np.searchsorted(self.frame_of, frame), np.searchsorted(self.frame_of, frame, side="right")
        found = np.nonzero((self.box_of[lo:hi] == np.array(box)).all(axis=1))[0]
        return int(self.track_of[lo + found[0]]) if len(found) else None

    def nearest(self, frame: int, kind: str) -> list[str]:
        """The named players ("TEAM:IDENTITY") nearest the ball at `frame` (seen within BALL_NEAR frames), nearest
        first, as the pipeline picks a touch's player (`attribution.ranked`) on either side of the net: who likely made
        a touch added there (first ASPOM match: the right one first 107 of 147, against 32 by touches in the set)."""
        if self.ball is None:
            b = tables.ball(self.match / "ball.csv")
            seen = b["visible"] & ~np.isnan(b["x"])
            self.ball = (b["frame"][seen], np.column_stack([b["x"][seen], b["y"][seen]]))
        frames, places = self.ball
        near = np.flatnonzero(np.abs(frames - frame) <= BALL_NEAR)
        if not len(near):
            return []
        x, y = places[near[np.argmin(np.abs(frames[near] - frame))]]
        gap = round(attribution.GAP_S * self.fps)
        rows = range(np.searchsorted(self.frame_of, frame - gap), np.searchsorted(self.frame_of, frame + gap, side="right"))
        boxes = [Row(int(self.frame_of[r]), int(self.track_of[r]), tuple(map(float, self.box_of[r])), 1.0, (0.0, 0.0), tuple(map(float, self.court_of[r])), "left" if self.left_of[r] else "right") for r in rows]
        best: dict[int, float] = {}
        for side in ("left", "right"):
            for d, _, track in attribution.ranked([(frame, float(x), float(y), kind, side)], boxes, self.fps)[0]:
                best[track] = min(d, best.get(track, d))
        out = []
        for track in sorted(best, key=best.get):
            found = identity.lookup(self.table, track, frame)
            if found and f"{found[0]}:{found[1]}" not in out:
                out.append(f"{found[0]}:{found[1]}")
        return out

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
        photos = files.read_json(offered, {})
        out = {}
        for team, number in sorted({(r[3], r[4]) for r in self.table if r[4]}):
            shown = re.findall(r"crop\?f=(\d+)&b=([\d,-]+)", json.dumps(self.faces(team, number)["crops"]))
            out[team, number] = [(int(f), tuple(int(v) for v in b.split(","))) for f, b in shown] + [(m["frame"], tuple(m["box"])) for m in photos.get(f"{team}:{number}", [])]
        return out

    def picture_stamp(self) -> str:
        """What the numbers read on pictures depend on: the video, the reader and how pictures are cut."""
        source = self.match / "source.json"
        video = files.read_json(source, {}).get("video")
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
        touches, the name and jersey number given, the roster's players of its team (`teams`'
        names) who look most like it and, unnamed, the name proposed (`propose`)."""
        names = identity.named(self.table, identity.read_names(self.match))
        with open(self.match / "actions.csv") as f:
            touches = Counter((int(r["team"]), int(r["identity"])) for r in csv.DictReader(f) if r.get("identity"))
        seconds = identity.on_court(self.table, self.fps)
        out, left = [], identity.leftovers(seconds, names)
        unnamed = [k for k in seconds if k not in left and not names.get(k, {}).get("name")]
        absent = read_absent(self.match)
        taken = {(t, given["name"].casefold()) for (t, _), given in names.items() if given.get("name")} | {(t, n.casefold()) for t, n in absent}
        proposed = propose({k: self.vectors.get(k) for k in unnamed}, self.read, roster, teams, taken, {k: self.together(*k, names) for k in unnamed})
        for (team, number), played in sorted(seconds.items(), key=lambda kv: -kv[1]):
            if (team, number) in left:
                continue
            given = names.get((team, number), {})
            out.append({
                "team": team, "identity": number, "seconds": round(played, 1), "contacts": touches[team, number],
                **self.faces(team, number), "name": given.get("name"), "jersey": given.get("jersey"),
                "read": self.read.get((team, number)),
                "suggestions": suggest(self.vectors.get((team, number)), roster, teams[team - 1], self.together(team, number, names) | {n for t, n in absent if t == team}, self.read.get((team, number))),
                "proposed": proposed.get((team, number)),
            })
        return out

    def build(self, asked: set[str]) -> tuple[list[dict], dict[str, dict]]:
        """The questions not asked yet, who a piece is first (most at stake first), and what each answer means (the refs).
        None that a rally checked answers: who made a touch it shows a named player for, whether it is a rally;
        nor who made a touch already answered elsewhere (the match tab, a rally checked)."""
        out, refs = [], {}
        log = log_of(self.match)
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
            # A record to confirm is answered alone: "Fausse" drops its reading.
            if r.get("record"):
                ref = {**ref, "record": r["record"]}
            group = groups.setdefault(r["key"] if ref["start"] is None or r.get("record") else ref["start"], [question, [], ref])
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
        # Who a piece of track is first: one answer names every touch on it, and a rally checked
        # in the match tab answers the others.
        return sorted(out, key=lambda q: -q["impact"]) + told + found + missed + touches, refs


def touches_in(actions: list[dict], window: tuple[int, int]) -> list[dict]:
    """actions.csv's touches inside `window` (its lead included)."""
    return [r for r in actions if r["type"] not in web.NO_PLAYER and window[0] <= int(r["frame"]) <= window[1]]


def aces(page: dict | None) -> list[tuple[dict, dict | None, int]]:
    """The aces of the page no touch follows in their rally, nor a ball the review says a player let fall, those its stats
    count as missed receptions (stats.ts), each with the contact after it (the landing, None when unseen) and its
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
# A report outside every rally window is about the one starting up to REPORT_BEFORE_S after it or
# ending up to REPORT_AFTER_S before it (a viewer reports while it plays or just after); the page's report button labels
# it so (web/src/lib/playlist.ts, rallyReported).
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


def unusual(page: dict, done: set[int] = frozenset()) -> list[dict]:
    """The rallies of the review's `page` (its data.js) that do not look like one, as reports at
    their start (no winner and a set's final score: their end), `kind` "auto.REASON": no touch, not starting with a serve, two serves, a reception
    not right after a serve, a serve followed by something else than a reception, a team touching
    four times in a row (a block apart), a player touching twice in a row (after a block aside), a
    touch after a fault or a point (either ends the rally), a relance as a team's first touch or as its second its team plays
    on, on a rally of `done` (checked, by key) a set as its second the other team plays next (before, its 3rd touch is often
    missed: the editor doubts of it), served by the team that lost the set's point
    before (unless the referee got that point wrong: the serve may follow what really happened), no winner (with teams), a set's last rally ending off the final score given ("scoreOff",
    its id with the score: asked again once it moves), over GAP_S between two touches, a server out of their team's order
    (`rotation_slips`), and, on the first rally either plays, two players of a team with one jersey.
    A playing fault or a ball let fall (`web.NO_BALL`) is no touch of the ball in the order of touches; one ends the rally as a fault does. The same rally
    and reason keep the same id: one handled is not asked again. `shown` names who it is about."""
    out = []
    rallies = page["rallies"]
    people = page.get("people") or {}
    name = lambda c: people.get(str(c.get("person")), {}).get("name")  # noqa: E731
    slips = rotation_slips(page)
    for k, r in enumerate(rallies):
        touches = [c for c in page["contacts"] if c["rally"] == k and c["type"] not in web.NO_PLAYER]
        # The touches of the ball, playing faults and balls let fall aside.
        played = [c for c in touches if c["type"] not in web.NO_BALL]
        serves = [c for c in played if c["type"] == "serve"]
        why = []
        if not touches:
            why.append("empty")
        elif played and played[0]["type"] != "serve":
            why.append("noServe")
        if len(serves) > 1:
            why.append("twoServes")
        pairs = list(zip(played, played[1:]))
        # A rally's first touch a reception already says "noServe".
        if any(b["type"] == "pass" and a["type"] != "serve" for a, b in pairs):
            why.append("passWithoutServe")
        if any(a["type"] == "serve" and b["type"] != "pass" for a, b in pairs):
            why.append("serveNotReceived")
        if any(a.get("person") is not None and a.get("person") == b.get("person") and a["type"] != "block" for a, b in pairs):
            why.append("samePlayer")
        if any(web.labelled(a) == "error" for a in touches[:-1]):
            why.append("afterFault")
        if any(web.labelled(a) == "point" for a in touches[:-1]):
            why.append("afterPoint")
        run, side, second, over = 0, None, False, False
        for n, c in enumerate(played):
            who = c.get("team") or c["side"]
            run, side = (0 if c["type"] == "block" else run + 1 if who == side else 1), who
            # Both hands on a team's second touch make a relance when the other team plays next, a set when its own plays on.
            after = played[n + 1] if n + 1 < len(played) else None
            if run == 2 and after:
                on = after["type"] != "block" and (after.get("team") or after["side"]) == who
                second = second or (c["type"] == "relance" and on)
                over = over or (c["type"] == "set" and not on and r.get("key") in done)
            if run > 3:
                why.append("fourTouches")
                break
        if second:
            why.append("relanceSecond")
        if over:
            why.append("setOver")
        before = rallies[k - 1] if k else None
        if serves and serves[0].get("team") and before and before["set"] == r["set"] and before.get("winner") and not before.get("wrongCall") and serves[0]["team"] != before["winner"]:
            why.append("server")
        if page.get("teams") and r.get("winner") is None and not r.get("redo"):
            why.append("noWinner")
        given = dict(enumerate(page.get("scores") or [], 1)).get(r["set"])
        score = r.get("score") and f"{r['score'][0]}-{r['score'][1]}"
        if given and score and score != given and (k + 1 == len(rallies) or rallies[k + 1]["set"] != r["set"]):
            why.append("scoreOff")
        # A team's first touch (after the other team's touch but a serve, or after a block) is a dig, never a relance.
        if any(b["type"] == "relance" and (a["type"] == "block" or (a["type"] != "serve" and (a.get("team") or a["side"]) != (b.get("team") or b["side"]))) for a, b in pairs):
            why.append("relanceFirst")
        if any(b["t"] - a["t"] > GAP_S for a, b in pairs):
            why.append("gap")
        if k in slips:
            why.append("serverOrder")
        for reason in why:
            said = f"auto:{reason}:{r.get('window', r['start'])}" + (f":{score}" if reason == "scoreOff" else "")
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


# The measures a trophy is a record of (the page's `trophies.ts`): the contacts' key, the touch it is on, its unit's scale and
# name, from how many measured.
RECORDS = (("speed", "serve", 1, "km/h"), ("attackSpeed", "attack", 1, "km/h"), ("jump", "attack", 100, "cm"))
RECORD_FROM = 5


def records(page: dict) -> list[dict]:
    """Each trophy's record (the fastest serve and attack, the highest jump: the best single reading, which a wrong one wins)
    as a report on its touch to confirm, kind "auto.record.KEY", `shown` its value: "Juste" keeps it, "Fausse" ("wrong")
    drops that reading from the page (`web.wrong_measures`) and the next best one is asked after the apply. Its id holds the
    reading: a new one is asked again. Each is a question of its own, `record` (the key and frame) in its ref."""
    out = []
    for key, kind, scale, unit in RECORDS:
        measured = [c for c in page["contacts"] if c["type"] == kind and c.get(key) is not None and c.get("person") is not None]
        if len(measured) < RECORD_FROM:
            continue
        best = max(round(c[key] * scale) for c in measured)
        for c in measured:
            if round(c[key] * scale) == best:
                frame = c.get("f", round(c["t"] * page["fps"]))
                said = f"auto:record:{key}:{frame}:{best}"
                out.append({"id": said, "key": hashlib.sha256(said.encode()).hexdigest()[:12], "time": c["t"], "kind": f"auto.record.{key}", "comment": None, "shown": f"{best} {unit}", "record": {"key": key, "frame": frame}})
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
            said = f"auto:boardStill:{r['set']}:{left}-{right}:{r.get('window', r['start'])}"
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
    last = {c["rally"]: c for c in page["contacts"] if c["type"] not in web.NO_PLAYER and c["type"] not in web.NO_BALL}
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
        # What the viewer's page said it was about: the clip playing; without one, the rally and its time, which the
        # rally's header and the report's own time say (an older page named the next rally between two, by its start); the
        # review's own checks, their value (a record's).
        "reports": [{"kind": report.get("kind"), "shown": report.get("shown") if report.get("clip") or str(report.get("kind") or "").startswith("auto.") else None, "comment": report.get("comment") or "", "time": round(at, 2), "received": report.get("received"), **({"at": report["at"]} if report.get("at") else {})}],
        "touches": touches, "winner": rally.get("winner"),
    }
    key = rally.get("key", round(rally["start"] * fps)) if k is not None else None
    return {**question, "rally": key}, {"start": key, "touches": {str(t["frame"]): t["team"] for t in touches}}


def unnamed(site: Path, fps: float) -> dict[int, str]:
    """The touches the page at `site` credits to no named player of their team, by frame: "brief"
    when its player was on the court only seconds in the set (web.brief), else "unknown". Asking them
    all leaves the page no unidentified player."""
    data = web.page_data(site)
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
