import { describe, expect, it, vi } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { defenders, sideOf } from '@/components/Coach/helpers/defense';

vi.mock('@/lib/match', () => {
  // Each side's spots in court order (4 3 2 5 6 1), the same under one or two blockers: from the right, 2 at the net, 4
  // and 3 off it, 5 6 1 deep; 1 deeper in the middle up.
  const right = [3, -3.5, 3, 1.5, 0.5, 3, 6, -2.5, 7, 0, 6, 2.5];
  const up = [3, -3.5, 3, 1.5, 0.5, 3, 8, -3, 3, 2, 8, 3];
  const sides = (flat: number[]) => ({ left: { 1: flat, 2: flat }, middle: { 1: flat, 2: flat }, right: { 1: flat, 2: flat } });
  return { match: { defense: { modes: ['perimeter', 'up'], attackers: { left: -3, middle: 0, right: 3 }, spots: { perimeter: sides(right), up: sides(up) } } } };
});

describe('defenders', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
  };

  // An attack by team 2 from `across`, its ball down at 5 m in the middle, each defender [person, depth, across, position].
  const attack = (across: number, defense: number[], g: 1 | 2 = 2): Contact =>
    ({
      i: 0,
      t: 0,
      type: 'attack',
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
      flight: [-1, across, 5, 0],
      defense,
    }) as Contact;
  const times = (n: number, make: (k: number) => Contact) => Array.from({ length: n }, (_, k) => make(k));

  it("gives each situation a player defended, by position in court order, side and block, from 4 attacks, against the side's spots", () => {
    const contacts = [
      // From the right: at 2 4 times; 3 times at 6, too few; at 1 4 times under a single block, 4 under a double one;
      // at 1 from the left 4 times.
      ...times(4, () => attack(3, [1, 0.6, 3, 2])),
      ...times(3, () => attack(3, [1, 6, 0, 6])),
      ...times(4, (k) => attack(3, [1, 5, 2 + k * 0.5, 1])),
      ...times(4, () => ({ ...attack(3, [1, 5, 3, 1]), block: 2 })),
      ...times(4, () => attack(-3, [1, 6, 2.5, 1])),
    ];

    const [alex] = defenders(contacts, 1, people, 0);

    expect(alex.situations.map((s) => [s.position, s.side, s.block, s.place.role])).toEqual([
      [2, 'right', 1, 'block'],
      [1, 'left', 1, 'back'],
      [1, 'right', 1, 'back'],
      [1, 'right', 2, 'back'],
    ]);
    expect(alex.situations[2].place).toEqual({ role: 'back', usual: [5, 2.75], spot: [6, 2.5] });
    expect(alex.situations[2].spots.map((s) => s.position)).toEqual([4, 3, 2, 5, 6, 1]);
    // At 1 from the right, every place 1 m or more off its spot.
    expect(alex.situations.map((s) => [s.attacks.length, s.off.length])).toEqual([
      [4, 0],
      [4, 0],
      [4, 4],
      [4, 4],
    ]);
    // The balls at 5 m in the middle come down nearest 6's spot: none at 2 or 1.
    expect(alex.situations.map((s) => s.mine.length)).toEqual([0, 0, 0, 0]);
    // In the middle up, the same situations, 1 deeper.
    const up = defenders(contacts, 1, people, 1)[0].situations;
    expect(up.map((s) => [s.position, s.side, s.block])).toEqual(alex.situations.map((s) => [s.position, s.side, s.block]));
    expect(up[2].place.spot).toEqual([8, 3]);
  });

  it("joins a player's identities, leaves out their own team's attacks and gives a ball to the nearest spot", () => {
    const contacts = [...times(2, () => attack(0, [2, 7, 0, 6])), ...times(2, () => attack(0, [4, 7, 0, 6]))];

    const found = defenders(contacts, 1, people, 0);
    expect(found.map((d) => [d.person, d.situations[0].side])).toEqual([[2, 'middle']]);
    expect(found[0].situations[0].mine).toHaveLength(4);
    expect(
      defenders(
        contacts.map((c) => ({ ...c, g: 1 as const })),
        1,
        people,
        0,
      ),
    ).toEqual([]);
    expect(contacts.map(sideOf)[0]).toBe('middle');
  });
});
