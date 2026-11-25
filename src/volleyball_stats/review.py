"""Review, on the video, the player identities the identity step is least sure of: the questions, the answers and the
names (the server is review_server.py).

    uv run python -m volleyball_stats.review_server outputs/matches/VIDEO --video VIDEO --court COURT_JSON [--squad N[,N]] [--theme NAME] [--roster PATH] [--port PORT]

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
ROSTER_MATCHES matches, suggests the names of those who look most like each new identity and proposes one per card.
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

from volleyball_stats import analysis, attribution, contacts, feedback, film, files, identity, jerseys, likeness, rallies, scoreboard, tables, timeouts, web
from volleyball_stats.court import Calibration
from volleyball_stats.players import Row
from volleyball_stats.teams import clock, match_end, parse_colour, seconds

# Frames between two boxes of a question's outline, pictures shown per piece and per identity, and
# frames looked at for the clearest picture of a piece.
BOX_STEP, PIECE_CROPS, IDENTITY_CROPS, CANDIDATES = 2, 3, 8, 12
# A player is alone in a frame where no other box covers ALONE of theirs.
ALONE = 0.05
# A touch added in the review is looked for near the ball seen up to BALL_NEAR frames from it (`Questions.nearest`).
BALL_NEAR = 12
CROP_PX, CROP_MARGIN = 448, 0.15
KINDS = ("same", "different", "not_player", "cut", "team", "touch", "rally", "receiver", "partner", "action", "winner", "added", "end", "join", "split", "pinned", "locked", "redo", "referee", "wrong")
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
ROSTER = Path("outputs/roster.json")
# What the identities were last computed from (`state`), to tell what an apply would change.
APPLIED = "identity_applied.json"
# The names removed in the review, by team: players absent from the match, never proposed nor suggested again in it.
ABSENT = "absent_names.json"
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
        self.page = page_data(self.match / "review")
        texts = scoreboard.load(self.match)
        missed = missed_points(self.page, texts) if self.page else []
        board = board_off(self.page, texts) if self.page else []
        done = set(checked(load_log(self.match / "identity_answers.json")))
        still = board_still(self.page, texts, done) if self.page else []
        over = not_over(self.page, crossings(self.match, self.calibration, self.fps), done) if self.page and self.calibration else []
        best = records(self.page) if self.page else []
        self.reports = sorted(reports(self.match) + (unusual(self.page, done) if self.page else []) + missed + board + still + over + best, key=lambda r: r.get("time") or 0)
        answers = self.match / "identity_answers.json"
        nothing = {str(a["frame"]) for a in (json.loads(answers.read_text()).get("touch", []) if answers.exists() else []) if a["identity"] is None}
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


def last_comparison(outputs: Path) -> dict | None:
    """The scores of the last update's runs (learn.json, its `update`; the newest run alone before 14 Nov 2026) and of
    the results they replaced, on the same answers, summed over its matches; None if it did not measure them."""
    lasts = [runs[-1] for path in sorted(outputs.glob("*/learn.json")) if (runs := json.loads(path.read_text()))]
    if not lasts:
        return None
    newest = max(lasts, key=lambda r: r["time"])
    same = [r for r in lasts if "before" in r and (r is newest or (newest.get("update") and r.get("update") == newest["update"]))]
    if not same:
        return None

    def summed(found: list[dict]) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for scores in found:
            for key, (right, total) in scores.items():
                sums = out.setdefault(key, [0, 0])
                sums[0], sums[1] = sums[0] + right, sums[1] + total
        return out

    return {"before": summed([r["before"] for r in same]), "after": summed([r["scores"] for r in same])}


def page_data(site: Path) -> dict | None:
    """The data.js of the page at `site`, None without one."""
    path = site / "data.js"
    if not path.exists():
        return None
    text = path.read_text()
    return json.loads(text[text.index("=") + 1 :].strip().rstrip(";"))


# Touches a report's corrections can give, and their results.
# "fault": a fault made without the ball (net, centre line, rotation), "missed": a ball its player should have played, let
# fall untouched; only the review adds them (`web.NO_BALL`).
TOUCH_TYPES, RESULTS = ("serve", "pass", "set", "attack", "relance", "block", "dig", "fault", "missed"), ("play", "point", "error")
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


def cause_of(change: dict) -> dict:
    """A correction's `cause`, the frame of the teammate's touch a fault is put on (`web.blamed`), as an `action`
    answer holds it: None for nobody else, nothing when the correction says nothing of it."""
    if "cause" not in change:
        return {}
    try:
        return {"cause": int(change["cause"]) or None}
    except (TypeError, ValueError):
        return {"cause": None}


def partner_of(change: dict, frame: int, team: int, given: dict[tuple[int, int], dict]) -> list[dict]:
    """A correction's `partner`, the second player ("TEAM:IDENTITY") its fault is shared with, as `partner` answers (`touch`
    ones' shape): no one for "none", nothing when the correction says nothing of it."""
    said = change.get("partner")
    if said == "none":
        return touch_answer({"frame": frame, "team": team}, "nobody", given)["touch"]
    if not said:
        return []
    t, i = (int(v) for v in str(said).split(":"))
    return touch_answer({"frame": frame, "team": t}, f"player:{t}:{i}", given)["touch"]


