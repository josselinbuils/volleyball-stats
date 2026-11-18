"""The spoken commentary of a match page: short lines timed on the match, with the audio generated once for each text.

The script comes from the page's data alone, so that every build says what the page shows: a line whose audio is not
there yet (`voice.py` makes it) is left out. A line is written as the page shows it (figures, "ace", "km/h") and spelled
for the voice (`spelled`); `outputs/matches/MATCH/spoken.json` spells words for it too ({"Loick": "Lo-ïk"}).

Like a commentator: each touch called, a different way each time; between rallies a remark on what the score or the
players just did (a streak, a comeback, a record, a milestone) and, now and then, a joke, never at a named player's
expense.
"""

import hashlib
import json
import re
from pathlib import Path

TOUCHES = ("serve", "pass", "set", "attack", "relance", "block", "dig")
# From this many touches a rally is a long one; from this many, the longest so far is remarked on, and joked about.
LONG_RALLY = 8
RECORD_RALLY = 10
JOKE_RALLY = 12
# The server is called this long before the serve, a touch this long before it lands, at the earliest with the rally.
SERVE_LEAD_S = 0.9
CALL_LEAD_S = 0.05
# Nothing runs over a line about to start by less than this.
BREATH_S = 0.15
# Set points and late ties: from this many points before the end of a set.
SET_AT, LAST_SET_AT, TIE_WITHIN = 25, 15, 5
LAST_SET = 5
# A remark between rallies waits for the rally's end to be said, and ends this long before the next serve.
REMARK_ROOM_S = 1.0
# A joke at most every this many rallies; a streak from this many points; a lead this wide is a gap; a comeback from this far.
JOKE_EVERY = 8
STREAK, HOT_STREAK = 3, 5
GAP = 5
COMEBACK = 4
# Records of speed are told once this many rallies are played, so that "the fastest" means something.
RECORD_AFTER = 20
# Milestones remarked on: aces from the second, attack points and blocks at these counts.
ATTACK_MILESTONES = (3, 5, 7, 10, 15, 20)
UNITS = "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize".split()
TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante"}
ORDINALS = {2: "Deuxième", 3: "Troisième", 4: "Quatrième", 5: "Cinquième", 6: "Sixième", 7: "Septième", 8: "Huitième", 9: "Neuvième", 10: "Dixième"}
SETS = {1: "premier", 2: "deuxième", 3: "troisième", 4: "quatrième", 5: "cinquième"}
# What each touch is called, said in full when there is room before the next, else just the name.
CALLS = {
    "serve": ("{name} au service.", "Service de {name}.", "C'est {name} qui sert.", "À {name} de servir.", "{name} prend le service."),
    "pass": ("Réception de {name}.", "{name} en réception.", "{name} réceptionne.", "{name} reçoit."),
    "set": ("Passe de {name}.", "{name} à la passe.", "{name} distribue.", "{name} lève le ballon.", "{name} met en place."),
    "attack": ("Attaque de {name} !", "{name} frappe !", "{name} à l'attaque !", "Et {name} qui frappe !", "{name} tente sa chance !", "{name} lâche le bras !"),
    "dig": ("Défense de {name} !", "Belle défense de {name} !", "{name} sauve le ballon !", "{name} va le chercher !", "Quel sauvetage de {name} !", "{name} remonte ça !"),
    "relance": ("Relance de {name}.", "{name} remet en jeu.", "{name} renvoie de l'autre côté."),
    "block": ("Contre de {name} !", "{name} au contre !", "{name} monte au contre !", "{name} lève les bras au filet !"),
}
POINTS = {
    "serve": ("Ace de {name} !", "Ace ! {name} ne laisse aucune chance !", "Service gagnant de {name} !", "Direct ! Ace de {name} !"),
    "attack": ("Attaque gagnante de {name} !", "Superbe frappe de {name} !", "{name} conclut !", "Et c'est {name} qui termine le point !", "Imparable, {name} !", "{name} fait mouche !"),
    "block": ("Contre gagnant de {name} !", "Et le contre de {name} !", "Le mur ! {name} ferme la porte !", "{name} dit non au filet !"),
}
TEAM_POINTS = {
    "serve": ("Un ace pour {team} !", "Service gagnant pour {team} !"),
    "attack": ("Attaque gagnante pour {team} !", "{team} conclut l'échange !"),
    "block": ("Contre gagnant pour {team} !", "Le contre de {team} fait le point !"),
}
FAULTS = {
    "serve": ("Le service de {name} ne passe pas.", "Service manqué pour {name}."),
    "attack": ("L'attaque de {name} ne passe pas.", "L'attaque de {name} sort du terrain."),
    "pass": ("La réception de {name} ne tient pas.",),
    "set": ("Le ballon échappe à {name}.",),
    "dig": ("{name} ne peut pas suivre en défense.",),
    "block": ("Le contre de {name} ne suffit pas.",),
    "relance": ("La relance de {name} ne passe pas.",),
    "fault": ("Faute de jeu de {name}.",),
    "missed": ("{name} laisse tomber le ballon.",),
}
# A ball let fall between two players (`partner`).
BETWEEN = ("Le ballon tombe entre {name} et {other}.",)
# A rally's end tells the score; who took the lead, levelled or pulled away is said so.
SCORES = {
    "tie": ("{team} égalise, {a} partout.", "{a} partout, {team} revient à hauteur.", "Tout est à refaire, {a} partout !"),
    "ahead": ("{team} passe devant, {a} à {b} !", "{team} prend l'avantage, {a} à {b}."),
    "gap": ("{team} creuse l'écart, {a} à {b}.", "{team} s'envole, {a} à {b}.", "{a} à {b}, {team} prend le large."),
    "lead": ("{team} mène, {a} à {b}.", "{a} à {b} pour {team}.", "{team} devant, {a} à {b}."),
    "behind": ("{team} revient, {a} à {b}.", "{team} réduit l'écart, {a} à {b}.", "{team} recolle, {a} à {b}."),
}
# The same when the point just named the team.
SCORES_UNNAMED = {
    "tie": ("{a} partout.", "Retour à {a} partout."),
    "ahead": ("Et les voilà devant, {a} à {b} !", "{a} à {b}, ça passe devant !"),
    "gap": ("L'écart se creuse, {a} à {b}.", "{a} à {b}, ça s'envole."),
    "lead": ("{a} à {b}.",),
    "behind": ("{a} à {b}, l'écart se réduit.", "{a} à {b}."),
}
LONG = ("Quel échange !", "Ça ne veut pas tomber !", "Le ballon refuse de toucher le sol !", "Quelle bataille !")
SET_START = {1: ("C'est parti pour le premier set !",), 0: ("Début du {nth} set.", "On attaque le {nth} set.", "Place au {nth} set.")}
WELCOME = ("Bienvenue pour ce match entre {one} et {two} !",)
GOODBYE = ("Merci d'avoir suivi ce match, à bientôt !",)
REMARKS = {
    "streak": ("{nth} point d'affilée pour {team}.", "{team} enchaîne, {nth_lower} point de suite."),
    "hot": ("{team} est en feu, {n} points d'affilée !", "Série de {n} points pour {team} !", "{n} points de suite, {team} déroule !"),
    "stopped": ("{team} met enfin fin à la série.", "La série s'arrête, enfin un point pour {team} !"),
    "comeback": ("{team} a effacé {n} points de retard !", "Quelle remontée de {team}, {n} points de retard effacés !"),
    "record": ("Le plus long échange du match jusqu'ici, {n} touches !", "{n} touches, c'est l'échange le plus long du match !"),
    "aces": ("Déjà {n} aces pour {name} !", "{name} en est à {n} aces dans ce match."),
    "ace2": ("Deuxième ace pour {name} !", "Et de deux pour {name} au service !"),
    "attacks": ("{nth} point en attaque pour {name}.", "{name} en est à {n} points en attaque."),
    "blocks": ("Déjà {n} contres gagnants pour {name} !", "{name} en est à {n} points au contre."),
    "serve_speed": ("Service de {name} à {v} km/h, le plus rapide du match !", "{v} km/h au service pour {name}, record du match !"),
    "serve_speed_team": ("Service à {v} km/h, le plus rapide du match !",),
    "attack_speed": ("Frappe de {name} à {v} km/h, la plus puissante du match !", "{v} km/h ! {name} signe la frappe la plus forte du match."),
    "attack_speed_team": ("Frappe à {v} km/h, la plus puissante du match !",),
    "close_set": ("Quel set accroché !", "Un set disputé jusqu'au bout."),
    "never_behind": ("{team} n'a jamais été mené dans ce set.",),
    "set_comeback": ("Belle remontée de {team} dans ce set !",),
    "one_sided": ("Set à sens unique pour {team}.", "{team} n'a pas fait de détail dans ce set."),
    "sides": ("Les équipes changent de côté.",),
    "timeout": ("Temps mort pour {team}.", "{team} demande un temps mort."),
    "timeout_none": ("Temps mort.",),
}
# Light-hearted, never at a named player's expense; at most every JOKE_EVERY rallies and one in each timeout, none twice in a match.
JOKES = {
    "long": ("Respirez, respirez !", "On va finir par jouer les prolongations !", "Les bras vont s'en souvenir demain matin.", "Personne ne veut lâcher ce ballon !"),
    "hot": ("Quelqu'un a le mode d'emploi pour arrêter {team} ?", "À ce rythme, il va falloir appeler des renforts en face !"),
    "serve_faults": ("Les services sont capricieux ce soir.", "Petite crise de service dans la salle !"),
    "ace": ("Celui-là, personne ne l'a vu passer !", "Même pas le temps de bouger !"),
    "tight": ("Ça se joue aux nerfs !", "Les cœurs battent fort dans la salle."),
    "redo": ("On efface tout et on recommence.",),
    "block": ("Interdit de passer !", "Le mur est fermé ce soir !"),
    "timeout": ("Le moment idéal pour boire un coup. D'eau, bien sûr.", "Le coach sort le tableau, ça va chauffer !", "Un peu de stratégie, et beaucoup de souffle à reprendre."),
}
# Which touches take the room first: the ball coming over, the serve, the save, then what builds the attack; a remark
# between rallies before the calls of the next.
RANKS = {"attack": 0, "block": 0, "serve": 2, "reaction": 3, "dig": 3, "set": 4, "pass": 4, "relance": 4}
LATE_RANK = 1
REPLAY = "Revoyons ce point au ralenti, à la place de {name}."
# Written as the page shows them, said so by the voice.
SAID = ((re.compile(r"\bAces\b"), "Èsses"), (re.compile(r"\bAce\b"), "Èsse"), (re.compile(r"\baces\b"), "èsses"), (re.compile(r"\bace\b"), "èsse"), (re.compile(r"km/h"), "kilomètres heure"))
FIGURES = re.compile(r"\b\d{1,3}\b")


