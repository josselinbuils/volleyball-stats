import { describe, expect, it } from 'vitest';
import type { Contact, Person, Rally } from '@/lib/match';
import { lostOn, setters, things } from '@/components/Coach/helpers/coach';

describe('coach', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    4: { team: 1, number: 4, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
  };

  function touch(rally: number, type: Contact['type'], person: number | null, result: Contact['result'] = 'play', extra: Partial<Contact> = {}): Contact {
    const g = person === null ? 1 : people[person].team;
    return { i: 0, t: rally, type, g, team: g, side: g === 1 ? 'left' : 'right', rally, set: 1, x: 0, y: 0, zone: null, result, person, player: null, name: null, ...extra };
  }

  const rally = (i: number, winner: Rally['winner'], contacts: Contact[], extra: Partial<Rally> = {}) =>
    ({ i, start: i, end: i + 1, set: 1, left: 1, flipped: false, winner, score: [0, 0], contacts, ...extra }) as Rally;

  describe('lostOn', () => {
    it('blames the last touch of the team that lost', () => {
      expect(lostOn(rally(0, 2, [touch(0, 'serve', 1, 'error')]), 1)?.cause).toBe('serve');
      expect(lostOn(rally(0, 2, [touch(0, 'serve', 3), touch(0, 'pass', 1), touch(0, 'dig', 2, 'error')]), 1)?.cause).toBe('defense');
      // A fault the review puts on a teammate's touch is that touch's.
      const blamed = lostOn(rally(0, 2, [touch(0, 'pass', 1), touch(0, 'set', 2, 'play', { f: 7 }), touch(0, 'attack', 1, 'error', { cause: 7 })]), 1);
      expect([blamed?.cause, blamed?.contact.type]).toEqual(['set', 'set']);
    });

    it("counts the other team's point as what it beat", () => {
      expect(lostOn(rally(0, 2, [touch(0, 'serve', 3, 'point')]), 1)?.cause).toBe('reception');
      expect(lostOn(rally(0, 2, [touch(0, 'attack', 3, 'point')]), 1)?.cause).toBe('defense');
      expect(lostOn(rally(0, 2, [touch(0, 'attack', 1, 'error'), touch(0, 'block', 3, 'point')]), 1)?.cause).toBe('attack');
    });

    it('skips a rally won, to replay or wrongly called, and floor contacts', () => {
      const fault = [touch(0, 'attack', 1, 'error')];
      expect(lostOn(rally(0, 1, fault), 1)).toBeNull();
      expect(lostOn(rally(0, 2, fault, { redo: true }), 1)).toBeNull();
      expect(lostOn(rally(0, 2, fault, { wrongCall: true }), 1)).toBeNull();
      expect(lostOn(rally(0, 2, [...fault, touch(0, 'floor', null)]), 1)?.cause).toBe('attack');
    });
  });

  describe('things', () => {
    const lost = (n: number, make: (k: number) => Contact) => Array.from({ length: n }, (_, k) => rally(k, 2, [make(k)]));

    it('ranks by points lost, keeps three, and gives the other team the same count', () => {
      const rallies = [
        ...lost(5, (k) => touch(k, 'attack', 1, 'error')),
        ...lost(4, (k) => touch(k, 'serve', 1, 'error')),
        ...lost(3, (k) => touch(k, 'set', 1, 'error')),
        ...lost(3, (k) => touch(k, 'dig', 1, 'error')),
        rally(0, 1, [touch(0, 'attack', 3, 'error')]),
        rally(0, 1, [touch(0, 'set', 3, 'error')]),
      ];
      const { lost: n, found } = things(rallies, 1);
      expect(n).toBe(15);
      expect(found.map((x) => [x.cause, x.n, x.other])).toEqual([
        ['attack', 5, 1],
        ['serve', 4, 0],
        ['defense', 3, 0],
      ]);
    });

    it('leaves out what cost under 3 points', () => {
      expect(
        things(
          lost(2, (k) => touch(k, 'serve', 1, 'error')),
          1,
        ).found,
      ).toEqual([]);
    });
  });

  describe('setters', () => {
    const pair = (k: number, setter: number, attacker: number, result: Contact['result'] = 'play') => [touch(k, 'set', setter), touch(k, 'attack', attacker, result)];

    it("lists each setter's attackers, a player's identities as one, most attacks first", () => {
      const contacts = [...pair(0, 1, 2), ...pair(1, 1, 4, 'point'), ...pair(2, 1, 1), ...pair(3, 1, 2), touch(4, 'set', 1)];
      const [alex] = setters(contacts, 1, people);
      expect(alex.sets).toBe(5);
      expect(alex.attackers).toHaveLength(1);
      expect(alex.attackers[0].attacks).toHaveLength(3);
    });

    it('leaves out a setter under 5 sets and the other team', () => {
      expect(setters(pair(0, 1, 2), 1, people)).toEqual([]);
      const contacts = Array.from({ length: 5 }, (_, k) => touch(k, 'set', 1));
      expect(setters(contacts, 2, people)).toEqual([]);
    });
  });
});
