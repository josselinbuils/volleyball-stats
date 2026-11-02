import { describe, expect, it } from 'vitest';
import type { Contact, Person, Rally } from '@/lib/match';
import { filmMoments, filmShots, momentOf, orbitCamera, shotAt } from '@/components/MyMatch/helpers/film';

describe('film', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
  };
  const KEY = '1:name Alex';

  function touch(rally: number, t: number, type: Contact['type'], result: Contact['result'] = 'play', extra: Partial<Contact> = {}): Contact {
    return { i: rally * 10 + t, t: rally * 100 + t, type, g: 1, team: 1, side: 'left', rally, set: 1, x: 8, y: 1, zone: null, result, person: 1, player: 1, name: 'Alex', ...extra };
  }

  function rallies(...contacts: Contact[][]): Rally[] {
    return contacts.map((c, i) => ({ i, start: i * 100, end: i * 100 + 20, set: 1, left: 1, flipped: false, winner: 1, score: [i + 1, i], contacts: c }));
  }

  describe('filmMoments', () => {
    it('opens on the fastest serve, then builds up to the best, one a rally', () => {
      const a = touch(0, 1, 'serve', 'play', { speed: 50 });
      const b = touch(1, 1, 'serve', 'play', { speed: 60 });
      const c = touch(2, 1, 'attack', 'point');
      const d = touch(2, 3, 'attack', 'point');
      const all = [a, b, c, d];
      const moments = filmMoments(rallies([a], [b], [c, d]), KEY, people, all);
      expect(moments[0]).toBe(b);
      expect(new Set(moments.map((m) => m.rally)).size).toBe(moments.length);
      expect(moments.at(-1)?.result).toBe('point');
    });

    it('leaves out what they got wrong', () => {
      const miss = touch(0, 1, 'attack', 'error');
      const dig = touch(1, 1, 'dig');
      expect(filmMoments(rallies([miss], [dig]), KEY, people, [miss, dig])).toEqual([dig]);
    });

    it('keeps at most four moments', () => {
      const all = [0, 1, 2, 3, 4, 5].map((k) => touch(k, 1, 'attack', 'point'));
      expect(filmMoments(rallies(...all.map((c) => [c])), KEY, people, all)).toHaveLength(4);
    });
  });

  describe('filmShots', () => {
    const point = touch(0, 10, 'attack', 'point');
    const serve = touch(1, 10, 'serve');
    const pass = touch(1, 11, 'pass', 'play', { person: 2 });
    const all = rallies([point], [serve, pass]);

    it('opens on a title, plays then replays each moment and ends', () => {
      const { shots } = filmShots([point, serve], all);
      expect(shots.map((s) => s.kind)).toEqual(['intro', 'live', 'replay', 'live', 'replay', 'outro']);
    });

    it('stays near 45 seconds with four moments', () => {
      const four = [0, 1, 2, 3].map((k) => touch(k, 10, 'attack', 'point'));
      const { length } = filmShots(four, rallies(...four.map((c) => [c])));
      expect(length).toBeGreaterThan(35);
      expect(length).toBeLessThanOrEqual(45);
    });

    it('never starts a moment before its rally', () => {
      const early = touch(0, 1, 'attack');
      const live = filmShots([early], rallies([early])).shots[1];
      expect(live.from).toBe(0);
    });

    it('follows a serve to the touch after it', () => {
      const live = filmShots([serve], all).shots[1];
      expect(live.from + live.length).toBeCloseTo(pass.t + 0.5);
    });

    it('slows the replay around the touch', () => {
      const { shots } = filmShots([point], all);
      const replay = shots[2];
      expect(shotAt(shots, replay.start + 0.01)).toBe(replay);
      expect(momentOf(replay, replay.start + replay.length)).toBeCloseTo(point.t + 0.8);
    });
  });

  describe('orbitCamera', () => {
    it('looks at the player from a few metres, moving as the replay goes on', () => {
      const c = touch(0, 10, 'attack', 'point');
      const replay = filmShots([c], rallies([c])).shots[2];
      const at = { x: 8, y: 1 };
      const first = orbitCamera(replay, replay.from, at, null);
      const last = orbitCamera(replay, replay.from + replay.length * replay.speed, at, null);
      expect(first.target).toEqual({ x: 8, y: 1, h: 1.05 });
      expect(Math.hypot(first.eye.x - 8, first.eye.y - 1)).toBeCloseTo(5.2);
      expect(last.eye.x).not.toBeCloseTo(first.eye.x);
    });
  });
});
