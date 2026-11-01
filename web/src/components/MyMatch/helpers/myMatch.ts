import type { Contact, Group, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';

// A point in a rally this long is a moment.
const LONG_RALLY = 7;
// From this many points a tie is a late one.
const LATE = 20;
// A team's best count of a stat is told from this many.
const TOP_FROM = 3;

/** A partner of a player: the player's attacks on their sets, their attacks on the player's. */
export interface Duo {
  person: number;
  fromThem: Contact[];
  fromMe: Contact[];
}

/** The players `key` attacked after or set for, most attacks first. An attack's setter is its
 * rally's touch right before it when a set of the same team. */
export function duos(contacts: Contact[], key: string, people: Record<string, Person>): Duo[] {
  const found = new Map<string, Duo>();
  for (const [k, c] of contacts.entries()) {
    const set = contacts[k - 1];
    if (c.type !== 'attack' || set?.type !== 'set' || set.rally !== c.rally || set.g !== c.g || c.person === null || set.person === null) {
      continue;
    }
    const [attacker, setter] = [playerKey(c.person, people), playerKey(set.person, people)];
    if (attacker === setter || (attacker !== key && setter !== key)) {
      continue;
    }
    const partner = attacker === key ? set.person : c.person;
    const name = playerKey(partner, people);
    if (name !== null) {
      const duo = found.get(name) ?? { person: partner, fromThem: [], fromMe: [] };
      (attacker === key ? duo.fromThem : duo.fromMe).push(c);
      found.set(name, duo);
    }
  }
  return [...found.values()].sort((a, b) => b.fromThem.length + b.fromMe.length - (a.fromThem.length + a.fromMe.length));
}

/** Points in a row at `key`'s serve: `rallies` their indexes, the scores theirs first. */
export interface ServeRun {
  rallies: number[];
  from: [number, number];
  to: [number, number];
}

const first = (score: [number, number], team: Group): [number, number] => (team === 1 ? score : [score[1], score[0]]);

/** The score before each rally of `rallies`, set by set. */
function scoresBefore(rallies: Rally[]): Map<number, [number, number]> {
  const out = new Map<number, [number, number]>();
  let set: number | null = null;
  let before: [number, number] = [0, 0];
  for (const r of rallies) {
    if (r.set !== set) {
      set = r.set;
      before = [0, 0];
    }
    out.set(r.i, before);
    before = r.score ?? before;
  }
  return out;
}

/** `key`'s longest run of points on their serve, 2 or more, null without one. A rally to replay
 * neither counts nor ends it. */
export function serveRun(rallies: Rally[], key: string, people: Record<string, Person>): ServeRun | null {
  const before = scoresBefore(rallies);
  let best: ServeRun | null = null;
  let going: number[] = [];
  let from: [number, number] = [0, 0];
  for (const r of rallies) {
    if (r.redo) {
      continue;
    }
    const serve = r.contacts.find((c) => c.type === 'serve');
    if (!serve || playerKey(serve.person, people) !== key || r.winner !== serve.g || !r.score) {
      going = [];
      continue;
    }
    if (!going.length) {
      from = first(before.get(r.i) as [number, number], serve.g);
    }
    going = [...going, r.i];
    if (going.length >= 2 && going.length > (best?.rallies.length ?? 0)) {
      best = { rallies: going, from, to: first(r.score, serve.g) };
    }
  }
  return best;
}

/** A point of `key`'s worth retelling, `score` after it theirs first. */
export interface Highlight {
  kind: 'setWon' | 'longRally' | 'lateTie' | 'ace' | 'block';
  contact: Contact;
  score: [number, number];
  touches: number;
}

const KINDS: Highlight['kind'][] = ['setWon', 'longRally', 'lateTie', 'ace', 'block'];

/** `key`'s best points, at most `most`: winning a set, ending a long rally, breaking or making a late
 * tie, then aces and blocks, in that order, each of the same kind by time. */
export function highlights(rallies: Rally[], key: string, people: Record<string, Person>, most = 4): Highlight[] {
  const before = scoresBefore(rallies);
  const out: Highlight[] = [];
  for (const [k, r] of rallies.entries()) {
    const c = r.contacts.filter(isTouch).at(-1);
    if (!c || c.result !== 'point' || r.winner !== c.g || !r.score || playerKey(c.person, people) !== key) {
      continue;
    }
    const was = before.get(r.i) as [number, number];
    const touches = r.contacts.filter(isTouch).length;
    const score = first(r.score, c.g);
    const late = Math.max(...r.score) >= LATE && Math.abs(r.score[0] - r.score[1]) <= 1 && Math.abs(was[0] - was[1]) <= 1;
    const kind: Highlight['kind'] | null =
      rallies[k + 1]?.set !== r.set && score[0] > score[1] ? 'setWon' : touches >= LONG_RALLY ? 'longRally' : late ? 'lateTie' : c.type === 'serve' ? 'ace' : c.type === 'block' ? 'block' : null;
    if (kind) {
      out.push({ kind, contact: c, score, touches });
    }
  }
  return out.sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind) || a.contact.t - b.contact.t).slice(0, most);
}

/** The stats where `mine` holds the team's most, from TOP_FROM, largest first, `others` the counts
 * of the rest of the team by stat. */
export function tops<S extends string>(mine: Record<S, Contact[]>, others: Record<S, Contact[]>[], names: readonly S[]): S[] {
  return names.filter((stat) => mine[stat].length >= TOP_FROM && others.every((o) => o[stat].length <= mine[stat].length)).sort((a, b) => mine[b].length - mine[a].length);
}