def number(n: int) -> str:
    """`n` in French words, up to 199: a score, a speed."""
    if n < len(UNITS):
        return UNITS[n]
    if n < 20:
        return f"dix-{UNITS[n - 10]}"
    if n < 60:
        tens, unit = n // 10 * 10, n % 10
        return TENS[tens] + ("" if not unit else " et un" if unit == 1 else f"-{UNITS[unit]}")
    if n < 80:
        rest = n - 60
        return "soixante" + ("" if not rest else " et un" if rest == 1 else " et onze" if rest == 11 else f"-{number(rest)}")
    if n < 100:
        return "quatre-vingts" if n == 80 else f"quatre-vingt-{number(n - 80)}"
    if n < 200:
        return "cent" + ("" if n == 100 else f" {number(n - 100)}")
    return str(n)


def of_name(text: str) -> str:
    """"de Manon" written as "d'Anthony" before a vowel."""
    for vowel in "aeiouyhàâäéèêëîïôöùûüAEIOUYHÀÂÉÈÊËÎÏÔÖÙÛÜ":
        text = text.replace(f" de {vowel}", f" d'{vowel}").replace(f"De {vowel}", f"D'{vowel}")
    return text


class Ways:
    """Picks how to say a thing, by the moment so that a build says it the same, never the way just used for that kind."""

    def __init__(self):
        self.last: dict[str, int] = {}

    def __call__(self, kind: str, ways: tuple[str, ...], seed: int, **values) -> str:
        k = seed % len(ways)
        if len(ways) > 1 and self.last.get(kind) == k:
            k = (k + 1) % len(ways)
        self.last[kind] = k
        return of_name(ways[k].format(**values))


