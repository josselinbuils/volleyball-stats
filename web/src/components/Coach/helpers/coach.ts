import type { Contact, Group, Lineup, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';
import { setAttacks } from '@/helpers/plays';
import { serveRating } from '@/components/Stats/helpers/stats';

// A thing to work on cost at least this many points.
const THING_FROM = 3;
const THINGS = 3;
// A setter from this many sets, a lineup from this many rallies: under them there is nothing to read.
const SETTER_FROM = 5;
const LINEUP_FROM = 3;
// A serve's grade from this one on caused trouble (`serveRating`): a poor reception, one lost, an ace.
const TROUBLE_FROM = 3;

export const CAUSES = ['serve', 'attack', 'defense', 'reception', 'set', 'relance', 'block', 'fault'] as const;
export type Cause = (typeof CAUSES)[number];

const OWN: Partial<Record<Contact['type'], Cause>> = { serve: 'serve', attack: 'attack', dig: 'defense', pass: 'reception', set: 'set', relance: 'relance', block: 'block', fault: 'fault' };
const THEIRS: Partial<Record<Contact['type'], Cause>> = { serve: 'reception', attack: 'defense', relance: 'defense', block: 'attack' };

/** Why `g` lost a rally, with the touch that lost it: its own last touch's fault, or the other team's last touch
 * scoring. Nothing for a rally they did not lose, one to replay, one the referee got wrong or one ending otherwise. */
export function lostOn(rally: Rally, g: Group): { cause: Cause; contact: Contact } | null {
  if (rally.redo || rally.wrongCall || !rally.winner || rally.winner === g) {
    return null;
  }
  const last = rally.contacts.filter((c) => isTouch(c) || c.type === 'fault').at(-1);
  const cause = !last ? undefined : last.g === g ? (last.result === 'error' ? OWN[last.type] : undefined) : last.result === 'point' ? THEIRS[last.type] : undefined;
  return cause && last ? { cause, contact: last } : null;
}

/** What cost `g` points: `n` the points, `other` what the same cost the other team. */
export interface Thing {
  cause: Cause;
  n: number;
  other: number;
  contacts: Contact[];
}

/** The rallies `g` lost, and the three causes that cost it the most from THING_FROM points: most points first,
 * then those costing the other team the least. */
export function things(rallies: Rally[], g: Group): { lost: number; found: Thing[] } {
  const count = (team: Group) => {
    const by = new Map<Cause, Contact[]>();
    for (const r of rallies) {
      const found = lostOn(r, team);
      if (found) {
        by.set(found.cause, [...(by.get(found.cause) ?? []), found.contact]);
      }
    }
    return by;
  };
  const [mine, theirs] = [count(g), count((3 - g) as Group)];
  const found = [...mine]
    .map(([cause, contacts]) => ({ cause, n: contacts.length, other: theirs.get(cause)?.length ?? 0, contacts }))
    .filter((x) => x.n >= THING_FROM)
    .sort((a, b) => b.n - a.n || a.other - b.other)
    .slice(0, THINGS);
  return { lost: rallies.filter((r) => !r.redo && r.winner && r.winner !== g).length, found };
}

export interface Attacker {
  person: number;
  attacks: Contact[];
}

/** A player setting for their team: `sets` their sets, `attackers` those attacking right after, most first. */
export interface Setter {
  person: number;
  sets: number;
  attackers: Attacker[];
}

/** `g`'s setters from SETTER_FROM sets, most sets first. A player's own attack after their set is left out. */
export function setters(contacts: Contact[], g: Group, people: Record<string, Person>): Setter[] {
  const found = new Map<string, Setter>();
  const setter = (c: Contact) => {
    const key = playerKey(c.person, people);
    if (key === null) {
      return null;
    }
    const out = found.get(key) ?? { person: c.person as number, sets: 0, attackers: [] };
    found.set(key, out);
    return out;
  };
  for (const c of contacts) {
    if (c.type === 'set' && c.g === g) {
      const out = setter(c);
      if (out) {
        out.sets += 1;
      }
    }
  }
  for (const { set, attack } of setAttacks(contacts)) {
    const [from, to] = [playerKey(set.person, people), playerKey(attack.person, people)];
    if (set.g !== g || from === null || to === null || from === to) {
      continue;
    }
    const out = setter(set) as Setter;
    const attacker = out.attackers.find((a) => playerKey(a.person, people) === to);
    if (attacker) {
      attacker.attacks.push(attack);
    } else {
      out.attackers.push({ person: attack.person as number, attacks: [attack] });
    }
  }
  return [...found.values()]
    .filter((s) => s.sets >= SETTER_FROM)
    .map((s) => ({ ...s, attackers: s.attackers.sort((a, b) => b.attacks.length - a.attacks.length) }))
    .sort((a, b) => b.sets - a.sets);
}

/** A six of `g` and the score while it played. */
export interface LineupScore {
  people: number[];
  sets: number[];
  won: number;
  lost: number;
}

/** Each six of `g` from LINEUP_FROM of `rallies` in play, first played first; the same six twice is one. */
export function lineupScores(lineups: Lineup[], rallies: Rally[], g: Group, people: Record<string, Person>): LineupScore[] {
  const found = new Map<string, LineupScore & { played: number }>();
  for (const lineup of lineups) {
    if (lineup.team !== g) {
      continue;
    }
    const key = lineup.people
      .map((p) => playerKey(p, people))
      .sort()
      .join('|');
    for (const r of rallies) {
      if (r.i < lineup.first || r.i > lineup.last || r.redo) {
        continue;
      }
      const out = found.get(key) ?? { people: lineup.people, sets: [], won: 0, lost: 0, played: 0 };
      found.set(key, out);
      out.played += 1;
      if (!out.sets.includes(r.set)) {
        out.sets.push(r.set);
      }
      out.won += r.winner === g ? 1 : 0;
      out.lost += r.winner && r.winner !== g ? 1 : 0;
    }
  }
  return [...found.values()].filter((x) => x.played >= LINEUP_FROM).map(({ played: _, ...x }) => x);
}

/** The serves reaching a zone, those causing trouble among them. */
export interface ZoneServes {
  all: Contact[];
  trouble: Contact[];
}

/** By zone, `g`'s serves in play, where they reach: the zone of the reception, or of the floor for one no one
 * touched. A serve left unrated or unplaced is in none. */
export function serveZones(contacts: Contact[], g: Group): Map<number, ZoneServes> {
  const out = new Map<number, ZoneServes>();
  for (const [k, c] of contacts.entries()) {
    const reached = contacts[k + 1];
    if (c.type !== 'serve' || c.g !== g || c.result === 'error' || reached?.rally !== c.rally || (reached.type !== 'pass' && reached.type !== 'floor') || reached.zone === null) {
      continue;
    }
    const grade = serveRating(c, reached, contacts[k + 2]);
    if (grade !== null) {
      const zone = out.get(reached.zone) ?? { all: [], trouble: [] };
      zone.all.push(c);
      if (grade >= TROUBLE_FROM) {
        zone.trouble.push(c);
      }
      out.set(reached.zone, zone);
    }
  }
  return out;
}
