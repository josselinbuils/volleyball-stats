import { describe, expect, it } from 'vitest';
import type { Contact, Group, Person, Rally } from '@/lib/match';
import { duos, highlights, serveRun, tops } from '@/components/MyMatch/helpers/myMatch';

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
});
