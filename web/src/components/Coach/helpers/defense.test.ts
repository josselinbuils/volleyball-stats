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

  it("gives each situation a player defended, by position in court order, side, block and role, from 4 attacks, with every position's spot", () => {
    const contacts = [
      // From the right: at 2 4 times blocking alone, 4 times off the net 1.5 m short beside a teammate at 6; 3 times at 6,
      // too few; 4 times at 1, 2 of them under a double block.
      ...times(4, () => attack(3, [1, 0.6, 3, 2, 0.5, 3, 2, 0.5, 3])),
      ...times(4, (k) => attack(3, [1, 1.5, 3 + k * 0.5, 2, 3, 3.5, 3, 3.5, 0, 2, 7, 0, 6, 7, 0, 6, 3, 2])),
      ...times(3, () => attack(3, [1, 6, 0, 6, 7, 0, 6, 3, 2])),
      ...times(4, (k) => ({ ...attack(3, [1, 5, 3, 1, 6, 2.5, 1, 8, 3]), block: k < 2 ? 2 : 1 })),
      ...times(2, () => ({ ...attack(3, [1, 5, 3, 1, 6, 2.5, 1, 8, 3]), block: 2 })),
      // At 1 from the left too.
      ...times(4, () => attack(-3, [1, 5, 3, 1, 6, 2.5, 1, 8, 3])),
    ];

    const [alex] = defenders(contacts, 1, people, 0);

    expect(alex.situations.map((s) => [s.position, s.side, s.block, s.place.role])).toEqual([
      [2, 'right', 1, 'block'],
      [2, 'right', 1, 'off'],
      [1, 'left', 1, 'back'],
      [1, 'right', 2, 'back'],
    ]);
    expect(alex.situations[1].place).toEqual({ role: 'off', usual: [1.5, 3.75], spot: [3, 3.5] });
    expect(alex.situations[1].spots).toEqual([
      { position: 2, spot: [3, 3.5] },
      { position: 6, spot: [7, 0] },
    ]);
    expect(alex.situations.map((s) => [s.attacks.length, s.off.length])).toEqual([
      [4, 0],
      [4, 4],
      [4, 4],
      [4, 4],
    ]);
    // The balls (all coming down at 5 m in the middle) nearest their spot: at 6 beside them off the net, theirs alone at 1.
    expect(alex.situations.map((s) => s.mine.length)).toEqual([4, 0, 4, 4]);
    // In the middle up, the same player off the net is at 3.
    expect(defenders(contacts, 1, people, 1)[0].situations.map((s) => s.position)).toEqual([3, 2, 1, 1]);
  });

  it("joins a player's identities, leaves out their own team's attacks and a system leaving them over", () => {
    const contacts = [...times(2, () => attack(0, [2, 7, 0, 6, 8, 0, 0, 0, 0])), ...times(2, () => attack(0, [4, 7, 0, 6, 8, 0, 0, 0, 0]))];

    expect(defenders(contacts, 1, people, 0).map((d) => [d.person, d.situations[0].side])).toEqual([[2, 'middle']]);
    expect(defenders(contacts, 1, people, 1)).toEqual([]);
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
