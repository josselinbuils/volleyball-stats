import type { Contact, Group, Person } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';
import type { Drop } from '@/components/Stats/helpers/between';

/** What the table counts, each the touches it holds. */
export const STATS = [
  'touches',
  'serves',
  'aces',
  'serveFaults',
  'receptions',
  'missed',
  'unattacked',
  'rated',
  'perfect',
  'good',
  'poor',
  'attacks',
  'kills',
  'attackFaults',
  'relances',
  'relanceFaults',
  'blocks',
  'digs',
  'digFaults',
  'unattackedDigs',
  'sets',
  'points',
  'faults',
  'between',
] as const;
export type Stat = (typeof STATS)[number];
export type Stats = Record<Stat, Contact[]>;

/** A row of the table: a player (`id` the key in `match.people` of their identity with the most
 * touches), the touches of no identified player (`rest`) or the whole team (`total`). */
export interface Line {
  id: number | 'rest' | 'total';
  stats: Stats;
}

// The setter's target on the left half, 1 m off the net between zones 2 and 3; the right half's is
// its mirror.
const TARGET = { x: -1, y: 1.5 };
// A reception's next touch this near the target makes a perfect pass (3), this near a good one (2).
const PERFECT_M = 1.5;
const GOOD_M = 3;
// A next touch sooner than this after a reception is most often the reception seen twice.
const FLIGHT_S = 1;
// The stats of the grades 1 to 3; a 0 is a fault, in `missed`.
const GRADES = ['poor', 'good', 'perfect'] as const;

/** A reception's grade from where its team plays the next touch: 3 within PERFECT_M of the setter's
 * target, 2 within GOOD_M, 1 further or straight over the net, 0 for a fault. Null without a placed
 * next touch in the rally FLIGHT_S or more after it. */
export function rating(c: Contact, next: Contact | undefined): number | null {
  if (c.result === 'error') {
    return 0;
  }
  if (!next || next.rally !== c.rally || next.t - c.t < FLIGHT_S) {
    return null;
  }
  if (next.side !== c.side) {
    return 1;
  }
  if (next.x === null || next.y === null) {
    return null;
  }
  const mirror = c.side === 'left' ? 1 : -1;
  const d = Math.hypot(next.x - TARGET.x * mirror, next.y - TARGET.y * mirror);
  return d <= PERFECT_M ? 3 : d <= GOOD_M ? 2 : 1;
}

/** The mean grade of the rated receptions of `s`, null without any. */
export function meanRating(s: Stats): number | null {
  return s.rated.length ? (3 * s.perfect.length + 2 * s.good.length + s.poor.length) / s.rated.length : null;
}

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
      out.rated.push(c);
    }
    if (!isTouch(c) || !mine(c)) {
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
      const grade = rating(c, contacts[k + 1]);
      if (grade !== null) {
        out.rated.push(c);
        if (grade > 0) {
          out[GRADES[grade - 1]].push(c);
        }
      }
    } else if (c.type === 'attack') {
      add('attacks', 'kills', 'attackFaults');
    } else if (c.type === 'relance') {
      add('relances', null, 'relanceFaults');
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

// The MVP played at least this share of the longest time on the court of the players.
const MVP_SHARE = 0.5;

/** The best player of `found`'s (both teams' lines), `seconds` each one's time on the court: the
 * best balance of points won minus faults per minute played, among those on the court at least
 * MVP_SHARE of the longest time (the balance alone without times), then the most points, then the
 * most touches; null when no one's balance is above 0. */
export function mvp(found: Line[], seconds: (person: number) => number): number | null {
  const balance = (l: Line) => l.stats.points.length - l.stats.faults.length;
  const players = found.filter((l): l is Line & { id: number } => typeof l.id === 'number');
  const longest = Math.max(0, ...players.map((l) => seconds(l.id)));
  const rate = (l: Line & { id: number }) => (longest ? balance(l) / seconds(l.id) : balance(l));
  const kept = players.filter((l) => balance(l) > 0 && (!longest || seconds(l.id) >= MVP_SHARE * longest));
  kept.sort((a, b) => rate(b) - rate(a) || b.stats.points.length - a.stats.points.length || b.stats.touches.length - a.stats.touches.length);
  return kept[0]?.id ?? null;
}

/** The table of team `g`: its identified players who touched the ball or missed an ace, most touches
 * first, then the touches of no identified player and the whole team. A player is the identities
 * sharing their `playerKey`. A touch is a player's when they play for the touch's team: a track
 * swapping players across the net can lend it the other's. A ball of `dropped` counts for each of
 * its two players, once for the team. */
export function lines(contacts: Contact[], people: Record<string, Person>, g: Group, dropped: Drop[] = []): Line[] {
  const owner = (person: number | null | undefined, team: Group) => (person != null && people[person]?.team === team ? playerKey(person, people) : null);
  const between = (keep: (key: string | null) => boolean) => dropped.filter((d) => d.landing.g === g && d.pair.some((q) => keep(owner(q, g)))).map((d) => d.landing);
  const touched = (p: number) => contacts.filter((c) => c.g === g && c.person === p).length;
  const shown = new Map<string, number>();
  for (const p of Object.keys(people).map(Number)) {
    const key = owner(p, g);
    if (key !== null && (!shown.has(key) || touched(p) > touched(shown.get(key) as number))) {
      shown.set(key, p);
    }
  }
  const players = [...shown]
    .map(([key, p]) => ({
      id: p,
      stats: {
        ...stats(
          contacts,
          (c) => c.g === g && owner(c.person, g) === key,
          (c) => owner(c.receiver, g) === key,
        ),
        between: between((k) => k === key),
      },
    }))
    .filter((line) => line.stats.touches.length || line.stats.missed.length)
    .sort((a, b) => b.stats.touches.length - a.stats.touches.length);
  const rest = {
    ...stats(
      contacts,
      (c) => c.g === g && owner(c.person, g) === null,
      (c) => c.g !== g && c.receiver !== null && owner(c.receiver, g) === null,
    ),
    between: between((k) => k === null),
  };
  const total = {
    ...stats(
      contacts,
      (c) => c.g === g,
      (c) => c.g !== g,
    ),
    between: between(() => true),
  };
  return [...players, ...(rest.touches.length || rest.missed.length ? [{ id: 'rest' as const, stats: rest }] : []), { id: 'total', stats: total }];
}
