import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import type { Drop } from '@/components/Stats/helpers/between';
import { lines, meanRating, rating, unattacked } from '@/components/Stats/helpers/stats';

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
    expect(count(two.stats)).toEqual({ touches: 1, receptions: 2, missed: 2, rated: 2, faults: 2 });
    expect(count(rest.stats)).toEqual({ touches: 2, attacks: 1, attackFaults: 1, digs: 1, faults: 1 });
    expect(count(total.stats)).toEqual({ touches: 5, serves: 1, aces: 1, receptions: 2, missed: 2, rated: 2, attacks: 2, kills: 1, attackFaults: 1, digs: 1, points: 2, faults: 3 });
  });

  it('counts free balls and their faults', () => {
    const [one] = lines([touch('relance', 1, 0, 'error')], people, 1);
    expect(count(one.stats)).toEqual({ touches: 1, relances: 1, relanceFaults: 1, faults: 1 });
  });

  it('counts an ace missed by no identified player in the rest', () => {
    const [player, rest] = lines([touch('serve', 1, 0, 'point', 2)], people, 2);
    expect([player.id, count(player.stats)]).toEqual(['rest', { receptions: 1, missed: 1, rated: 1, faults: 1 }]);
    expect(rest.id).toBe('total');
  });

  it('counts a ball dropped between two players for each of them, once for the team', () => {
    const landing = touch('floor', 1, null);
    const dropped: Drop[] = [{ landing, pair: [0, 2] }];
    const [one, two, rest, total] = lines([touch('serve', 1, 0), touch('serve', 1, 1), touch('serve', 1, 2), landing], people, 1, dropped);
    expect([one.stats.between, two.stats.between, rest.stats.between, total.stats.between]).toEqual([[landing], [], [landing], [landing]]);
  });

  it('grades the receptions it can rate', () => {
    const at = (type: string, t: number, x: number, y: number) => ({ type, t, x, y, side: 'left', rally: 0, result: 'play' }) as Contact;
    const [one] = lines([{ ...at('pass', 0, -6, 0), g: 1, person: 0 }, at('set', 1.5, -1, 1), { ...at('pass', 3, -6, 0), g: 1, person: 0 }, at('set', 4.5, -6, -3)], people, 1);
    expect(count(one.stats)).toEqual({ touches: 2, receptions: 2, unattacked: 2, rated: 2, perfect: 1, poor: 1 });
    expect(meanRating(one.stats)).toBe(2);
  });
});

describe('rating', () => {
  const touch = (type: string, side: string, t: number, x: number | null, y: number | null, result = 'play', rally = 0) => ({ type, side, t, x, y, result, rally }) as Contact;

  it('grades a reception by how far from the setter’s target its next touch is played', () => {
    const pass = touch('pass', 'left', 0, -6, 0);
    expect(rating(pass, touch('set', 'left', 1.5, -1.5, 1))).toBe(3);
    expect(rating(pass, touch('set', 'left', 1.5, -3, 0))).toBe(2);
    expect(rating(pass, touch('set', 'left', 1.5, -6, -3))).toBe(1);
    // The right half's target is the left one's mirror.
    expect(rating(touch('pass', 'right', 0, 6, 0), touch('set', 'right', 1.5, 1.5, -1))).toBe(3);
  });

  it('gives 1 to a ball sent straight over the net and 0 to a fault', () => {
    expect(rating(touch('pass', 'left', 0, -6, 0), touch('dig', 'right', 1.5, 4, 0))).toBe(1);
    expect(rating(touch('pass', 'left', 0, -6, 0, 'error'), touch('floor', 'left', 1, -7, 0))).toBe(0);
  });

  it('cannot rate without a placed next touch in the rally a second or more later', () => {
    const pass = touch('pass', 'left', 0, -6, 0);
    expect(rating(pass, undefined)).toBeNull();
    expect(rating(pass, touch('serve', 'right', 9, 9, 0, 'play', 1))).toBeNull();
    expect(rating(pass, touch('set', 'left', 0.5, -1, 1.5))).toBeNull();
    expect(rating(pass, touch('set', 'left', 1.5, null, null))).toBeNull();
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
