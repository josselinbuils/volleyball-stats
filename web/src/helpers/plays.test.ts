import { describe, expect, it } from 'vitest';
import type { Contact, Group, Person, Rally } from '@/lib/match';
import { duos, longestRally, scoringTouch, serveRun } from '@/helpers/plays';

describe('plays', () => {
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

  describe('duos', () => {
    it('finds who set whom, whatever the identity, most attacks first', () => {
      const contacts = [touch(0, 'set', 2), touch(0, 'attack', 1, 'point'), touch(1, 'set', 2), touch(1, 'attack', 3), touch(2, 'set', 1), touch(2, 'attack', 2)];
      expect(duos(contacts, ALEX, people)).toEqual([{ person: 2, fromThem: [contacts[1], contacts[3]], fromMe: [contacts[5]] }]);
    });

    it('needs the set right before the attack, in the rally and the team', () => {
      const contacts = [touch(0, 'set', 2), touch(1, 'attack', 1), touch(2, 'set', 4, 'play', 2), touch(2, 'attack', 1), touch(3, 'dig', 2), touch(3, 'attack', 1)];
      expect(duos(contacts, ALEX, people)).toEqual([]);
    });

    it('leaves out setting oneself', () => {
      expect(duos([touch(0, 'set', 1), touch(0, 'attack', 3)], ALEX, people)).toEqual([]);
    });
  });

  describe('serveRun', () => {
    it("finds the longest run, its scores the server's team first", () => {
      const rallies = [
        rally(0, [touch(0, 'serve', 1)], [1, 0]),
        rally(1, [touch(1, 'serve', 1)], [2, 0]),
        rally(2, [touch(2, 'serve', 1)], [2, 1], 2),
        rally(3, [touch(3, 'serve', 3)], [3, 1]),
        rally(4, [touch(4, 'serve', 3)], [4, 1]),
        rally(5, [touch(5, 'serve', 1)], [5, 1]),
      ];
      expect(serveRun(rallies, ALEX, people)).toEqual({ rallies: [3, 4, 5], from: [2, 1], to: [5, 1] });
    });

    it('goes through a rally to replay', () => {
      const rallies = [rally(0, [touch(0, 'serve', 1)], [1, 0]), { ...rally(1, [touch(1, 'serve', 1)], [1, 0]), redo: true }, rally(2, [touch(2, 'serve', 1)], [2, 0])];
      expect(serveRun(rallies, ALEX, people)?.rallies).toEqual([0, 2]);
    });

    it('needs 2 points', () => {
      expect(serveRun([rally(0, [touch(0, 'serve', 1)], [1, 0])], ALEX, people)).toBeNull();
    });
  });

  describe('scoringTouch', () => {
    it('takes a last touch scoring, or an attack the other team then lost', () => {
      const ace = touch(0, 'serve', 1, 'point');
      expect(scoringTouch(rally(0, [ace], [1, 0]))).toBe(ace);
      const attack = touch(1, 'attack', 1, 'point');
      expect(scoringTouch(rally(1, [attack, touch(1, 'dig', 4, 'error', 2)], [1, 0]))).toBe(attack);
    });

    it('takes none for a plain fault', () => {
      expect(scoringTouch(rally(0, [touch(0, 'attack', 1), touch(0, 'dig', 4, 'error', 2)], [1, 0]))).toBeUndefined();
    });
  });

  describe('longestRally', () => {
    it('takes the most touches, then the longest', () => {
      const short = rally(0, [touch(0, 'serve', 1), touch(0, 'pass', 2)], [1, 0]);
      const long = { ...rally(1, [touch(1, 'serve', 1), touch(1, 'pass', 2)], [2, 0]), end: 99 };
      expect(longestRally([short, long, rally(2, [touch(2, 'serve', 1)], [3, 0])])).toBe(long);
    });

    it('leaves out a rally with no score', () => {
      expect(longestRally([{ ...rally(0, [touch(0, 'serve', 1)], [1, 0]), score: null }])).toBeUndefined();
    });
  });
});