def _seed(item: dict, fallback: int) -> int:
    """A number of the moment, the same at every build: its frame."""
    return int(item.get("f", item.get("key", fallback)))


def _score_line(winner: int, score: list[int], before: list[int], team: str, ways: Ways, seed: int, named: bool = False) -> str:
    """The score after a point, from the winner's side; without the team's name where the point just said it (`named`)."""
    mine, theirs = (score[0], score[1]) if winner == 1 else (score[1], score[0])
    was_mine, was_theirs = (before[0], before[1]) if winner == 1 else (before[1], before[0])
    kind = "tie" if mine == theirs else "ahead" if was_mine <= was_theirs < mine else "gap" if mine - theirs >= GAP > was_mine - was_theirs else "lead" if mine > theirs else "behind"
    return ways(f"score:{kind}:{named}", (SCORES_UNNAMED if named else SCORES)[kind], seed, team=team, a=mine, b=theirs)


def _scored(touches: list[dict]) -> dict | None:
    """The touch that scored a rally: its last, or the one before a last touch of the other team that lost it."""
    last = touches[-1] if touches else None
    before = touches[-2] if len(touches) > 1 else None
    if last and last["result"] == "point":
        return last
    return before if last and last["result"] == "error" and before and before["result"] == "point" and before.get("team") != last.get("team") else None


