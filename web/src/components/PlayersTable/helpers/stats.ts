import type { Contact, Group, Person } from '@/lib/match';

/** What the table counts, each the touches it holds. */
export const STATS = ['touches', 'serves', 'aces', 'serveFaults', 'receptions', 'missed', 'attacks', 'kills', 'attackFaults', 'blocks', 'blockPoints', 'digs', 'sets', 'points', 'faults'] as const;
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

/** The stats of the touches `mine` holds; `missedAce` holds the aces counted against them. */
export function stats(contacts: Contact[], mine: (c: Contact) => boolean, missedAce: (c: Contact) => boolean): Stats {
  const out = Object.fromEntries(STATS.map((s) => [s, [] as Contact[]])) as Stats;
  for (const c of contacts) {
    const ace = c.type === 'serve' && c.result === 'point';
    if (ace && missedAce(c)) {
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
    } else if (c.type === 'attack') {
      add('attacks', 'kills', 'attackFaults');
    } else if (c.type === 'block') {
      add('blocks', 'blockPoints', null);
    } else if (c.type === 'dig') {
      add('digs', null, null);
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
