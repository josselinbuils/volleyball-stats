import type { Contact, Group, Person } from '@/lib/match';
import { playerKey } from '@/helpers/players';

// A usual place from this many attacks at a position in one role, a way told from this many metres.
const FROM = 5;
export const OFF_M = 1;

/** The positions in court order: the front row left to right, then the back row. */
export const POSITIONS = [4, 3, 2, 5, 6, 1] as const;

/** At the net, off it in front (2 and 4), covering the tip behind a single block (3), or in the back row. */
export type Role = 'block' | 'off' | 'tip' | 'back';

/** A role at a position: the player's usual place and their spot there, [metres from the net, metres to their right]. */
export interface Place {
  role: Role;
  usual: [number, number];
  spot: [number, number];
}

/** A position a player defended: their places in each role from FROM attacks, and the attacks they stood OFF_M or
 * more from their spot. */
export interface Position {
  position: number;
  places: Place[];
  off: Contact[];
}

export interface Defender {
  key: string;
  person: number;
  positions: Position[];
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function role(position: number, depth: number): Role {
  return depth <= 1 ? 'block' : position === 3 ? 'tip' : position === 2 || position === 4 ? 'off' : 'back';
}

/** `g`'s players at the other team's attacks, each with the positions they defended in court order. */
export function defenders(contacts: Contact[], g: Group, people: Record<string, Person>): Defender[] {
  const found = new Map<string, { person: number; at: Map<number, { c: Contact; place: number[] }[]> }>();
  for (const c of contacts) {
    if (c.type !== 'attack' || c.g === g || !c.defense) {
      continue;
    }
    for (let k = 0; k < c.defense.length; k += 6) {
      const place = c.defense.slice(k, k + 6);
      const key = playerKey(place[0], people);
      if (key === null || people[place[0]].team !== g) {
        continue;
      }
      const player = found.get(key) ?? { person: place[0], at: new Map() };
      player.at.set(place[1], [...(player.at.get(place[1]) ?? []), { c, place }]);
      found.set(key, player);
    }
  }
  return [...found].flatMap(([key, { person, at }]) => {
    const positions = POSITIONS.flatMap((position) => {
      const seen = at.get(position) ?? [];
      const places = (['block', 'off', 'tip', 'back'] as const).flatMap((r) => {
        const here = seen.filter((x) => role(position, x.place[4]) === r).map((x) => x.place);
        const mid = (n: number) => median(here.map((p) => p[n]));
        return here.length >= FROM ? [{ role: r, usual: [mid(2), mid(3)], spot: [mid(4), mid(5)] } as Place] : [];
      });
      const off = seen.filter((x) => Math.hypot(x.place[4] - x.place[2], x.place[5] - x.place[3]) >= OFF_M).map((x) => x.c);
      return places.length ? [{ position, places, off }] : [];
    });
    return positions.length ? [{ key, person, positions }] : [];
  });
}
