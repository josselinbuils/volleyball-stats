import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { defenders } from '@/components/Coach/helpers/defense';

describe('defenders', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
  };

  const attack = (g: 1 | 2, defense: number[]): Contact =>
    ({
      i: 0,
      t: 0,
      type: 'attack',
      g,
      team: g,
      side: g === 1 ? 'left' : 'right',
      rally: 0,
      set: 1,
      x: 0,
      y: 0,
      zone: null,
      result: 'play',
      person: null,
      player: null,
      name: null,
      defense,
    }) as Contact;
  const times = (n: number, defense: (k: number) => number[]) => Array.from({ length: n }, (_, k) => attack(2, defense(k)));

  it("gives each position a player defended, in court order, their usual place and spot in each role from 5 of the other team's attacks", () => {
    const contacts = [
      // Position 2: 5 times at the net, 5 times off it 1.5 m short of the 3 m line; 4 times at 6, too few.
      ...times(5, () => [1, 2, 0.6, 3, 0.5, 3]),
      ...times(5, (k) => [1, 2, 1.5, 3 + k * 0.1, 3, 3.5]),
      ...times(4, () => [1, 6, 6, 0, 8, 0]),
      ...times(5, () => [1, 1, 5, 3, 6.5, 3.5]),
    ];

    const [alex] = defenders(contacts, 1, people);

    expect(alex.positions.map((p) => p.position)).toEqual([2, 1]);
    expect(alex.positions[0].places).toEqual([
      { role: 'block', usual: [0.6, 3], spot: [0.5, 3] },
      { role: 'off', usual: [1.5, 3.2], spot: [3, 3.5] },
    ]);
    // 1.5 m off at 2 when not blocking, at 1 every time.
    expect(alex.positions.map((p) => p.off.length)).toEqual([5, 5]);
  });

  it("joins a player's identities and leaves out their own team's attacks", () => {
    const contacts = [...times(3, () => [2, 6, 7, 0, 8, 0]), ...times(2, () => [4, 6, 7, 0, 8, 0])];

    expect(defenders(contacts, 1, people).map((d) => [d.person, d.positions[0].places[0].role])).toEqual([[2, 'back']]);
    expect(
      defenders(
        contacts.map((c) => ({ ...c, g: 1 as const })),
        1,
        people,
      ),
    ).toEqual([]);
  });
});