def report_answer(changes: dict, teams: dict[int, int], windows: list[tuple[int, int]], given: dict[tuple[int, int], dict], lead: int, keys: list[int] | None = None) -> dict:
    """What the corrections made in the review add to identity_answers.json, anywhere in the match
    (the page's touches' `teams` by frame, its rally `windows` and the `keys` naming them, their
    starts by default): a touch's player ("TEAM:IDENTITY") or none ("none", no touch) as `touch`
    answers, its type or result as `action` ones, the second player a fault is shared with ("TEAM:IDENTITY", "none" for no
    one) as `partner` ones; a touch added (frame, team, type, result, player, partner)
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
            out["action"].append({"frame": frame, "result": c["result"], **cause_of(c)})
        if c.get("player"):
            t, i = (int(v) for v in str(c["player"]).split(":"))
            out["touch"] += touch_answer({"frame": frame, "team": t}, f"player:{t}:{i}", given)["touch"]
        out["partner"] += partner_of(c, frame, team, given)
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
        out["partner"] += partner_of(c, frame, team, given)
        fix = {**{k: c[k] for k, allowed in (("type", TOUCH_TYPES), ("result", RESULTS)) if c.get(k) in allowed}, **cause_of(c)}
        if fix:
            out["action"].append({"frame": frame, **fix})
    if not out["partner"]:
        del out["partner"]
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


def propose(cards: dict[tuple[int, int], np.ndarray | None], read: dict[tuple[int, int], int], roster: list[dict], teams: list[str | None], taken: set[tuple[int, str]] = frozenset(), unless: dict[tuple[int, int], set[str]] | None = None) -> dict[tuple[int, int], dict]:
    """A name and jersey number for each card of `cards` (team, identity: its vector), each roster player on one card at
    most: the one of its team wearing the number `read` on it first, then the most alike pairs left, but a player who
    last wore another number than the one read; a card left with a number read is "Joueur N". Not the names `taken` in
    its team, nor those in its `unless`. No floor on the likeness: the wrong ones (0.81-0.89) sit among the right ones
    (0.74-0.997, benchmarks/identity/names.py)."""
    unless = unless or {}
    mean = [np.mean(list(p["vectors"].values()), axis=0) if p["vectors"] else None for p in roster]
    mean = [m / max(float(np.linalg.norm(m)), 1e-9) if m is not None else None for m in mean]
    pairs = []
    for card, vector in cards.items():
        team = teams[card[0] - 1]
        for k, player in enumerate(roster):
            if vector is None or mean[k] is None or team and player.get("team") and player["team"] != team:
                continue
            if (card[0], player["name"].casefold()) in taken or player["name"] in unless.get(card, ()):
                continue
            like = float(mean[k] @ vector)
            worn = card in read and player.get("jersey") == read[card]
            # Another number read than the one last worn: often a jersey changed hands (no team jerseys).
            other = card in read and player.get("jersey") is not None and not worn
            if not other:
                pairs.append((not worn, -like, card, k))
    out: dict[tuple[int, int], dict] = {}
    used: set[int] = set()
    for _, _, card, k in sorted(pairs):
        if card not in out and k not in used:
            out[card] = {"name": roster[k]["name"], "jersey": read.get(card, roster[k].get("jersey"))}
            used.add(k)
    given = set(taken) | {(card[0], p["name"].casefold()) for card, p in out.items()}
    for card in cards:
        # likeness.NUMBERED
        name = f"Joueur {read[card]}" if card in read else None
        if card not in out and name and (card[0], name.casefold()) not in given:
            out[card] = {"name": name, "jersey": read[card]}
            given.add((card[0], name.casefold()))
    return out


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


def read_absent(match: Path) -> list[tuple[int, str]]:
    path = match / ABSENT
    return [(int(t), n) for t, n in json.loads(path.read_text())["absent"]] if path.exists() else []


def name_absent(match: Path, table: list, team: int, name: str | None, removed: str | None) -> None:
    """ABSENT after a card of `team` was named `name`: that name no longer absent; else the name `removed` from it (given
    or only proposed) absent, unless another card of the team still holds it."""
    absent = read_absent(match)
    if name and name.strip():
        kept = [(t, n) for t, n in absent if (t, n.casefold()) != (team, name.strip().casefold())]
    elif removed and removed.strip():
        held = {given["name"].strip().casefold() for (t, _), given in identity.named(table, identity.read_names(match)).items() if t == team and given.get("name")}
        gone = removed.strip()
        known = gone.casefold() in held or (team, gone.casefold()) in {(t, n.casefold()) for t, n in absent}
        kept = absent if known else [*absent, (team, gone)]
    else:
        return
    if kept != absent:
        files.write_text(match / ABSENT, json.dumps({"absent": [list(a) for a in kept]}, ensure_ascii=False) + "\n")


def set_photo(match: Path, table: list, team: int, number: int, frame: int, box: list[int]) -> None:
    """web.PHOTO_PICKED with the card picture of identity `number` of `team` taken at `frame` in
    `box`, by the player's name (it outlives the identities' numbers), else by their card."""
    who = (identity.named(table, identity.read_names(match)).get((team, number)) or {}).get("name")
    path = match / web.PHOTO_PICKED
    taken = json.loads(path.read_text()) if path.exists() else {}
    taken[who or f"{team}:{number}"] = {"frame": int(frame), "box": [int(v) for v in box]}
    files.write_text(path, json.dumps(taken, indent=1, ensure_ascii=False) + "\n")


def set_look(match: Path, table: list, team: int, number: int, field: str, value: str) -> None:
    """likeness.CHOICES with the 3D figure's `field` (`figure`, a man's or a woman's, or `hair`, its colour) of identity
    `number` of `team` set to `value`, by the player's name, else by their card; the review's page showing it at once, and
    by name (not a likeness.NUMBERED one) the pages of the player's other matches too, their own choice following (their
    hosted copies then late)."""
    who = (identity.named(table, identity.read_names(match)).get((team, number)) or {}).get("name")
    likeness.choose(match, who or f"{team}:{number}", field, value)
    show_look(match / "review", lambda p: (p["team"], p["number"]) == (team, number) or bool(who and p.get("name") == who), field, value)
    if not who or likeness.NUMBERED.fullmatch(who):
        return
    for other in sorted(p for p in match.parent.iterdir() if p != match and (p / "review" / "data.js").exists()):
        if show_look(other / "review", lambda p: p.get("name") == who, field, value):
            likeness.choose(other, who, field, value)


def show_look(site: Path, whose: Callable[[dict], bool], field: str, value: str) -> bool:
    """The page at `site` with the 3D figure's `field` of each person `whose` set to `value`; whether one was."""
    people = (page_data(site) or {}).get("people")
    found = [p for p in (people or {}).values() if whose(p)]
    if not found:
        return False
    for person in found:
        person["look"] = {**(person.get("look") or {}), field: value}
    web.patch_people(site, people)
    return True


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


