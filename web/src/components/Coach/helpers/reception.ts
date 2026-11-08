import type { Contact, Group, Person } from '@/lib/match';
import { median } from '@/helpers/median';
import { playerKey } from '@/helpers/players';
import { FROM, OFF_M, type Spot } from '@/components/Coach/helpers/defense';

/** The players a serve's reception reads: a whole team seen, else who stands at the net is unsure. */
const TEAM = 6;

/** A reception system: how many players stay at the net, the others receiving at `spots`. Three receivers, the middle
 * one as deep as the others in a line, 1 m deeper in an arc (the owner's team on 2 Nov, centred) and 2.5 m in a V; the
 * line 6 m off the net (two thirds back) in 3 m lanes, the textbook's. */
export interface Formation {
  net: number;
  spots: Spot[];
}

export const FORMATIONS = {
  line: {
    net: 3,
    spots: [
      [6, -3],
      [6, 0],
      [6, 3],
    ],
  },
  arc: {
    net: 3,
    spots: [
      [5.5, -2.5],
      [6.5, 0],
      [5.5, 2.5],
    ],
  },
  v: {
    net: 3,
    spots: [
      [5, -3],
      [7.5, 0],
      [5, 3],
    ],
  },
} satisfies Record<string, Formation>;
export type Mode = keyof typeof FORMATIONS;
export const MODES = Object.keys(FORMATIONS) as Mode[];

/** Where a player stood at one of a formation's spots, or at the net (`spot` null): their usual place from FROM serves,
 * and the serves they stood OFF_M or more off the spot. */
export interface Taken {
  spot: number | null;
  usual: Spot;
  off: Contact[];
}

export interface Receiver {
  key: string;
  person: number;
  taken: Taken[];
}

/** The other team's serves on `g` with all six of its players seen. */
export const servesOn = (contacts: Contact[], g: Group) => contacts.filter((c) => c.type === 'serve' && c.g !== g && c.receive?.length === 3 * TEAM);

/** Every order of `n` items. */
function orders(n: number): number[][] {
  return n <= 1 ? [[...Array(n).keys()]] : orders(n - 1).flatMap((o) => [...Array(n).keys()].map((k) => [...o.slice(0, k), n - 1, ...o.slice(k)]));
}

/** Each receiver's spot among `spots`, as many, by the least total distance: `spots`' index for each. */
export function assign(places: Spot[], spots: Spot[]): number[] {
  const far = (o: number[]) => o.reduce((sum, s, k) => sum + Math.hypot(places[k][0] - spots[s][0], places[k][1] - spots[s][1]), 0);
  return orders(places.length).reduce((best, o) => (far(o) < far(best) ? o : best));
}

/** `g`'s players receiving the other team's serves in `formation`, each with their usual place at each spot they took
 * and at the net, the nearest it staying there: the spots in order, the net last. */
export function receivers(contacts: Contact[], g: Group, people: Record<string, Person>, formation: Formation): Receiver[] {
  const found = new Map<string, { person: number; at: Map<number | null, { c: Contact; place: Spot }[]> }>();
  for (const c of servesOn(contacts, g)) {
    const all = c.receive as number[];
    const players = Array.from({ length: TEAM }, (_, k) => ({ person: all[3 * k], place: [all[3 * k + 1], all[3 * k + 2]] as Spot })).sort((a, b) => a.place[0] - b.place[0]);
    const back = players.slice(formation.net);
    const spots = assign(
      back.map((p) => p.place),
      formation.spots,
    );
    players.forEach(({ person, place }, k) => {
      const key = playerKey(person, people);
      if (key === null) {
        return;
      }
      const player = found.get(key) ?? { person, at: new Map() };
      const spot = k < formation.net ? null : spots[k - formation.net];
      player.at.set(spot, [...(player.at.get(spot) ?? []), { c, place }]);
      found.set(key, player);
    });
  }
  return [...found].flatMap(([key, { person, at }]) => {
    const taken = [...formation.spots.keys(), null].flatMap((spot): Taken[] => {
      const seen = at.get(spot) ?? [];
      if (seen.length < FROM) {
        return [];
      }
      const to = spot === null ? null : formation.spots[spot];
      const off = to ? seen.filter((x) => Math.hypot(to[0] - x.place[0], to[1] - x.place[1]) >= OFF_M).map((x) => x.c) : [];
      return [{ spot, usual: [median(seen.map((x) => x.place[0])), median(seen.map((x) => x.place[1]))], off }];
    });
    return taken.length ? [{ key, person, taken }] : [];
  });
}
