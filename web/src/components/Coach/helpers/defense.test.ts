import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { placements } from '@/components/Coach/helpers/defense';

describe('placements', () => {
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

  it("gives each player their usual way in the kind of spot where it is longest, from 8 of the other team's attacks", () => {
    const contacts = [
      ...Array.from({ length: 8 }, (_, k) => attack(2, [1, 2, 2 + k * 0.5, 0, 2, 1, 0.5, 1.2])),
      ...Array.from({ length: 8 }, () => attack(2, [1, 1, 1, 0])),
      ...Array.from({ length: 7 }, () => attack(2, [1, 0, 4, 0])),
    ];

    const found = placements(contacts, 1, people);

    expect(found.map(({ person, spot, back, out }) => ({ person, spot, back, out }))).toEqual([
      { person: 1, spot: 'deep', back: 3.75, out: 0 },
      { person: 2, spot: 'corner', back: 0.5, out: 1.2 },
    ]);
    expect(found[0].off).toHaveLength(8);
  });

  it("joins a player's identities, leaves out their own team's attacks and a way under 1 m", () => {
    const contacts = [...Array.from({ length: 4 }, () => attack(2, [2, 0, 1.5, 0])), ...Array.from({ length: 4 }, () => attack(2, [4, 0, 1.5, 0]))];

    expect(placements(contacts, 1, people).map((p) => p.spot)).toEqual(['front']);
    expect(
      placements(
        contacts.map((c) => ({ ...c, g: 1 as const })),
        1,
        people,
      ),
    ).toEqual([]);
    expect(
      placements(
        Array.from({ length: 8 }, () => attack(2, [1, 0, 0.9, -0.9])),
        1,
        people,
      ),
    ).toEqual([]);
  });
});