def given_sets(match: Path) -> list[str]:
    """The set starts teams.json gives, as written."""
    path = match / "teams.json"
    return (json.loads(path.read_text()).get("sets") or ["0:00"]) if path.exists() else ["0:00"]


def set_start(match: Path, fps: float, add: float | None = None, remove: str | None = None) -> None:
    """teams.json with a set starting at the rally playing `add` seconds into the video or the next one (the set start the
    middle of the break before it), or without the set start `remove`; the scores of the sets kept stay theirs.
    ValueError for a first rally, a moment after the last one, or the first set's start."""
    path = match / "teams.json"
    data = json.loads(path.read_text())
    starts = data.get("sets") or ["0:00"]
    scores = dict(zip(starts, data.get("scores") or []))
    if add is not None:
        windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in web.read_csv(match / "rallies.csv")]
        k = next((k for k, (_, end) in enumerate(windows) if end >= add * fps), None)
        if not k:
            raise ValueError(f"no set can start at {add} s")
        # One start a break: a start already in it gives way.
        kept = [s for s in starts if not windows[k - 1][1] < seconds(s) * fps <= windows[k][0]]
        starts = sorted([*kept, clock((windows[k - 1][1] + windows[k][0]) / 2 / fps)], key=seconds)
    if remove is not None:
        if remove not in starts[1:]:
            raise ValueError(f"no set starts at {remove!r} but the first")
        starts = [s for s in starts if s != remove]
    data["sets"], data["scores"] = starts, [scores.get(s) for s in starts]
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
    player (`touch`), action and result (`action`), the second player of a fault shared (`partner`), and the touches themselves (`locked`: the page
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
            out["action"].append({"frame": frame, "type": c["type"], "result": web.labelled(c), **({"cause": c["cause"]} if c.get("cause") else {})})
            # Keyed by text once read from data.js.
            p = people.get(str(c["person"]), people.get(c["person"])) if c.get("person") is not None else None
            if p and p.get("number") is not None and p["team"] == c["team"]:
                out["touch"] += touch_answer({"frame": frame, "team": c["team"]}, f"player:{p['team']}:{p['number']}", given)["touch"]
            q = people.get(str(c["partner"]), people.get(c["partner"])) if c.get("partner") is not None else None
            if q and q.get("number") is not None:
                out["partner"] += touch_answer({"frame": frame, "team": q["team"]}, f"player:{q['team']}:{q['number']}", given)["touch"]
        out["locked"].append({"start": r["key"], "touches": mine})
    return [{"id": "lock", "choice": "locked", **out, "applied": True}] if out else []


def unlocked(keys: list[int]) -> list[dict]:
    """An answer unlocking the rallies unchecked (`keys`): their touches stay as answered."""
    return [{"id": "unlock", "choice": "unlocked", "locked": [{"start": k, "touches": None} for k in keys], "applied": True}] if keys else []


# Each step's and pipeline stage's duration in seconds before one is measured: the first ASPOM
# match, 4K, on the M4 (1 Nov); "play" and "playTraining" on the RTX 5080 (12 Nov), "pipeline:identity" there too with its
# embeddings computed (17 Nov, 0.39 s per second of video).
TOOK = {
    "reports": 3.0, "training": 270.0, "playTraining": 2400.0, "pipeline": 2400.0, "players": 25.0, "questions": 3.0, "roster": 1.0, "review": 15.0, "page": 10.0, "hosting": 60.0, "hostingAll": 120.0, "copies": 4800.0, "films": 2400.0, "film": 180.0, "highlights": 300.0,
    "pipeline:tracking": 7200.0, "pipeline:play": 620.0, "pipeline:rallies": 25.0, "pipeline:actions": 640.0, "pipeline:wrists": 790.0, "pipeline:gesture": 480.0, "pipeline:teams": 880.0, "pipeline:jerseys": 2400.0, "pipeline:scoreboard": 360.0,
    "pipeline:identity": 1560.0, "pipeline:jumps": 420.0, "pipeline:answers": 60.0,
}
# The pipeline's stages in order (match.stage): "tracking" only when the trackers run again, "play" only with its model
# (`playing.available`) on a match it has not seen, "gesture" only with its model (`gesture.wanted`).
STAGES = ("tracking", "play", "rallies", "actions", "wrists", "gesture", "teams", "jerseys", "scoreboard", "identity", "jumps", "answers")
TIMINGS = "review_timings.json"


def eta(progress: dict, took: dict[str, float], now: float) -> dict:
    """Where a run of steps (`progress`: their names, the one running since when, its stage since when, the share it
    counted, `own`) stands at `now`. Only counted work moves it (the owner's rule): the whole run's share (`fraction`),
    each step and stage weighted by its last duration (`weights`, kept as the run started, else `took`), the running
    one's counted share (`part`, None while it counts nothing: the bar holds); the time spent and left, from the pace
    of the counted share, else the last duration; and whether the step or stage runs longer than it did (`late`)."""
    weights = progress.get("weights") or took
    steps, done, stage, own = progress["steps"], progress["done"], progress.get("stage"), progress.get("own")
    step = steps[done]
    if stage:
        later = [s for s in STAGES[STAGES.index(stage) + 1 :] if s not in ("tracking", "play")] if stage in STAGES else []
        spent, expected = now - progress["stage_since"], weights.get(f"{step}:{stage}", 0.0)
        rest = sum(weights.get(f"{step}:{s}", 0.0) for s in later)
    else:
        spent, expected = now - progress["since"], weights.get(step, 1.0)
        rest = 0.0
    counted = own is not None and own > 0.01
    here = spent * (1 - own) / own if counted else max(0.0, expected - spent)
    left = here + rest + sum(weights.get(s, 1.0) for s in steps[done + 1 :])
    whole = weights.get(step, 1.0)
    within = min(whole, progress.get("passed", 0.0) + (own or 0.0) * (expected if stage else whole))
    fraction = (sum(weights.get(s, 1.0) for s in steps[:done]) + within) / max(sum(weights.get(s, 1.0) for s in steps), 1e-9)
    late = spent / own > expected > 0 if counted else 0 < expected < spent
    return {"steps": steps, "done": done, "stage": stage, "elapsed": now - progress["started"], "left": left, "late": late, "part": own, "fraction": min(1.0, fraction)}


def checked(log: list[dict]) -> list[int]:
    """The rallies the user checked and did not uncheck since, by their key: they show green while
    no report is open on them."""
    out: set[int] = set()
    for e in log:
        out = (out | set(e.get("checked", []))) - set(e.get("unchecked", []))
    return sorted(out)


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


def given(answers: dict) -> dict:
    """The kinds of `answers` with something said: a kind added since the last apply, empty, changes nothing."""
    return {kind: said for kind, said in answers.items() if said}


# What an apply takes in, by what the answers are about (`waiting`'s `toApply`): an answer counts once, under its first.
ABOUT = {
    "players": ("same", "different", "not_player", "cut", "team", "join", "split"),
    "touches": ("touch", "receiver", "partner"),
    "actions": ("action", "added", "wrong", "redo"),
    "rallies": ("rally", "winner", "end", "referee"),
}


def to_apply(log: list[dict], changed: dict[str, bool]) -> list[list]:
    """What an apply takes in, for its button: the answers not applied yet by what they are about, with how many, then
    `changed`'s parts ("answers" when the answers differ with none of those, as after an undo)."""
    counts = dict.fromkeys(ABOUT, 0)
    for e in log:
        said = [kind for kind in KINDS if e.get(kind)]
        if not e.get("applied", True) and said:
            counts[next((a for a, kinds in ABOUT.items() if set(kinds) & set(said)), "rallies")] += 1
    out = [[about, n] for about, n in counts.items() if n]
    return out + [[part, None] for part, on in changed.items() if on and not (part == "answers" and out)]


def applied_too(match: Path, entries: list[dict]) -> None:
    """`entries`, saying what the page shows already, first in what the identities were computed from (APPLIED), as they
    are first in the log: else they would show as answers to apply."""
    computed = match / APPLIED
    if not computed.exists():
        return
    then = json.loads(computed.read_text())
    answers = then.setdefault("answers", {})
    for kind in KINDS:
        said = [x for e in entries for x in e.get(kind, [])]
        if said and kind not in ("pinned", "locked"):
            answers[kind] = said + answers.get(kind, [])
    files.write_text(computed, json.dumps(json.loads(json.dumps(then))))


def waiting(match: Path, log: list[dict], shown: set[str] | frozenset[str] = frozenset()) -> dict:
    """What an apply would take in: the answers saying something not applied yet (those saved
    before the flag were), whether the answers or the jersey numbers, and the names, differ from
    what the identities were computed from (APPLIED); the reports' `corrections` the review's
    page does not show yet (`shown`: the answers it was built with), the rallies `checked`, the
    `films` to make, players' and highlights, and whether the last learning run saw these answers."""
    computed = match / APPLIED
    now, then = state(match, log), json.loads(computed.read_text()) if computed.exists() else {}
    parts = {
        "answers": given(now["answers"]) != given(then.get("answers") or {}),
        # The jersey numbers' time to the second: a copy through the server (`sync`) keeps no less.
        "jerseys": now["jerseys"] != (None if then.get("jerseys") is None else int(then["jerseys"])),
        "timeouts": now["timeouts"] != then.get("timeouts", []),
        "names": now["names"] != then.get("names"),
    }
    return {
        "pending": sum(not e.get("applied", True) and any(e.get(kind) for kind in KINDS) for e in log),
        "changed": parts["answers"] or parts["jerseys"] or parts["timeouts"],
        "namesPending": parts["names"],
        "toApply": to_apply(log, parts),
        "corrections": corrections(log, shown),
        "checked": checked(log),
        "films": film.status(match),
        "due": due(match, log),
    }


def answers_stamp(log: list[dict]) -> str:
    """What the answers say, applied or not: kept with each learning run (learn.json)."""
    said = [{k: v for k, v in e.items() if k != "applied"} for e in log]
    return hashlib.sha256(json.dumps(said, sort_keys=True).encode()).hexdigest()[:16]


def silent(answer: dict) -> bool:
    """Whether `answer` teaches nothing: a report marked handled as the rally stood, no correction, no rally checked."""
    return (
        answer.get("choice") == "report"
        and set(answer) <= {"id", "choice", "applied", "changes"}
        and not any((answer.get("changes") or {}).values())
    )


def learned(match: Path, log: list[dict]) -> bool:
    """Whether the match's last learning run (learn.json) saw the answers as they stand, but for those given since that
    teach nothing (`silent`): a report marked handled no longer asks for the match to be analysed again."""
    path = match / "learn.json"
    runs = json.loads(path.read_text()) if path.exists() else []
    if not runs:
        return False
    n = len(log)
    while answers_stamp(log[:n]) != runs[-1].get("answers"):
        if not n or not silent(log[n - 1]):
            return False
        n -= 1
    return True


def due(match: Path, log: list[dict] | None = None) -> str | None:
    """Why the app's update would take `match` (learn.update): "answers" given since it last learned from them, "rules"
    when other code or models made its analysis (analysis.py); None for one up to date, or not analysed yet. A fully
    checked match keeps its labels: only new answers make it wait."""
    if not (match / "report.md").exists():
        return None
    log = load_log(match / "identity_answers.json") if log is None else log
    if log and not learned(match, log):
        return "answers"
    if reviewed(page_data(match / "review"), log):
        return None
    return "rules" if analysis.made_by(match) != analysis.fingerprint(match) else None


def rebuilt(match: Path, video: Path, court: Path, theme: str = web.CLUB) -> None:
    """`match`'s pages made again once its pipeline ran again outside the review (learn.update), its answers then
    applied, as the review's own reruns leave them."""
    web.review_page(match, video, court, theme)
    (match / STALE_PHOTOS).unlink(missing_ok=True)
    if (match / "page.json").exists():
        web.publish(match, video, court, theme, {})
    path = match / "identity_answers.json"
    log = [{**e, "applied": True} for e in load_log(path)]
    if path.exists():
        save(path, log)
    files.write_text(match / APPLIED, json.dumps(state(match, log)))


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


if __name__ == "__main__":
    # The review's command before review_server.py: a server started by an older app restarts so.
    from volleyball_stats.review_server import main

    main()