def _end(rally: dict, k: int, contacts: list[dict], name, team, set_end: tuple[int, int, bool] | None, before: list[int], ways: Ways) -> dict | None:
    """What a rally's end says: who scored or gave the point away, then the score, or the set won (`set_end`: its score
    from the winner's side, and whether it ends the match)."""
    if rally.get("redo"):
        return {"t": rally["end"] - 0.2, "text": "Le point est à rejouer.", "strong": True, "late": True}
    winner = rally.get("winner")
    moves = [c for c in contacts if c["type"] in TOUCHES or c["type"] in ("fault", "missed")]
    if not winner or not moves:
        return None
    scored = _scored([c for c in moves if c["type"] in TOUCHES])
    final = moves[-1]
    t = max(final["t"] + 0.2, min(rally["end"], (scored or final)["t"] + 0.6))
    seed = _seed(scored or final, k)
    said = ""
    named = False
    if scored and scored.get("team") == winner and scored["type"] in POINTS:
        who = name(scored["person"])
        kind = scored["type"]
        said = ways(f"point:{kind}", POINTS[kind], seed, name=who) if who else ways(f"team:{kind}", TEAM_POINTS[kind], seed, team=team(winner))
        named = not who
    elif final.get("team") != winner and final["result"] == "error" and final["type"] == "missed" and name(final["person"]) and final.get("partner") is not None and name(final["partner"]):
        said = ways("fault:between", BETWEEN, seed, name=name(final["person"]), other=name(final["partner"]))
    elif final.get("team") != winner and final["result"] == "error" and final["type"] in FAULTS and name(final["person"]):
        said = ways(f"fault:{final['type']}", FAULTS[final["type"]], seed, name=name(final["person"]))
    if set_end:
        mine, theirs, match_over = set_end
        tail = f"{'Et le set' if named else team(winner) + ' remporte le set'}, {mine} à {theirs}{', et le match' if match_over else ''} !"
        return {"t": t, "text": f"{said} {tail}".strip(), "strong": True, "late": True}
    score = rally.get("score")
    tail = _score_line(winner, score, before, team(winner), ways, seed // 7, named) if score else "" if named else f"Point pour {team(winner)}."
    return {"t": t, "text": f"{said} {tail}".strip(), "strong": True, "late": True}


class Story:
    """What happened so far in the match, to remark on after each rally: streaks, comebacks, records, milestones."""

    def __init__(self):
        self.streak = (0, 0)
        self.worst = {1: 0, 2: 0}
        self.down = {1: 0, 2: 0}
        self.longest = 0
        self.fastest = {"speed": 0, "attackSpeed": 0}
        self.aces: dict[str, int] = {}
        self.attacks: dict[str, int] = {}
        self.blocks: dict[str, int] = {}
        self.serve_faults = 0
        self.joked = -JOKE_EVERY
        self.told: set[tuple[str, int]] = set()

    def new_set(self):
        self.streak = (0, 0)
        self.worst = {1: 0, 2: 0}
        self.down = {1: 0, 2: 0}

    def after(self, k: int, rally: dict, touches: list[dict], scored: dict | None, before: list[int], name, team, ways: Ways, set_over: bool) -> tuple[list[str], str | None]:
        """The remarks on rally `k` (the first is said), and a joke if one is due."""
        winner = rally.get("winner")
        seed = _seed(rally, k)
        if rally.get("redo") or not winner:
            return [], self._joke(k, "redo", seed, ways) if rally.get("redo") else None
        loser = 3 - winner
        remarks: list[str] = []
        jokes: list[str] = []
        streak_team, streak = self.streak
        stopped = streak_team == loser and streak >= HOT_STREAK - 1
        self.streak = (winner, streak + 1 if streak_team == winner else 1)
        run = self.streak[1]
        score = rally.get("score")
        if score:
            for g in (1, 2):
                self.worst[g] = min(self.worst[g], score[g - 1] - score[2 - g])
                self.down[g] = max(self.down[g], score[2 - g] - score[g - 1])
            # A comeback: level again after trailing by COMEBACK or more since the last tie.
            if score[0] == score[1]:
                if self.down[winner] >= COMEBACK:
                    remarks.append(ways("comeback", REMARKS["comeback"], seed, team=team(winner), n=self.down[winner]))
                self.down = {1: 0, 2: 0}
        if stopped:
            remarks.append(ways("stopped", REMARKS["stopped"], seed, team=team(winner)))
        # The scorer's milestones and the match's records.
        who = name(scored["person"]) if scored and scored.get("team") == winner else None
        if scored and scored.get("team") == winner and scored["type"] == "serve":
            jokes.append("ace")
            if who:
                self.aces[who] = self.aces.get(who, 0) + 1
                n = self.aces[who]
                if n == 2:
                    remarks.append(ways("ace2", REMARKS["ace2"], seed, name=who))
                elif n > 2:
                    remarks.append(ways("aces", REMARKS["aces"], seed, name=who, n=n))
        if scored and scored.get("team") == winner and scored["type"] == "attack" and who:
            self.attacks[who] = self.attacks.get(who, 0) + 1
            n = self.attacks[who]
            if n in ATTACK_MILESTONES:
                remarks.append(ways("attacks", REMARKS["attacks"], seed, name=who, n=n, nth=ORDINALS.get(n, f"{n}e")))
        if scored and scored.get("team") == winner and scored["type"] == "block":
            jokes.append("block")
            if who:
                self.blocks[who] = self.blocks.get(who, 0) + 1
                if self.blocks[who] >= 2:
                    remarks.append(ways("blocks", REMARKS["blocks"], seed, name=who, n=self.blocks[who]))
        for key, kind in (("speed", "serve_speed"), ("attackSpeed", "attack_speed")):
            measured = [c for c in touches if c.get(key)]
            if not measured:
                continue
            best = max(measured, key=lambda c: c[key])
            if best[key] > self.fastest[key]:
                beaten = self.fastest[key]
                self.fastest[key] = best[key]
                if k >= RECORD_AFTER and beaten:
                    fast = name(best["person"])
                    remarks.append(ways(kind, REMARKS[kind], seed, name=fast, v=best[key]) if fast else ways(f"{kind}_team", REMARKS[f"{kind}_team"], seed, v=best[key]))
        # A team's streak after what a player did, the longest rally last.
        if run >= HOT_STREAK:
            remarks.append(ways("hot", REMARKS["hot"], seed, team=team(winner), n=run))
            jokes.append("hot")
        elif run >= STREAK:
            nth = ORDINALS.get(run, f"{run}e")
            remarks.append(ways("streak", REMARKS["streak"], seed, team=team(winner), nth=nth, nth_lower=nth.lower()))
        if len(touches) > self.longest:
            if len(touches) >= RECORD_RALLY and self.longest:
                remarks.append(ways("record", REMARKS["record"], seed, n=len(touches)))
            self.longest = len(touches)
        if len(touches) >= JOKE_RALLY:
            jokes.append("long")
        last = touches[-1] if touches else None
        self.serve_faults = self.serve_faults + 1 if last and last["type"] == "serve" and last["result"] == "error" else 0
        if self.serve_faults >= 2:
            jokes.append("serve_faults")
        if score and score[0] == score[1] and score[0] >= SET_AT - TIE_WITHIN:
            jokes.append("tight")
        if set_over and score:
            mine, theirs = (score[0], score[1]) if winner == 1 else (score[1], score[0])
            if mine - theirs <= 2:
                remarks.insert(0, ways("close_set", REMARKS["close_set"], seed))
            elif self.worst[winner] >= 0:
                remarks.insert(0, ways("never_behind", REMARKS["never_behind"], seed, team=team(winner)))
            elif -self.worst[winner] >= COMEBACK:
                remarks.insert(0, ways("set_comeback", REMARKS["set_comeback"], seed, team=team(winner)))
            elif mine - theirs >= 2 * GAP:
                remarks.insert(0, ways("one_sided", REMARKS["one_sided"], seed, team=team(winner)))
            else:
                remarks.insert(0, ways("sides", REMARKS["sides"], seed))
        joke = next(filter(None, (self._joke(k, kind, seed, ways, team=team(winner)) for kind in jokes)), None)
        return remarks, joke

    def joke(self, kind: str, seed: int, **values) -> str | None:
        """One of `kind`'s jokes not told yet in the match, None once all were."""
        fresh = [i for i in range(len(JOKES[kind])) if (kind, i) not in self.told]
        if not fresh:
            return None
        i = fresh[seed % len(fresh)]
        self.told.add((kind, i))
        return of_name(JOKES[kind][i].format(**values))

    def _joke(self, k: int, kind: str, seed: int, ways: Ways, **values) -> str | None:
        if k - self.joked < JOKE_EVERY:
            return None
        said = self.joke(kind, seed, **values)
        if said:
            self.joked = k
        return said


def _between(t: float, until: float, texts: list[str]) -> list[dict]:
    """Lines said one after another from `t`, each only if it ends by `until`."""
    return [{"t": t, "text": text, "strong": False, "late": True, "kind": "remark", "until": until} for text in texts]


def script(data: dict) -> list[dict]:
    """The match's lines by time, each `t`, `text` and `strong`, said whatever comes before it; a touch's its `kind`, and `short`
    what to say when there is no room for `text`; a remark between rallies its `until`, by when it has to end."""
    if not data.get("teams"):
        return []
    people = data["people"]
    name = lambda person: None if person is None else (people.get(str(person), people.get(person)) or {}).get("name")
    team = lambda g: data["teams"][g - 1]["name"] or f"Équipe {g}"
    by_rally: dict[int, list[dict]] = {}
    for c in data["contacts"]:
        by_rally.setdefault(c["rally"], []).append(c)
    rallies = data["rallies"]
    if not rallies:
        return []
    last_set = max(r["set"] for r in rallies)
    won = {1: 0, 2: 0}
    ways = Ways()
    story = Story()
    lines = _between(max(0.0, rallies[0]["start"] - 8), rallies[0]["start"] - REMARK_ROOM_S, [ways("welcome", WELCOME, 0, one=team(1), two=team(2))])
    before = [0, 0]
    for k, r in enumerate(rallies):
        contacts = by_rally.get(k, [])
        touches = [c for c in contacts if c["type"] in TOUCHES]
        first = k == 0 or rallies[k - 1]["set"] != r["set"]
        if first:
            before = [0, 0]
            story.new_set()
        to = LAST_SET_AT if r["set"] == LAST_SET else SET_AT
        start = r["start"] - 0.7
        if max(before) >= to - 1 and before[0] != before[1]:
            lines.append({"t": start, "text": f"Balle de set pour {team(1 if before[0] > before[1] else 2)} !", "strong": True})
        elif before[0] == before[1] and before[0] >= to - TIE_WITHIN:
            lines.append({"t": start, "text": f"Égalité, {before[0]} partout.", "strong": True})
        scored = _scored(touches)
        for n, c in enumerate(touches):
            who = name(c["person"])
            # The rally's end tells the touch that scored and a last touch lost.
            if not who or c["type"] not in CALLS or c is scored or (n == len(touches) - 1 and c["result"] != "play"):
                continue
            said = ways(f"call:{c['type']}", CALLS[c["type"]], _seed(c, k + n), name=who)
            if c["type"] == "serve":
                opening = ways("set_start", SET_START[1 if r["set"] == 1 else 0], k, nth=SETS.get(r["set"], f"{r['set']}e"))
                lines.append({"t": max(start, c["t"] - SERVE_LEAD_S), "text": f"{opening} {said}" if first else said, "short": who, "strong": False, "kind": "serve"})
            else:
                lines.append({"t": c["t"] - CALL_LEAD_S, "text": said, "short": who, "strong": False, "kind": c["type"]})
        if len(touches) >= LONG_RALLY:
            lines.append({"t": touches[LONG_RALLY - 2]["t"], "text": ways("long", LONG, k, ), "strong": False, "kind": "reaction"})
        set_over = k + 1 == len(rallies) or rallies[k + 1]["set"] != r["set"]
        set_end = None
        winner = r.get("winner")
        ends_match = False
        if set_over and winner and r.get("score"):
            won[winner] += 1
            mine, theirs = (r["score"][0], r["score"][1]) if winner == 1 else (r["score"][1], r["score"][0])
            ends_match = k + 1 == len(rallies) and r["set"] == last_set and won[winner] > won[3 - winner]
            set_end = (mine, theirs, ends_match)
        end = _end(r, k, contacts, name, team, set_end, before, ways)
        if end:
            lines.append(end)
        remarks, joke = story.after(k, r, touches, scored, before, name, team, ways, set_over)
        nxt = rallies[k + 1]["start"] if k + 1 < len(rallies) else max(data.get("duration") or 0, r["end"] + 12)
        said_after = [*remarks[:1], *([joke] if joke else [])]
        if ends_match:
            said_after = [ways("goodbye", GOODBYE, 0)]
        lines += _between(end["t"] if end else r["end"], nxt - REMARK_ROOM_S, said_after)
        before = r.get("score") or before
    for g in data.get("timeouts") or []:
        said = ways("timeout", REMARKS["timeout"], int(g["start"]), team=team(g["team"])) if g.get("team") else ways("timeout_none", REMARKS["timeout_none"], 0)
        lines += _between(g["start"] + 1, g["end"] - REMARK_ROOM_S, [said, *filter(None, [story.joke("timeout", int(g["start"]))])])
    return sorted(lines, key=lambda line: line["t"])


def replay_lines(data: dict) -> dict[str, str]:
    """What a replay says, by the name of the player it follows."""
    named = {p.get("name") for p in data["people"].values() if p.get("name")}
    return {n: of_name(REPLAY.format(name=n)) for n in sorted(named)}


def read_spoken(match: Path) -> dict[str, str]:
    path = match / "spoken.json"
    return json.loads(path.read_text()) if path.exists() else {}


def spelled(text: str, spoken: dict[str, str]) -> str:
    """`text` spelled for the voice: the names as `spoken` says, then "ace", "km/h" and the figures in words."""
    for word, sound in spoken.items():
        text = text.replace(word, sound)
    for pattern, sound in SAID:
        text = pattern.sub(sound, text)
    return FIGURES.sub(lambda m: number(int(m.group())), text)


def clip_name(text: str) -> str:
    """The audio file of a text as the voice reads it."""
    return hashlib.sha256(text.encode()).hexdigest()[:16] + ".mp3"


def placed(lines: list[dict], durations: dict[str, float], spoken: dict[str, str], walls: tuple[float, ...] = ()) -> list[tuple[dict, str, str, float]]:
    """The lines to say, by time, each with its text, file and seconds, the most telling first in the running (`RANKS`): each
    in full where it fits between those already there, else in `short`, else not at all. A strong line is always said; a `late`
    one, a rally's end, waits for what is being said. None runs over one of the `walls` (the hosted video's cuts: `timeline`),
    strong or not."""
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
            if start + seconds > line.get("until", float("inf")) or any(start < wall < start + seconds for wall in walls):
                continue
            if line["strong"] or all(start + seconds <= begin or start >= stop for begin, stop in taken):
                out.append(({**line, "t": start}, text, clip, durations[clip]))
                taken.append((start, start + seconds))
                break
    return sorted(out, key=lambda item: item[0]["t"])


def fitted(lines: list[dict], durations: dict[str, float], spoken: dict[str, str], walls: tuple[float, ...] = ()) -> list[list]:
    """The lines to say as flat [t, file, seconds, text as the page shows it]."""
    return [[round(line["t"], 2), clip, round(seconds, 2), text] for line, text, clip, seconds in placed(lines, durations, spoken, walls)]


def voice_index(match: Path, data: dict, walls: tuple[float, ...] = ()) -> dict | None:
    """What the page plays, from the audio in `match`/voice: `lines` and `replay`, a file by name; None without any. No
    line runs over one of the `walls` (`placed`)."""
    folder = match / "voice"
    if not (folder / "durations.json").exists():
        return None
    durations = json.loads((folder / "durations.json").read_text())
    spoken = read_spoken(match)
    lines = fitted(script(data), durations, spoken, walls)
    if not lines:
        return None
    replay = {n: clip_name(spelled(text, spoken)) for n, text in replay_lines(data).items()}
    return {"lines": lines, "replay": {n: clip for n, clip in replay.items() if clip in durations}, "folder": folder}
