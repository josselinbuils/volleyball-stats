import { describe, expect, it, vi } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { defenders, sideOf, spotsOf } from '@/components/Coach/helpers/defense';

vi.mock('@/lib/match', () => {
  // Each side's spots in court order (4 3 2 5 6 1), the same under one or two blockers: 2 at the net, 4 and 3 off it,
  // 5 6 1 deep; 1 deeper in the middle up.
  const perimeter = [3, -3.5, 3, 1.5, 0.5, 3, 6, -2.5, 7, 0, 6, 2.5];
  const up = [3, -3.5, 3, 1.5, 0.5, 3, 8, -3, 3, 2, 8, 3];
  const sides = (flat: number[]) => ({ left: { 1: flat, 2: flat }, middle: { 1: flat, 2: flat }, right: { 1: flat, 2: flat } });
  return { match: { defense: { modes: ['perimeter', 'up'], attackers: { left: -3, middle: 0, right: 3 }, spots: { perimeter: sides(perimeter), up: sides(up) } } } };
});

describe('defenders', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
  };

  // An attack by team 2 hit from `across`, each defender [person, depth, across, position].
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
      hit: [-1, across],
      defense,
    }) as Contact;
  const times = (n: number, make: (k: number) => Contact) => Array.from({ length: n }, (_, k) => make(k));

  it('gives where a player defended each position, by court order, side and block, from 3 attacks', () => {
    const contacts = [
      // From the right: at 2 3 times; 2 times at 6, too few; at 1 4 times under a single block, 4 under a double one;
      // at 1 from the left 4 times.
      ...times(3, () => attack(3, [1, 0.6, 3, 2])),
      ...times(2, () => attack(3, [1, 6, 0, 6])),
      ...times(4, (k) => attack(3, [1, 5, 2 + k * 0.5, 1])),
      ...times(4, () => ({ ...attack(3, [1, 5, 3, 1]), block: 2 })),
      ...times(4, () => attack(-3, [1, 6, 2.5, 1])),
    ];

    const [alex] = defenders(contacts, 1, people, 0);

    expect(alex.played.map((p) => [p.position, p.side, p.block, p.usual, p.off.length])).toEqual([
      [2, 'right', 1, [0.6, 3], 0],
      [1, 'left', 1, [6, 2.5], 0],
      [1, 'right', 1, [5, 2.75], 4],
      [1, 'right', 2, [5, 3], 4],
    ]);
    // In the middle up, the same places, off its deeper 1.
    expect(defenders(contacts, 1, people, 1)[0].played.map((p) => p.off.length)).toEqual([0, 4, 4, 4]);
  });

  it("joins a player's identities and leaves out their own team's attacks", () => {
    const contacts = [...times(2, () => attack(0, [2, 7, 0, 6])), ...times(2, () => attack(0, [4, 7, 0, 6]))];

    expect(defenders(contacts, 1, people, 0).map((d) => [d.person, d.played[0].side])).toEqual([[2, 'middle']]);
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

  it("gives every position's spot in a system", () => {
    expect(spotsOf(1, 'left', 2).map((s) => s.position)).toEqual([4, 3, 2, 5, 6, 1]);
    expect(spotsOf(1, 'left', 2)[4].spot).toEqual([3, 2]);
  });

  it('swaps the blocker and the outside on the attack side under a single block with the setter at 3', () => {
    // From the right: 3's job at the net goes to 2, 2's behind the block to 3; nothing moves under a double block.
    expect(spotsOf(0, 'right', 1, 3).slice(1, 3)).toEqual([
      { position: 3, spot: [0.5, 3] },
      { position: 2, spot: [3, 1.5] },
    ]);
    expect(spotsOf(0, 'right', 2, 3)).toEqual(spotsOf(0, 'right', 2));
    // A player numbered 3 at the net is 2 with the setter at 3.
    const blocking = Array.from({ length: 4 }, () => attack(3, [1, 0.5, 3, 3]));
    expect(defenders(blocking, 1, people, 0, 3)[0].played[0].position).toBe(2);
    expect(defenders(blocking, 1, people, 0)[0].played[0].position).toBe(3);
  });
});
