"""The spoken commentary of a match page: short lines timed on the match, with the audio generated once for each text.

The script comes from the page's data alone, so that every build says what the page shows: a line whose audio is not
there yet (`voice.py` makes it) is left out. `outputs/MATCH/spoken.json` spells words for the voice ({"Loick": "Lo-ïk"}).
"""

import hashlib
import json
from pathlib import Path

TOUCHES = ("serve", "pass", "set", "attack", "relance", "block", "dig")
# From this many touches a rally is a long one.
LONG_RALLY = 8
# The server is called this long before the serve, a touch this long before it lands, at the earliest with the rally.
SERVE_LEAD_S = 0.9
CALL_LEAD_S = 0.05
# Nothing runs over a line about to start by less than this.
BREATH_S = 0.15
# Set points and late ties: from this many points before the end of a set.
SET_AT, LAST_SET_AT, TIE_WITHIN = 25, 15, 5
LAST_SET = 5
UNITS = "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize".split()
TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante"}
# What each touch is called, said in full when there is room before the next, else just the name.
CALLS = {
    "serve": ("{name} au service.", "Service de {name}.", "C'est {name} qui sert."),
    "pass": ("Réception de {name}.", "{name} en réception."),
    "set": ("Passe de {name}.", "{name} à la passe."),
    "attack": ("Attaque de {name} !", "{name} frappe !", "{name} à l'attaque !"),
    "dig": ("Défense de {name} !", "Belle défense de {name} !", "{name} sauve le ballon !"),
    "relance": ("Relance de {name}.", "{name} remet en jeu."),
    "block": ("Contre de {name} !", "{name} au contre !"),
}
POINTS = {
    "serve": ("Èsse de {name} !", "Èsse ! {name} ne laisse aucune chance !"),
    "attack": ("Attaque gagnante de {name} !", "Superbe frappe de {name} !", "{name} conclut !"),
    "block": ("Contre gagnant de {name} !", "Et le contre de {name} !"),
}
TEAM_POINTS = {"serve": "Un èsse pour {team} !", "attack": "Attaque gagnante pour {team} !", "block": "Contre gagnant pour {team} !"}
FAULTS = {
    "serve": "Le service de {name} ne passe pas.",
    "attack": "L'attaque de {name} ne passe pas.",
    "pass": "La réception de {name} ne tient pas.",
    "set": "Le ballon échappe à {name}.",
    "dig": "{name} ne peut pas suivre en défense.",
    "block": "Le contre de {name} ne suffit pas.",
    "relance": "La relance de {name} ne passe pas.",
    "fault": "Faute de jeu de {name}.",
}
# Which touches take the room first: the ball coming over, the serve, the save, then what builds the attack.
RANKS = {"attack": 0, "block": 0, "serve": 2, "reaction": 3, "dig": 3, "set": 4, "pass": 4, "relance": 4}
LATE_RANK = 1
REPLAY = "Revoyons ce point au ralenti, à la place de {name}."


def number(n: int) -> str:
    """`n` in French words, up to 59: a score."""
    if n < len(UNITS):
        return UNITS[n]
    tens, unit = n // 10 * 10, n % 10
    if n < 20:
        return f"dix-{UNITS[unit]}"
    return TENS[tens] + ("" if not unit else " et un" if unit == 1 else f"-{UNITS[unit]}")


def of_name(text: str) -> str:
    """"de Manon" written as "d'Anthony" before a vowel."""
    for vowel in "aeiouyhàâäéèêëîïôöùûüAEIOUYHÀÂÉÈÊËÎÏÔÖÙÛÜ":
        text = text.replace(f" de {vowel}", f" d'{vowel}").replace(f"De {vowel}", f"D'{vowel}")
    return text


def team_name(name: str) -> str:
    """A team's name said aloud: its numbers as words ("ASPOM 01", "ASPOM un")."""
    return " ".join(number(int(word)) if word.isdigit() and int(word) < 60 else word for word in name.split())


def _score_line(winner: int, score: list[int], team: str) -> str:
    mine, theirs = (score[0], score[1]) if winner == 1 else (score[1], score[0])
    if mine == theirs:
        return f"{team} égalise, {number(mine)} partout."
    if mine > theirs:
        return f"{team} mène, {number(mine)} à {number(theirs)}."
    return f"{team} revient, {number(mine)} à {number(theirs)}."


