import type { Contact, Person } from '@/lib/match';
import type { Players } from '@/lib/players';
import { playersAt } from '@/helpers/players';

// A teammate this near where the ball lands could have played it.
const REACH_M = 2.5;
// The nearer of two teammates at least this share of the other's distance: neither was clearly
// the one to play it.
const EVEN = 0.6;

/** A ball that landed untouched between two teammates (`pair`, keys in `match.people`). */
export interface Drop {
  landing: Contact;
  pair: [number, number];
}

/** The balls that landed in untouched, the two teammates nearest to where they landed both within
 * REACH_M and about as near: the nearer at least EVEN of the other's distance. */
export function drops(contacts: Contact[], players: Players, fps: number, people: Record<string, Person>): Drop[] {
  const out: Drop[] = [];
  for (const [k, c] of contacts.entries()) {
    // A point of the touch before is the ball landing in, on the other side of the net.
    const before = contacts[k - 1];
    if (c.type !== 'floor' || c.x === null || c.y === null || before?.rally !== c.rally || before.result !== 'point') {
      continue;
    }
    const { x, y } = c;
    const near = playersAt(players, fps, c.t)
      .filter((p) => people[p.person]?.team === c.g && Math.sign(p.x) === Math.sign(x))
      .map((p) => ({ person: p.person, d: Math.hypot(p.x - x, p.y - y) }))
      .sort((a, b) => a.d - b.d);
    if (near.length >= 2 && near[1].d <= REACH_M && near[0].d >= EVEN * near[1].d) {
      out.push({ landing: c, pair: [near[0].person, near[1].person] });
    }
  }
  return out;
}
