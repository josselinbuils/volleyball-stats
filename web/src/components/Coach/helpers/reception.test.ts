import { describe, expect, it, vi } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { assign, FORMATIONS, receivers, servesOn } from '@/components/Coach/helpers/reception';

vi.mock('@/lib/match', () => ({ match: {} }));

describe('receivers', () => {
  const people: Record<string, Person> = Object.fromEntries(Array.from({ length: 7 }, (_, k) => [k + 1, { team: 1, number: k + 1, jersey: null, name: k === 6 ? 'P1' : `P${k + 1}` }]));

  // A serve by team 2, team 1's players [person, depth, across].
  const serve = (receive: number[], g: 1 | 2 = 2): Contact => ({
    i: 0,
    t: 0,
    type: 'serve',
    g,
    team: g,
    side: 'right',
    rally: 0,
    set: 1,
    x: 0,
    y: 0,
    zone: null,
    result: 'play',
    person: null,
    player: null,
    name: null,
    receive,
  });
  // Three at the net, the back three in their lanes, 1 at `left` across.
  const usual = (left = -2.5) => serve([1, 5.5, left, 2, 6.5, 0, 3, 5.5, 2.5, 4, 1, -1, 5, 1.5, 0, 6, 1, 1]);

  it("gives each player's usual place at the spots they took and at the net, and the serves they stood off", () => {
    const contacts = [usual(), usual(), usual(-4)];

    const found = receivers(contacts, 1, people, FORMATIONS.three);

    expect(found.find((r) => r.person === 1)?.taken.map((x) => [x.spot, x.usual, x.off.length])).toEqual([[0, [5.5, -2.5], 1]]);
    expect(found.find((r) => r.person === 2)?.taken.map((x) => [x.spot, x.off.length])).toEqual([[1, 0]]);
    expect(found.find((r) => r.person === 5)?.taken.map((x) => [x.spot, x.usual])).toEqual([[null, [1.5, 0]]]);
  });

  it('keeps the nearest the net there as the formation says, and needs FROM serves', () => {
    // In a W only the nearest stays at the net: 4 and 6 receive in front.
    const w = receivers([usual(), usual(), usual()], 1, people, FORMATIONS.w);
    expect(w.filter((r) => r.taken.some((x) => x.spot === null)).map((r) => r.person)).toEqual([4]);
    expect(receivers([usual(), usual()], 1, people, FORMATIONS.three)).toEqual([]);
  });

  it("joins a player's identities and leaves out serves missing a player or the team's own", () => {
    const swapped = serve([7, 5.5, -2.5, 2, 6.5, 0, 3, 5.5, 2.5, 4, 1, -1, 5, 1.5, 0, 6, 1, 1]);

    expect(receivers([usual(), usual(), swapped], 1, people, FORMATIONS.three).find((r) => r.person === 1)?.taken[0].usual).toEqual([5.5, -2.5]);
    expect(servesOn([serve([1, 5, 0]), { ...usual(), g: 1 }, usual()], 1)).toHaveLength(1);
  });

  it('pairs places with spots by the least total distance', () => {
    expect(
      assign(
        [
          [5, 2],
          [5, -2],
        ],
        [
          [5, -2.5],
          [5, 2.5],
        ],
      ),
    ).toEqual([1, 0]);
  });
});