def _scored(touches: list[dict]) -> dict | None:
    """The touch that scored a rally: its last, or the one before a last touch of the other team that lost it."""
    last = touches[-1] if touches else None
    before = touches[-2] if len(touches) > 1 else None
    if last and last["result"] == "point":
        return last
    return before if last and last["result"] == "error" and before and before["result"] == "point" and before.get("team") != last.get("team") else None


def _end(rally: dict, k: int, contacts: list[dict], name, team, set_end: str | None) -> dict | None:
    if rally.get("redo"):
        return {"t": rally["end"] - 0.2, "text": "Le point est à rejouer.", "strong": True, "late": True}
    winner = rally.get("winner")
    moves = [c for c in contacts if c["type"] in TOUCHES or c["type"] == "fault"]
    if not winner or not moves:
        return None
    scored = _scored([c for c in moves if c["type"] != "fault"])
    final = moves[-1]
    t = max(final["t"] + 0.2, min(rally["end"], (scored or final)["t"] + 0.6))
    said = ""
    if scored and scored.get("team") == winner and scored["type"] in POINTS:
        who = name(scored["person"])
        ways = POINTS[scored["type"]]
        said = ways[k % len(ways)].format(name=who) if who else TEAM_POINTS[scored["type"]].format(team=team(winner))
    elif final.get("team") != winner and final["result"] == "error" and final["type"] in FAULTS and name(final["person"]):
        said = FAULTS[final["type"]].format(name=name(final["person"]))
    if set_end:
        return {"t": t, "text": of_name(f"{said} {set_end}".strip()), "strong": True, "late": True}
    score = rally.get("score")
    tail = _score_line(winner, score, team(winner)) if score else f"Point pour {team(winner)}."
    return {"t": t, "text": of_name(f"{said} {tail}".strip()), "strong": True, "late": True}


def script(data: dict) -> list[dict]:
    """The match's lines by time, each `t`, `text` and `strong`, said whatever comes before it; a touch's its `kind`, and `short`
    what to say when there is no room for `text`."""
    if not data.get("teams"):
        return []
    people = data["people"]
    name = lambda person: None if person is None else (people.get(str(person), people.get(person)) or {}).get("name")
    team = lambda g: team_name(data["teams"][g - 1]["name"] or f"Équipe {g}")
    by_rally: dict[int, list[dict]] = {}
    for c in data["contacts"]:
        by_rally.setdefault(c["rally"], []).append(c)
    rallies = data["rallies"]
    last_set = max((r["set"] for r in rallies), default=1)
    won = {1: 0, 2: 0}
    lines = []
    before = [0, 0]
    for k, r in enumerate(rallies):
        contacts = by_rally.get(k, [])
        touches = [c for c in contacts if c["type"] in TOUCHES]
        first = k == 0 or rallies[k - 1]["set"] != r["set"]
        if first:
            before = [0, 0]
        to = LAST_SET_AT if r["set"] == LAST_SET else SET_AT
        start = r["start"] - 0.7
        if max(before) >= to - 1 and before[0] != before[1]:
            lines.append({"t": start, "text": f"Balle de set pour {team(1 if before[0] > before[1] else 2)} !", "strong": True})
        elif before[0] == before[1] and before[0] >= to - TIE_WITHIN:
            lines.append({"t": start, "text": f"Égalité, {number(before[0])} partout.", "strong": True})
        scored = _scored(touches)
        for n, c in enumerate(touches):
            who = name(c["person"])
            # The rally's end tells the touch that scored and a last touch lost.
            if not who or c["type"] not in CALLS or c is scored or (n == len(touches) - 1 and c["result"] != "play"):
                continue
            ways = CALLS[c["type"]]
            said = of_name(ways[(k + n) % len(ways)].format(name=who))
            if c["type"] == "serve":
                lines.append({"t": max(start, c["t"] - SERVE_LEAD_S), "text": f"Set {number(r['set'])}. {said}" if first else said, "short": who, "strong": False, "kind": "serve"})
            else:
                lines.append({"t": c["t"] - CALL_LEAD_S, "text": said, "short": who, "strong": False, "kind": c["type"]})
        if len(touches) >= LONG_RALLY:
            lines.append({"t": touches[LONG_RALLY - 2]["t"], "text": "Quel échange !", "strong": False, "kind": "reaction"})
        set_over = k + 1 == len(rallies) or rallies[k + 1]["set"] != r["set"]
        set_end = None
        winner = r.get("winner")
        if set_over and winner and r.get("score"):
            won[winner] += 1
            mine, theirs = (r["score"][0], r["score"][1]) if winner == 1 else (r["score"][1], r["score"][0])
            ends_match = k + 1 == len(rallies) and r["set"] == last_set and won[winner] > won[3 - winner]
            set_end = f"{team(winner)} remporte le set, {number(mine)} à {number(theirs)}{', et le match' if ends_match else ''} !"
        end = _end(r, k, contacts, name, team, set_end)
        if end:
            lines.append(end)
        before = r.get("score") or before
    return sorted(lines, key=lambda line: line["t"])


