import { describe, expect, it } from 'vitest';
import type { Contact, Person, Rally } from '@/lib/match';
import { lines } from '@/components/Stats/helpers/stats';
import { trophies } from '@/components/Trophies/helpers/trophies';

describe('trophies', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
  };

  function touch(rally: number, type: Contact['type'], person: number, result: Contact['result'] = 'play'): Contact {
    const g = people[person].team;
    return { i: 0, t: rally, type, g, team: g, side: 'left', rally, set: 1, x: null, y: null, zone: null, result, person, player: null, name: null };
  }

  function played(contacts: Contact[], rallies: Rally[] = []) {
    return trophies([...lines(contacts, people, 1), ...lines(contacts, people, 2)], contacts, rallies, people);
  }

  const times = (n: number, make: (k: number) => Contact) => Array.from({ length: n }, (_, k) => make(k));

  it('gives a trophy to the most, across both teams', () => {
    const contacts = [...times(2, (k) => touch(k, 'serve', 1, 'point')), ...times(3, (k) => touch(10 + k, 'serve', 3, 'point'))];
    expect(played(contacts).find((x) => x.kind === 'aces')).toMatchObject({ people: [3], n: 3 });
  });

  it('shares a trophy in a tie, replaying all their touches', () => {
    const contacts = [...times(2, (k) => touch(k, 'serve', 1, 'point')), ...times(2, (k) => touch(10 + k, 'serve', 3, 'point'))];
    expect(played(contacts).find((x) => x.kind === 'aces')).toMatchObject({ people: [1, 3], n: 2, contacts: expect.any(Array) });
    expect(played(contacts).find((x) => x.kind === 'aces')).toHaveProperty('contacts.length', 4);
  });

  it('gives none under its minimum', () => {
    expect(played([touch(0, 'serve', 1, 'point')]).some((x) => x.kind === 'aces')).toBe(false);
  });

  it('names no fault', () => {
    const kinds = played(times(9, (k) => touch(k, 'attack', 1, 'error'))).map((x) => x.kind as string);
    expect(kinds).not.toContain('attackFaults');
    expect(kinds).not.toContain('faults');
  });

  it('finds the duo with the most winning attacks, the fewest tries then', () => {
    const pair = (k: number, setter: number, attacker: number, result: Contact['result']) => [touch(k, 'set', setter), touch(k, 'attack', attacker, result)];
    const contacts = [...pair(0, 1, 2, 'point'), ...pair(1, 1, 2, 'point'), ...pair(2, 1, 2, 'point'), ...pair(3, 1, 2, 'play'), ...pair(4, 2, 1, 'point'), ...pair(5, 2, 1, 'point')];
    expect(played(contacts).find((x) => x.kind === 'duo')).toMatchObject({ setter: 1, attacker: 2, n: 3, of: 4 });
  });

  it('gives the run on serve from 3 points, and the longest rally', () => {
    const rally = (i: number, score: [number, number], extra: Contact[] = []) =>
      ({ i, start: i, end: i + 1, set: 1, left: 1, flipped: false, winner: 1, score, contacts: [touch(i, 'serve', 1), ...extra] }) as Rally;
    const rallies = [rally(0, [1, 0]), rally(1, [2, 0], [touch(1, 'pass', 3), touch(1, 'dig', 3)]), rally(2, [3, 0])];
    const found = played(
      rallies.flatMap((r) => r.contacts),
      rallies,
    );
    expect(found.find((x) => x.kind === 'serveRun')).toMatchObject({ people: [1], n: 3, rallies: [0, 1, 2] });
    expect(found.find((x) => x.kind === 'longest')).toMatchObject({ n: 3, rally: rallies[1] });
  });

  it('gives the fastest serve, once enough are measured', () => {
    const served = (rally: number, person: number, speed?: number) => ({ ...touch(rally, 'serve', person), speed });
    const few = [served(0, 1, 60), served(1, 3, 40), served(2, 3, 41), served(3, 3), served(4, 3)];
    expect(played(few).find((x) => x.kind === 'fastServe')).toBeUndefined();
    const enough = [served(0, 1, 60), served(1, 3, 40), served(2, 3, 41), served(3, 3, 42), served(4, 2, 45)];
    expect(played(enough).find((x) => x.kind === 'fastServe')).toMatchObject({ people: [1], n: 60, contacts: [enough[0]] });
  });
});
