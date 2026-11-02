import { describe, expect, it } from 'vitest';
import type { Contact, Group, Person, Rally } from '@/lib/match';
import { highlights, measures, tops } from '@/components/MyMatch/helpers/myMatch';

describe('myMatch', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    // A second identity of the same player.
    3: { team: 1, number: 3, jersey: null, name: 'Alex' },
    4: { team: 2, number: 4, jersey: null, name: 'Noa' },
  };
  const ALEX = '1:name Alex';

  function touch(rally: number, type: Contact['type'], person: number | null, result: Contact['result'] = 'play', g: Group = 1): Contact {
    return { i: 0, t: rally * 10, type, g, team: g, side: 'left', rally, set: 1, x: null, y: null, zone: null, result, person, player: null, name: null };
  }

  function rally(i: number, contacts: Contact[], score: [number, number], winner: Group = 1, set = 1): Rally {
    return { i, start: i * 10, end: i * 10 + 5, set, left: 1, flipped: false, winner, score, contacts };
  }

  describe('highlights', () => {
    it('puts the point winning a set first, then long rallies, late ties, aces', () => {
      const long = Array.from({ length: 7 }, () => touch(1, 'dig', 2));
      const rallies = [
        rally(0, [touch(0, 'serve', 1, 'point')], [18, 19]),
        rally(1, [...long, touch(1, 'attack', 1, 'point')], [19, 19]),
        rally(2, [touch(2, 'attack', 1, 'point')], [20, 19]),
        rally(3, [touch(3, 'attack', 1, 'point')], [25, 19]),
      ];
      expect(highlights(rallies, ALEX, people).map((h) => h.kind)).toEqual(['setWon', 'longRally', 'lateTie', 'ace']);
    });

    it("tells nothing of a point lost or another player's", () => {
      const rallies = [rally(0, [touch(0, 'serve', 2, 'point')], [1, 0]), rally(1, [touch(1, 'serve', 1, 'error')], [1, 1], 2)];
      expect(highlights(rallies, ALEX, people)).toEqual([]);
    });

    it("gives the score the player's team first", () => {
      const rallies = [rally(0, [touch(0, 'serve', 4, 'point', 2)], [0, 1], 2), rally(1, [touch(1, 'serve', 2)], [0, 2], 2)];
      expect(highlights(rallies, '2:name Noa', people)).toEqual([expect.objectContaining({ kind: 'ace', score: [1, 0] })]);
    });

    it('keeps the most asked', () => {
      const rallies = [0, 1, 2].map((i) => rally(i, [touch(i, 'serve', 1, 'point')], [i + 1, 0]));
      expect(highlights(rallies, ALEX, people, 2)).toHaveLength(2);
    });
  });

  describe('tops', () => {
    const count = (digs: number, aces: number) => ({ digs: Array<Contact>(digs).fill(touch(0, 'dig', 1)), aces: Array<Contact>(aces).fill(touch(0, 'serve', 1)) });

    it('keeps the stats where the player leads or ties from 3, largest first', () => {
      expect(tops(count(3, 5), [count(3, 1), count(1, 4)], ['digs', 'aces'])).toEqual(['aces', 'digs']);
    });

    it('needs 3, and to lead', () => {
      expect(tops(count(2, 3), [count(1, 4)], ['digs', 'aces'])).toEqual([]);
    });
  });

  describe('measures', () => {
    const served = (...speeds: (number | undefined)[]) => speeds.map((speed, k) => ({ ...touch(k, 'serve', 1), speed }));
    const hit = (...reaches: (number | undefined)[]) => reaches.map((reach, k) => ({ ...touch(k, 'attack', 1), reach }));

    it('finds the fastest serve and the usual speed, leaving out the serves not measured', () => {
      const found = measures(served(40, undefined, 62, 50), []);
      expect(found.fastest?.speed).toBe(62);
      expect(found).toMatchObject({ timed: 3, speed: 50 });
    });

    it('tells no usual speed from under 3 serves, but still the fastest', () => {
      expect(measures(served(40, 50), [])).toMatchObject({ speed: null, timed: 2, fastest: { speed: 50 } });
    });

    it('has nothing without a measure', () => {
      expect(measures(served(undefined), hit(undefined))).toMatchObject({ fastest: null, speed: null, reach: null });
    });

    it('tells an attack height from 5 attacks only, to the decimetre, a wild one not moving it', () => {
      expect(measures([], hit(2.7, 2.7, 2.7, 2.7)).reach).toBeNull();
      expect(measures([], hit(2.68, 2.72, 2.74, 2.7, 3.8)).reach).toBe(2.7);
    });
  });
});
