import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { jumpers } from '@/components/Coach/helpers/jumps';

describe('jumpers', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
    5: { team: 2, number: 5, jersey: null, name: 'Lou' },
  };

  function touch(type: Contact['type'], person: number, rally: number, jump: Partial<Contact> = {}): Contact {
    const g = people[person].team;
    return { i: 0, t: rally, type, g, team: g, side: 'left', rally, set: 1, x: 0, y: 0, zone: null, result: 'play', person, player: null, name: null, ...jump };
  }

  // Each attack on a teammate's set: Alex sets for the others, Sam for Alex, Noa and Lou for each other.
  const setter = (person: number) => ({ 1: 2, 3: 5, 5: 3 })[person] ?? 1;
  const times = (n: number, person: number, jump: Partial<Contact>, from = setter(person)) =>
    Array.from({ length: n }, (_, k) => [touch('set', from, k + 100 * person), touch('attack', person, k + 100 * person, jump)]).flat();

  it('tells a player hitting on the way down to jump later, one hitting on the way up earlier', () => {
    expect(jumpers(times(5, 1, { late: 150, run: 2, drift: 0.3 }), 1, people)).toEqual([expect.objectContaining({ person: 1, tips: ['later'] })]);
    expect(jumpers(times(5, 1, { late: -150 }), 1, people)[0].tips).toEqual(['earlier']);
  });

  it('asks for more run-up and a jump up rather than forward, from their medians', () => {
    const contacts = [...times(3, 1, { late: 0, run: 0.5, drift: 1 }), ...times(2, 1, { late: 0, run: 3, drift: 0.2 })];
    expect(jumpers(contacts, 1, people)[0].tips).toEqual(['runUp', 'up']);
  });

  it('joins a named player across identities and leaves those under five jumps, the other team and nothing to say', () => {
    expect(jumpers([...times(3, 2, { late: 200 }), ...times(2, 4, { late: 200 })], 1, people)).toHaveLength(1);
    expect(jumpers(times(4, 1, { late: 200 }), 1, people)).toEqual([]);
    expect(jumpers(times(5, 3, { late: 200 }), 1, people)).toEqual([]);
    expect(jumpers(times(5, 1, { late: 50, run: 2, drift: 0.3 }), 1, people)).toEqual([]);
  });

  it("skips attacks with no jump measured, a setter's dump and an attack on no set", () => {
    expect(jumpers([...times(4, 1, { late: 200 }), ...times(3, 1, {})], 1, people)).toEqual([]);
    expect(jumpers(times(5, 1, { late: 200 }, 1), 1, people)).toEqual([]);
    expect(
      jumpers(
        times(5, 1, { late: 200 }).filter((c) => c.type === 'attack'),
        1,
        people,
      ),
    ).toEqual([]);
  });
});
