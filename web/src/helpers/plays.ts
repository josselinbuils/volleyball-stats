import type { Contact, Group, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';

/** Each attack right after a set of its team in the rally, with that set. */
export function setAttacks(contacts: Contact[]): { set: Contact; attack: Contact }[] {
  return contacts.flatMap((attack, k) => {
    const set = contacts[k - 1];
    return attack.type === 'attack' && set?.type === 'set' && set.rally === attack.rally && set.g === attack.g && attack.person !== null && set.person !== null ? [{ set, attack }] : [];
  });
}

/** A partner of a player: the player's attacks on their sets, their attacks on the player's. */
export interface Duo {
  person: number;
  fromThem: Contact[];
  fromMe: Contact[];
}

/** The players `key` attacked after or set for, most attacks first. */
export function duos(contacts: Contact[], key: string, people: Record<string, Person>): Duo[] {
  const found = new Map<string, Duo>();
  for (const { set, attack } of setAttacks(contacts)) {
    const [attacker, setter] = [playerKey(attack.person, people), playerKey(set.person, people)];
    if (attacker === setter || (attacker !== key && setter !== key)) {
      continue;
    }
    const partner = (attacker === key ? set.person : attack.person) as number;
    const name = playerKey(partner, people);
    if (name !== null) {
      const duo = found.get(name) ?? { person: partner, fromThem: [], fromMe: [] };
      (attacker === key ? duo.fromThem : duo.fromMe).push(attack);
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

export const teamFirst = (score: [number, number], team: Group): [number, number] => (team === 1 ? score : [score[1], score[0]]);

/** The score before each rally of `rallies`, set by set. */
export function scoresBefore(rallies: Rally[]): Map<number, [number, number]> {
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
      from = teamFirst(before.get(r.i) as [number, number], serve.g);
    }
    going = [...going, r.i];
    if (going.length >= 2 && going.length > (best?.rallies.length ?? 0)) {
      best = { rallies: going, from, to: teamFirst(r.score, serve.g) };
    }
  }
  return best;
}

/** The longest of `rallies` in touches, then seconds, with a score; undefined without one. */
export function longestRally(rallies: Rally[]): Rally | undefined {
  const touches = (r: Rally) => r.contacts.filter(isTouch).length;
  return rallies.filter((r) => r.score && touches(r) > 0).sort((a, b) => touches(b) - touches(a) || b.end - b.start - (a.end - a.start))[0];
}
