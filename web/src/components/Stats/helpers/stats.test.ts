import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { lines, unattacked } from '@/components/Stats/helpers/stats';

describe('lines', () => {
  const people: Record<string, Person> = {
    0: { team: 1, number: 1, jersey: null },
    1: { team: 1, number: 2, jersey: null },
    2: { team: 1, number: null, jersey: null },
    3: { team: 2, number: 1, jersey: null },
  };
  // Each touch alone in its rally: no touch follows it.
  let rally = 0;
  const touch = (type: string, g: number, person: number | null, result = 'play', receiver?: number) => ({ type, g, person, result, receiver, rally: rally++ }) as Contact;
  const contacts = [
    touch('serve', 1, 0, 'point', 3), // ace on team 2's no. 1
    touch('serve', 2, 3, 'point', 1), // ace on team 1's no. 2
    touch('serve', 2, 3, 'play'),
    touch('pass', 1, 1, 'error'),
    touch('attack', 1, 0, 'point'),
    touch('attack', 1, 2, 'error'), // a track without identity
    touch('dig', 1, 3), // team 2's player on team 1's side: a swapped track
    touch('floor', 1, null),
  ];
  const count = (stats: Record<string, Contact[]>) =>
    Object.fromEntries(
      Object.entries(stats)
        .filter(([, v]) => v.length)
        .map(([k, v]) => [k, v.length]),
    );

  it('counts the touches, points and faults of each player, aces missed included, then the rest and the team', () => {
    const [one, two, rest, total] = lines(contacts, people, 1);
    expect([one.id, two.id, rest.id, total.id]).toEqual([0, 1, 'rest', 'total']);
    expect(count(one.stats)).toEqual({ touches: 2, serves: 1, aces: 1, attacks: 1, kills: 1, points: 2 });
    expect(count(two.stats)).toEqual({ touches: 1, receptions: 2, missed: 2, faults: 2 });
    expect(count(rest.stats)).toEqual({ touches: 2, attacks: 1, attackFaults: 1, digs: 1, faults: 1 });
    expect(count(total.stats)).toEqual({ touches: 5, serves: 1, aces: 1, receptions: 2, missed: 2, attacks: 2, kills: 1, attackFaults: 1, digs: 1, points: 2, faults: 3 });
  });

  it('counts free balls and their faults', () => {
    const [one] = lines([touch('relance', 1, 0, 'error')], people, 1);
    expect(count(one.stats)).toEqual({ touches: 1, relances: 1, relanceFaults: 1, faults: 1 });
  });

  it('counts an ace missed by no identified player in the rest', () => {
    const [player, rest] = lines([touch('serve', 1, 0, 'point', 2)], people, 2);
    expect([player.id, count(player.stats)]).toEqual(['rest', { receptions: 1, missed: 1, faults: 1 }]);
    expect(rest.id).toBe('total');
  });
});

describe('unattacked', () => {
  const touch = (type: string, side: string, rally = 0, result = 'play') => ({ type, side, rally, result }) as Contact;

  it('is a reception or a dig after which its team sent the ball back or lost it without attacking', () => {
    expect(unattacked(touch('pass', 'left'), [touch('set', 'left'), touch('attack', 'left'), touch('dig', 'right')])).toBe(false);
    expect(unattacked(touch('pass', 'left'), [touch('set', 'left'), touch('relance', 'left'), touch('dig', 'right'), touch('attack', 'right')])).toBe(true);
    expect(unattacked(touch('dig', 'left'), [touch('dig', 'right')])).toBe(true);
    expect(unattacked(touch('dig', 'left'), [touch('set', 'left'), touch('floor', 'left')])).toBe(true);
  });

  it('is unknown for a fault, without a next touch in the rally, or for another touch', () => {
    expect(unattacked(touch('pass', 'left', 0, 'error'), [touch('floor', 'left')])).toBe(false);
    expect(unattacked(touch('pass', 'left'), [touch('serve', 'left', 1)])).toBe(false);
    expect(unattacked(touch('set', 'left'), [touch('dig', 'right')])).toBe(false);
  });
});
