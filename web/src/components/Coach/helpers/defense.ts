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
const ROLES: Role[] = ['block', 'off', 'back'];

/** A role at a position: the player's usual place and their spot there, [metres from the net, metres to their right]. */
export interface Place {
  role: Role;
  usual: [number, number];
  spot: [number, number];
}

/** A situation a player defended: their position, the side the attack came from, how many blocked, their role, their
 * usual place and spot from FROM attacks, every position's spot then, those attacks, those whose ball came down nearer
 * their spot than any other (theirs to play), and those they stood OFF_M or more from their spot. */
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

/** Whether the ball of `c`, attacked on `team` (each defender's [position, spot depth, spot across]), came down nearest
 * the spot of `position`. */
function theirs(c: Contact, team: number[][], position: number): boolean {
  const f = c.flight as number[];
  const spots = team.filter((s) => s[0]);
  if (f.length < 4 || !spots.length) {
    return false;
  }
  const far = (s: number[]) => Math.hypot(s[1] - f[2], s[2] - f[3]);
  return spots.reduce((a, b) => (far(b) < far(a) ? b : a))[0] === position;
}

export interface Defender {
  key: string;
  person: number;
  situations: Situation[];
}

function median(xs: number[]): number {
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

/** `g`'s players at the other team's attacks in the `mode`th of `match.defenseModes`, each with the situations they
 * defended: by position in court order, then side, block and role. */
export function defenders(contacts: Contact[], g: Group, people: Record<string, Person>, mode: number): Defender[] {
  const stride = 4 + 2 * match.defenseModes.length;
  const found = new Map<string, { person: number; at: Map<string, { c: Contact; place: number[]; team: number[][] }[]> }>();
  for (const c of attacksOn(contacts, g)) {
    const all = c.defense as number[];
    // Every position's spot at this attack.
    const team: number[][] = [];
    for (let k = 0; k < all.length; k += stride) {
      team.push([all[k + 3], ...all.slice(k + 4 + 2 * mode, k + 6 + 2 * mode)]);
    }
    for (let k = 0; k < all.length; k += stride) {
      const [person, depth, across, position] = all.slice(k, k + 4);
      const [spotDepth, spotAcross] = all.slice(k + 4 + 2 * mode, k + 6 + 2 * mode);
      const key = playerKey(person, people);
      if (key === null || people[person].team !== g) {
        continue;
      }
      const player = found.get(key) ?? { person, at: new Map() };
      const at = `${position} ${sideOf(c)} ${c.block === 2 ? 2 : 1} ${role(position, spotDepth)}`;
      player.at.set(at, [...(player.at.get(at) ?? []), { c, place: [depth, across, spotDepth, spotAcross], team }]);
      found.set(key, player);
    }
  }
  return [...found].flatMap(([key, { person, at }]) => {
    const situations = POSITIONS.flatMap((position) =>
      SIDES.flatMap((side) =>
        [1, 2].flatMap((block) =>
          ROLES.flatMap((r): Situation[] => {
            const seen = at.get(`${position} ${side} ${block} ${r}`) ?? [];
            if (seen.length < FROM) {
              return [];
            }
            const mid = (n: number) => median(seen.map((x) => x.place[n]));
            const spots = POSITIONS.flatMap((p) => {
              const here = seen.flatMap((x) => x.team.filter((s) => s[0] === p));
              return here.length ? [{ position: p, spot: [median(here.map((s) => s[1])), median(here.map((s) => s[2]))] as [number, number] }] : [];
            });
            const off = seen.filter((x) => Math.hypot(x.place[2] - x.place[0], x.place[3] - x.place[1]) >= OFF_M).map((x) => x.c);
            const mine = seen.filter((x) => theirs(x.c, x.team, position)).map((x) => x.c);
            return [{ position, side, block, place: { role: r, usual: [mid(0), mid(1)], spot: [mid(2), mid(3)] }, spots, attacks: seen.map((x) => x.c), mine, off }];
          }),
        ),
      ),
    );
    return situations.length ? [{ key, person, situations }] : [];
  });
}
