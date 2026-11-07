import { match, type Contact, type Group, type Person } from '@/lib/match';
import { playerKey } from '@/helpers/players';

// A usual place from this many attacks at a position in one role, a way told from this many metres.
const FROM = 4;
export const OFF_M = 1;
// An attack this near the court's long axis comes through the middle (`defense.MIDDLE_M`).
const MIDDLE_M = 1.5;

/** The positions in court order: the front row left to right, then the back row. */
export const POSITIONS = [4, 3, 2, 5, 6, 1] as const;
/** Where an attack comes from, as the defenders see it facing the net. */
export const SIDES = ['left', 'middle', 'right'] as const;
export type Side = (typeof SIDES)[number];

/** At the net, off it in front (2 and 4), covering the tip behind a single block (3), or in the back row. */
export type Role = 'block' | 'off' | 'tip' | 'back';

/** A role at a position: the player's usual place and their spot there, [metres from the net, metres to their right]. */
export interface Place {
  role: Role;
  usual: [number, number];
  spot: [number, number];
}

/** A position a player defended against attacks from one side: their places in each role from FROM attacks, those
 * attacks, and those they stood OFF_M or more from their spot. */
export interface Situation {
  side: Side;
  places: Place[];
  attacks: Contact[];
  off: Contact[];
}

/** A position a player defended, against attacks from each side where they have a place. */
export interface Position {
  position: number;
  situations: Situation[];
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

/** Where `c`, an attack with its flight, comes from. */
export function sideOf(c: Contact): Side {
  const across = c.flight?.[1] ?? 0;
  return across < -MIDDLE_M ? 'left' : across > MIDDLE_M ? 'right' : 'middle';
}

/** The other team's attacks on `g` with their defenders' places. */
export const attacksOn = (contacts: Contact[], g: Group) => contacts.filter((c) => c.type === 'attack' && c.g !== g && c.defense && c.flight);

/** `g`'s players at the other team's attacks in the `mode`th of `match.defenseModes`, each with the positions they
 * defended in court order. */
export function defenders(contacts: Contact[], g: Group, people: Record<string, Person>, mode: number): Defender[] {
  const stride = 3 + 3 * match.defenseModes.length;
  const found = new Map<string, { person: number; at: Map<string, { c: Contact; place: number[] }[]> }>();
  for (const c of attacksOn(contacts, g)) {
    const all = c.defense as number[];
    for (let k = 0; k < all.length; k += stride) {
      const [person, depth, across] = all.slice(k, k + 3);
      const [position, spotDepth, spotAcross] = all.slice(k + 3 + 3 * mode, k + 6 + 3 * mode);
      const key = playerKey(person, people);
      if (key === null || people[person].team !== g || !position) {
        continue;
      }
      const player = found.get(key) ?? { person, at: new Map() };
      const at = `${position} ${sideOf(c)}`;
      player.at.set(at, [...(player.at.get(at) ?? []), { c, place: [depth, across, spotDepth, spotAcross] }]);
      found.set(key, player);
    }
  }
  return [...found].flatMap(([key, { person, at }]) => {
    const positions = POSITIONS.flatMap((position) => {
      const situations = SIDES.flatMap((side) => {
        const seen = at.get(`${position} ${side}`) ?? [];
        const places = (['block', 'off', 'tip', 'back'] as const).flatMap((r) => {
          const here = seen.filter((x) => role(position, x.place[2]) === r).map((x) => x.place);
          const mid = (n: number) => median(here.map((p) => p[n]));
          return here.length >= FROM ? [{ role: r, usual: [mid(0), mid(1)], spot: [mid(2), mid(3)] } as Place] : [];
        });
        const off = seen.filter((x) => Math.hypot(x.place[2] - x.place[0], x.place[3] - x.place[1]) >= OFF_M).map((x) => x.c);
        return places.length ? [{ side, places, attacks: seen.map((x) => x.c), off }] : [];
      });
      return situations.length ? [{ position, situations }] : [];
    });
    return positions.length ? [{ key, person, positions }] : [];
  });
}
