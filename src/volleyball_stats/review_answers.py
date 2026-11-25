"""The review's answers and names (the questions are review_questions.py, the server review_server.py): what each
answer adds to identity_answers.json, the log of those answers (superseded, let go, marked as someone else, moved onto a new
tracking: `reanchor`), and the names and jersey numbers in player_names.json.

The roster (--roster, outputs/roster.json by default, kept out of the repository: it names people)
remembers the named players across matches with their re-identification embedding of their last
ROSTER_MATCHES matches, suggests the names of those who look most like each new identity and proposes one per card.
"""

import json
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from volleyball_stats import files, identity, jerseys, likeness, pictures, timeouts, web
from volleyball_stats.teams import clock, match_end, parse_colour, seconds

if TYPE_CHECKING:
    from volleyball_stats.review_questions import Questions


KINDS = ("same", "different", "not_player", "cut", "team", "touch", "rally", "receiver", "partner", "action", "winner", "added", "end", "join", "split", "pinned", "locked", "redo", "referee", "wrong")
ROSTER = Path("outputs/roster.json")
# The names removed in the review, by team: players absent from the match, never proposed nor suggested again in it.
ABSENT = "absent_names.json"
# Matches of a player the roster keeps (the latest), and names suggested per identity.
ROSTER_MATCHES, SUGGESTIONS = 5, 3
# Readings of a number from which it is a player's: on the second match, 102-616 for the players' own,
# 44 at most for a number on a player who has another.
CARD_READINGS = 20
PICTURE_READINGS = 2

Ref = dict


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


# Touches a report's corrections can give, and their results.
# "fault": a fault made without the ball (net, centre line, rotation), "missed": a ball its player should have played, let
# fall untouched; only the review adds them (`web.NO_BALL`).
TOUCH_TYPES, RESULTS = ("serve", "pass", "set", "attack", "relance", "block", "dig", "fault", "missed"), ("play", "point", "error")


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


def set_name(match: Path, questions: "Questions", team: int, number: int, given: str | None, jersey: int | None) -> None:
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
    """pictures.PHOTO_PICKED with the card picture of identity `number` of `team` taken at `frame` in
    `box`, by the player's name (it outlives the identities' numbers), else by their card."""
    who = (identity.named(table, identity.read_names(match)).get((team, number)) or {}).get("name")
    path = match / pictures.PHOTO_PICKED
    taken = files.read_json(path, {})
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
    people = (web.page_data(site) or {}).get("people")
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
    return files.read_json(path, {}).get("log", [])


def log_of(match: Path) -> list[dict]:
    """The log of the review's answers on `match`, empty before any."""
    return load_log(match / files.ANSWERS)


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


def checked(log: list[dict]) -> list[int]:
    """The rallies the user checked and did not uncheck since, by their key: they show green while
    no report is open on them."""
    out: set[int] = set()
    for e in log:
        out = (out | set(e.get("checked", []))) - set(e.get("unchecked", []))
    return sorted(out)


def restorable(log: list[dict]) -> dict[str, dict]:
    """The rallies an edit unchecked and nothing checked since, by their key: the corrections on their frames when last
    checked (`was`, as the page sent them), to put back. An apply ends it: the page then shows what was saved."""
    out: dict[str, dict] = {}
    for e in log:
        for k in e.get("checked", []):
            out.pop(str(k), None)
        for k in e.get("unchecked", []):
            was = None if e.get("applied", True) else (e.get("was") or {}).get(str(k))
            if was is None:
                out.pop(str(k), None)
            else:
                out[str(k)] = was
    return out


def reviewed(page: dict | None, log: list[dict]) -> bool:
    """Whether every rally of the review's `page` is checked."""
    keys = {r["key"] for r in (page or {}).get("rallies", [])}
    return bool(keys) and keys <= set(checked(log))
