import type { Contact, Group, Person } from '@/lib/match';

/** What the table counts, each the touches it holds. */
export const STATS = [
  'touches',
  'serves',
  'aces',
  'serveFaults',
  'receptions',
  'missed',
  'unattacked',
  'attacks',
  'kills',
  'attackFaults',
  'blocks',
  'digs',
  'digFaults',
  'unattackedDigs',
  'sets',
  'points',
  'faults',
] as const;
export type Stat = (typeof STATS)[number];
export type Stats = Record<Stat, Contact[]>;

/** A row of the table: a player (`person` their key), the touches of no identified player (`rest`)
 * or the whole team (`total`). */
export interface Line {
  id: number | 'rest' | 'total';
  stats: Stats;
}

// Floor and net contacts are the ball's, not a player's.
const TOUCHES = new Set(['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig']);

/** Whether a reception's or a dig's team did not attack after it: it sent the ball back or the
 * rally ended before any attack of its team. Unknown, so false, for a fault or without a next touch
 * in the rally. */
export function unattacked(c: Contact, after: Contact[]): boolean {
  const next = after.filter((n) => n.rally === c.rally);
  if ((c.type !== 'pass' && c.type !== 'dig') || c.result !== 'play' || !next.length) {
    return false;
  }
  const crossed = next.findIndex((n) => n.side !== c.side);
  return !next.slice(0, crossed < 0 ? undefined : crossed).some((n) => n.type === 'attack');
}

/** The stats of the touches `mine` holds; `missedAce` holds the aces counted against them, as
 * receptions and faults. */
export function stats(contacts: Contact[], mine: (c: Contact) => boolean, missedAce: (c: Contact) => boolean): Stats {
  const out = Object.fromEntries(STATS.map((s) => [s, [] as Contact[]])) as Stats;
  for (const [k, c] of contacts.entries()) {
    const ace = c.type === 'serve' && c.result === 'point';
    if (ace && missedAce(c)) {
      out.receptions.push(c);
      out.missed.push(c);
      out.faults.push(c);
    }
    if (!TOUCHES.has(c.type) || !mine(c)) {
      continue;
    }
    out.touches.push(c);
    const add = (stat: Stat, point: Stat | null, fault: Stat | null) => {
      out[stat].push(c);
      if (point && c.result === 'point') {
        out[point].push(c);
      }
      if (fault && c.result === 'error') {
        out[fault].push(c);
      }
    };
    if (c.type === 'serve') {
      add('serves', 'aces', 'serveFaults');
    } else if (c.type === 'pass') {
      add('receptions', null, 'missed');
      // A rally holds a handful of touches.
      if (unattacked(c, contacts.slice(k + 1, k + 8))) {
        out.unattacked.push(c);
      }
    } else if (c.type === 'attack') {
      add('attacks', 'kills', 'attackFaults');
    } else if (c.type === 'block') {
      add('blocks', null, null);
    } else if (c.type === 'dig') {
      add('digs', null, 'digFaults');
      if (unattacked(c, contacts.slice(k + 1, k + 8))) {
        out.unattackedDigs.push(c);
      }
    } else if (c.type === 'set') {
      add('sets', null, null);
    }
    if (c.result === 'point') {
      out.points.push(c);
    } else if (c.result === 'error') {
      out.faults.push(c);
    }
  }
  return out;
}

/** The table of team `g`: its identified players who touched the ball or missed an ace, most touches
 * first, then the touches of no identified player and the whole team. A touch is a player's when
 * they play for the touch's team: a track swapping players across the net can lend it the other's. */
export function lines(contacts: Contact[], people: Record<string, Person>, g: Group): Line[] {
  const owner = (person: number | null | undefined, team: Group) => (person != null && people[person]?.number != null && people[person].team === team ? person : null);
  const players = Object.keys(people)
    .map(Number)
    .filter((p) => people[p].team === g && people[p].number !== null)
    .map((p) => ({
      id: p,
      stats: stats(
        contacts,
        (c) => c.g === g && owner(c.person, g) === p,
        (c) => owner(c.receiver, g) === p,
      ),
    }))
    .filter((line) => line.stats.touches.length || line.stats.missed.length)
    .sort((a, b) => b.stats.touches.length - a.stats.touches.length);
  const rest = stats(
    contacts,
    (c) => c.g === g && owner(c.person, g) === null,
    (c) => c.g !== g && owner(c.receiver, g) === null,
  );
  const total = stats(
    contacts,
    (c) => c.g === g,
    (c) => c.g !== g,
  );
  return [...players, ...(rest.touches.length || rest.missed.length ? [{ id: 'rest' as const, stats: rest }] : []), { id: 'total', stats: total }];
}
