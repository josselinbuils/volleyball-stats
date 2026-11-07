import { describe, expect, it, vi } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { defenders, sideOf } from '@/components/Coach/helpers/defense';

vi.mock('@/lib/match', () => ({ match: { defenseModes: ['perimeter', 'up'] } }));

describe('defenders', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
  };

  // An attack by team 2 from `across`, each defender [person, depth, across, perimeter spot, middle up spot].
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

  it('gives each position a player defended against one side, in court order, their usual place and spot in each role from 4 attacks', () => {
    const contacts = [
      // From the right: position 2 4 times at the net, 4 times off it 1.5 m short; 3 times at 6, too few; 4 times at 1.
      ...times(4, () => attack(3, [1, 0.6, 3, 2, 0.5, 3, 2, 0.5, 3])),
      ...times(4, (k) => attack(3, [1, 1.5, 3 + k * 0.5, 2, 3, 3.5, 3, 3.5, 0])),
      ...times(3, () => attack(3, [1, 6, 0, 6, 7, 0, 6, 3, 2])),
      ...times(4, () => attack(3, [1, 5, 3, 1, 6, 2.5, 1, 8, 3])),
      // From the left, not counted.
      ...times(4, () => attack(-3, [1, 5, 3, 1, 6, 2.5, 1, 8, 3])),
    ];

    const [alex] = defenders(contacts, 1, people, 0, 'right');

    expect(alex.positions.map((p) => p.position)).toEqual([2, 1]);
    expect(alex.positions[0].places).toEqual([
      { role: 'block', usual: [0.6, 3], spot: [0.5, 3] },
      { role: 'off', usual: [1.5, 3.75], spot: [3, 3.5] },
    ]);
    expect(alex.positions.map((p) => [p.attacks.length, p.off.length])).toEqual([
      [8, 4],
      [4, 4],
    ]);
    // In the middle up, the same player off the net is at 3.
    expect(defenders(contacts, 1, people, 1, 'right')[0].positions.map((p) => p.position)).toEqual([3, 2, 1]);
  });

  it("joins a player's identities, leaves out their own team's attacks and a system leaving them over", () => {
    const contacts = [...times(2, () => attack(0, [2, 7, 0, 6, 8, 0, 0, 0, 0])), ...times(2, () => attack(0, [4, 7, 0, 6, 8, 0, 0, 0, 0]))];

    expect(defenders(contacts, 1, people, 0, 'middle').map((d) => [d.person, d.positions[0].places[0].role])).toEqual([[2, 'back']]);
    expect(defenders(contacts, 1, people, 1, 'middle')).toEqual([]);
    expect(
      defenders(
        contacts.map((c) => ({ ...c, g: 1 as const })),
        1,
        people,
        0,
        'middle',
      ),
    ).toEqual([]);
    expect(contacts.map(sideOf)[0]).toBe('middle');
  });
});
