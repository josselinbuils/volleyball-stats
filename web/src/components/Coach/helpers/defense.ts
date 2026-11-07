import { match, type Contact, type Group, type Person } from '@/lib/match';
import { playerKey } from '@/helpers/players';

// A usual place from this many attacks at a position against one side and block; a place this far off its spot is off.
const FROM = 4;
const OFF_M = 1;
// An attack this near the court's long axis comes through the middle (`defense.MIDDLE_M`).
const MIDDLE_M = 1.5;

/** The positions in court order: the front row left to right, then the back row. */
export const POSITIONS = [4, 3, 2, 5, 6, 1] as const;
/** Where an attack comes from, as the defenders see it facing the net. */
export const SIDES = ['left', 'middle', 'right'] as const;
export type Side = (typeof SIDES)[number];
/** One blocker or two. */
export const BLOCKS = [1, 2] as const;

/** A spot, [metres from the net, metres to the defenders' right]. */
export type Spot = [number, number];

/** Where a player defended a position against one side and block: their usual place from FROM attacks, and the attacks
 * they stood OFF_M or more from the position's spot in the system. */
export interface Played {
  position: number;
  side: Side;
  block: number;
  usual: Spot;
  off: Contact[];
}

export interface Defender {
  key: string;
  person: number;
  played: Played[];
}

export function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Where `c`, an attack, was hit from. */
export function sideOf(c: Contact): Side {
  const across = c.hit?.[1] ?? 0;
  return across < -MIDDLE_M ? 'left' : across > MIDDLE_M ? 'right' : 'middle';
}

/** The other team's attacks on `g` with their defenders' places. */
export const attacksOn = (contacts: Contact[], g: Group) => contacts.filter((c) => c.type === 'attack' && c.g !== g && c.defense && c.hit);

/** Every position's spot in the `mode`th system against the attacker on `side`, under `block` blockers (`match.defense`). */
export function spotsOf(mode: number, side: Side, block: number): { position: number; spot: Spot }[] {
  const flat = match.defense?.spots[match.defense.modes[mode]]?.[side]?.[String(block)] ?? [];
  return POSITIONS.map((position, k) => ({ position, spot: [flat[2 * k], flat[2 * k + 1]] }));
}

/** `g`'s players at the other team's attacks, each with where they defended, in the `mode`th system: by position in
 * court order, then side and block. */
export function defenders(contacts: Contact[], g: Group, people: Record<string, Person>, mode: number): Defender[] {
  const found = new Map<string, { person: number; at: Map<string, { c: Contact; place: Spot }[]> }>();
  for (const c of attacksOn(contacts, g)) {
    const all = c.defense as number[];
    for (let k = 0; k < all.length; k += 4) {
      const [person, depth, across, position] = all.slice(k, k + 4);
      const key = playerKey(person, people);
      if (key === null || people[person].team !== g) {
        continue;
      }
      const player = found.get(key) ?? { person, at: new Map() };
      const at = `${position} ${sideOf(c)} ${c.block === 2 ? 2 : 1}`;
      player.at.set(at, [...(player.at.get(at) ?? []), { c, place: [depth, across] }]);
      found.set(key, player);
    }
  }
  return [...found].flatMap(([key, { person, at }]) => {
    const played = POSITIONS.flatMap((position) =>
      SIDES.flatMap((side) =>
        BLOCKS.flatMap((block): Played[] => {
          const seen = at.get(`${position} ${side} ${block}`) ?? [];
          if (seen.length < FROM) {
            return [];
          }
          const spot = (spotsOf(mode, side, block).find((s) => s.position === position) as { spot: Spot }).spot;
          const off = seen.filter((x) => Math.hypot(spot[0] - x.place[0], spot[1] - x.place[1]) >= OFF_M).map((x) => x.c);
          return [{ position, side, block, usual: [median(seen.map((x) => x.place[0])), median(seen.map((x) => x.place[1]))], off }];
        }),
      ),
    );
    return played.length ? [{ key, person, played }] : [];
  });
}
