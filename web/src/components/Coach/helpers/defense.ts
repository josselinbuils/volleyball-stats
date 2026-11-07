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

/** At the net, off it in front, or in the back row. */
export type Role = 'block' | 'off' | 'back';

/** A role at a position: the player's usual place and their spot there, [metres from the net, metres to their right]. */
export interface Place {
  role: Role;
  usual: [number, number];
  spot: [number, number];
}

/** A situation a player defended: their position, the side the attack came from, how many blocked, their role, their
 * usual place from FROM attacks and their spot, every position's spot against the side's attacker (`match.defense`),
 * those attacks, those whose ball came down nearer their spot than any other (theirs to play), and those they stood OFF_M
 * or more from their spot. */
export interface Situation {
  position: number;
  side: Side;
  block: number;
  place: Place;
  spots: { position: number; spot: [number, number] }[];
  attacks: Contact[];
  mine: Contact[];
  off: Contact[];
}

export interface Defender {
  key: string;
  person: number;
  situations: Situation[];
}

export function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function role(position: number, depth: number): Role {
  return depth <= 1 ? 'block' : position >= 2 && position <= 4 ? 'off' : 'back';
}

/** Where `c`, an attack with its flight, comes from. */
export function sideOf(c: Contact): Side {
  const across = c.flight?.[1] ?? 0;
  return across < -MIDDLE_M ? 'left' : across > MIDDLE_M ? 'right' : 'middle';
}

/** The other team's attacks on `g` with their defenders' places. */
export const attacksOn = (contacts: Contact[], g: Group) => contacts.filter((c) => c.type === 'attack' && c.g !== g && c.defense && c.flight);

/** Every position's spot in the `mode`th system against the attacker on `side`, under `block` blockers. */
function spotsOf(mode: number, side: Side, block: number): { position: number; spot: [number, number] }[] {
  const flat = match.defense?.spots[match.defense.modes[mode]]?.[side]?.[String(block)] ?? [];
  return POSITIONS.map((position, k) => ({ position, spot: [flat[2 * k], flat[2 * k + 1]] as [number, number] }));
}

/** `g`'s players at the other team's attacks in the `mode`th of `match.defense`'s systems, each with the situations they
 * defended: by position in court order, then side and block. */
export function defenders(contacts: Contact[], g: Group, people: Record<string, Person>, mode: number): Defender[] {
  const found = new Map<string, { person: number; at: Map<string, { c: Contact; place: number[] }[]> }>();
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
    const situations = POSITIONS.flatMap((position) =>
      SIDES.flatMap((side) =>
        [1, 2].flatMap((block): Situation[] => {
          const seen = at.get(`${position} ${side} ${block}`) ?? [];
          if (seen.length < FROM) {
            return [];
          }
          const spots = spotsOf(mode, side, block);
          const spot = (spots.find((s) => s.position === position) as { spot: [number, number] }).spot;
          // A ball is theirs when it came down nearer their spot than any other.
          const mine = seen
            .map((x) => x.c)
            .filter((c) => {
              const f = c.flight as number[];
              const far = (s: { spot: [number, number] }) => Math.hypot(s.spot[0] - f[2], s.spot[1] - f[3]);
              return f.length === 4 && spots.reduce((a, b) => (far(b) < far(a) ? b : a)).position === position;
            });
          const off = seen.filter((x) => Math.hypot(spot[0] - x.place[0], spot[1] - x.place[1]) >= OFF_M).map((x) => x.c);
          const usual: [number, number] = [median(seen.map((x) => x.place[0])), median(seen.map((x) => x.place[1]))];
          return [{ position, side, block, place: { role: role(position, spot[0]), usual, spot }, spots, attacks: seen.map((x) => x.c), mine, off }];
        }),
      ),
    );
    return situations.length ? [{ key, person, situations }] : [];
  });
}