def replay_lines(data: dict) -> dict[str, str]:
    """What a replay says, by the name of the player it follows."""
    named = {p.get("name") for p in data["people"].values() if p.get("name")}
    return {n: of_name(REPLAY.format(name=n)) for n in sorted(named)}


def read_spoken(match: Path) -> dict[str, str]:
    path = match / "spoken.json"
    return json.loads(path.read_text()) if path.exists() else {}


def spelled(text: str, spoken: dict[str, str]) -> str:
    """`text` spelled for the voice."""
    for word, sound in spoken.items():
        text = text.replace(word, sound)
    return text


def clip_name(text: str) -> str:
    """The audio file of a text as the voice reads it."""
    return hashlib.sha256(text.encode()).hexdigest()[:16] + ".mp3"


def placed(lines: list[dict], durations: dict[str, float], spoken: dict[str, str]) -> list[tuple[dict, str, str, float]]:
    """The lines to say, by time, each with its text, file and seconds, the most telling first in the running (`RANKS`): each
    in full where it fits between those already there, else in `short`, else not at all. A strong line is always said; a `late`
    one, a rally's end, waits for what is being said."""
    out: list[tuple[dict, str, str, float]] = []
    taken: list[tuple[float, float]] = []

    def rank(line: dict) -> float:
        return LATE_RANK if line.get("late") else -1 if line["strong"] else RANKS.get(line.get("kind"), len(RANKS))

    for line in sorted(lines, key=lambda x: (rank(x), x["t"])):
        for text in filter(None, (line["text"], line.get("short"))):
            clip = clip_name(spelled(text, spoken))
            if clip not in durations:
                continue
            start = line["t"]
            seconds = durations[clip] + BREATH_S
            if line.get("late"):
                for begin, stop in sorted(taken):
                    if start < stop and start + seconds > begin:
                        start = stop
            if line["strong"] or all(start + seconds <= begin or start >= stop for begin, stop in taken):
                out.append(({**line, "t": start}, text, clip, durations[clip]))
                taken.append((start, start + seconds))
                break
    return sorted(out, key=lambda item: item[0]["t"])


def fitted(lines: list[dict], durations: dict[str, float], spoken: dict[str, str]) -> list[list]:
    """The lines to say as flat [t, file, seconds]."""
    return [[round(line["t"], 2), clip, round(seconds, 2)] for line, _, clip, seconds in placed(lines, durations, spoken)]


def voice_index(match: Path, data: dict) -> dict | None:
    """What the page plays, from the audio in `match`/voice: `lines` and `replay`, a file by name; None without any."""
    folder = match / "voice"
    if not (folder / "durations.json").exists():
        return None
    durations = json.loads((folder / "durations.json").read_text())
    spoken = read_spoken(match)
    lines = fitted(script(data), durations, spoken)
    if not lines:
        return None
    replay = {n: clip_name(spelled(text, spoken)) for n, text in replay_lines(data).items()}
    return {"lines": lines, "replay": {n: clip for n, clip in replay.items() if clip in durations}, "folder": folder}
