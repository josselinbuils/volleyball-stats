import type { Contact, Group, Person } from '@/lib/match';
import { playerKey } from '@/helpers/players';

// A player's usual way to their spot from this many attacks in one kind of spot, told from this many metres.
const FROM = 8;
export const OFF_M = 1;

/** The kinds of perimeter spot (`defense.py`): a front player not blocking, zone 1 or 5, zone 6. */
export const SPOTS = ['front', 'corner', 'deep'] as const;
export type Spot = (typeof SPOTS)[number];

/** A player's cue: their usual way to their `spot`, in metres `back` from the net and `out` toward its sideline, and
 * the attacks they stood OFF_M or more from it. */
export interface Placement {
  person: number;
  spot: Spot;
  back: number;
  out: number;
  off: Contact[];
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** `g`'s players' cues, the longest way first: each player's in the kind of spot where their usual way, from FROM
 * attacks, is the longest, if OFF_M or more. */
export function placements(contacts: Contact[], g: Group, people: Record<string, Person>): Placement[] {
  const found = new Map<string, { person: number; spot: number; gaps: { c: Contact; back: number; out: number }[] }>();
  for (const c of contacts) {
    if (c.type !== 'attack' || c.g === g || !c.defense) {
      continue;
    }
    for (let k = 0; k < c.defense.length; k += 4) {
      const [person, spot, back, out] = c.defense.slice(k, k + 4);
      const key = playerKey(person, people);
      if (key === null || people[person].team !== g) {
        continue;
      }
      const at = found.get(`${key}|${spot}`) ?? { person, spot, gaps: [] };
      at.gaps.push({ c, back, out });
      found.set(`${key}|${spot}`, at);
    }
  }
  const best = new Map<string, Placement & { size: number }>();
  for (const { person, spot, gaps } of found.values()) {
    const [back, out] = [median(gaps.map((x) => x.back)), median(gaps.map((x) => x.out))];
    const size = Math.max(Math.abs(back), Math.abs(out));
    const key = playerKey(person, people) as string;
    if (gaps.length >= FROM && size >= OFF_M && size > (best.get(key)?.size ?? 0)) {
      const off = gaps.filter((x) => Math.hypot(x.back, x.out) >= OFF_M).map((x) => x.c);
      best.set(key, { person, spot: SPOTS[spot], back, out, off, size });
    }
  }
  return [...best.values()].sort((a, b) => b.size - a.size).map(({ size: _, ...p }) => p);
}
