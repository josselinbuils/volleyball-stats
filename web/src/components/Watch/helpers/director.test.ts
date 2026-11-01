import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import { broadcastClips, idleCamera, rallyCamera, replayAt, replayCamera, replays, REPLAY_S } from '@/components/Watch/helpers/director';

describe('director', () => {
  function touch(t: number, type: Contact['type'], g: 1 | 2, result: Contact['result'] = 'play', x = g === 1 ? -5 : 5): Contact {
    return { i: t * 100, t, type, g, team: g, side: g === 1 ? 'left' : 'right', rally: 0, set: 1, x, y: 0, zone: null, result, person: 1, player: null, name: null };
  }

  function rally(i: number, start: number, contacts: Contact[], winner: Rally['winner'] = 1, set = 1): Rally {
    return { i, start, end: start + 5, set, left: 1, flipped: false, winner, score: [0, 0], contacts };
  }

  const kill = (start: number) => [touch(start, 'serve', 2, 'play', 9), touch(start + 1, 'pass', 1), touch(start + 2, 'set', 1), touch(start + 3, 'attack', 1, 'point')];
  // Rallies 40 s apart: dead time for any replay.
  const apart = (n: number, make = kill) => Array.from({ length: n }, (_, k) => rally(k, k * 40, make(k * 40)));

  describe('replays', () => {
    it('spaces winning attacks, and keeps the last of a set', () => {
      expect([...replays(apart(10)).keys()]).toEqual([0, 4, 8, 9]);
    });

    it('always shows an ace or a winning block', () => {
      expect([...replays(apart(3, (s) => [touch(s, 'serve', 1, 'point')])).keys()]).toEqual([0, 1, 2]);
    });

    it('needs the dead time and a point for who did it', () => {
      const close = [rally(0, 0, kill(0)), rally(1, 8, kill(8))];
      expect(replays(close).has(0)).toBe(false);
      expect(replays([rally(0, 0, kill(0), 2)]).size).toBe(0);
      expect(replays([{ ...rally(0, 0, kill(0)), redo: true }]).size).toBe(0);
    });

    it('shows no fault', () => {
      expect(replays([rally(0, 0, [touch(0, 'serve', 1, 'error')], 2)]).size).toBe(0);
    });
  });

  describe('replayAt', () => {
    const rallies = apart(1);
    const chosen = replays(rallies);

    it('runs slowly after the rally, around the touch', () => {
      expect(replayAt(rallies, chosen, 5.9)).toBeNull();
      const at = replayAt(rallies, chosen, 6);
      expect(at?.time).toBeCloseTo(3 - 1.8);
      expect(at?.f).toBe(0);
      expect(replayAt(rallies, chosen, 6 + REPLAY_S / 2)?.time).toBeCloseTo(3 - 1.8 + 1.4);
      expect(replayAt(rallies, chosen, 6 + REPLAY_S)).toBeNull();
    });
  });

  describe('broadcastClips', () => {
    it('plays a rally through its replay', () => {
      const rallies = apart(2);
      const clips = broadcastClips(rallies, replays(rallies), 1000);
      expect(clips[0]).toMatchObject({ start: 0, end: 6 + REPLAY_S, rally: 0 });
      // The last of a set has its replay too; a rally without one ends soon after.
      const none = broadcastClips(rallies, new Map(), 1000);
      expect(none[1]).toMatchObject({ start: 39, end: 47.5 });
    });

    it('stays within the video', () => {
      const rallies = apart(1);
      expect(broadcastClips(rallies, new Map(), 6)[0].end).toBe(6);
    });
  });

  describe('rallyCamera', () => {
    const r = rally(0, 0, kill(0));

    it('starts behind the server, inside the hall', () => {
      const shot = rallyCamera(r, 0.2, null);
      expect(shot.eye.x).toBeGreaterThan(9);
      expect(shot.eye.x).toBeLessThanOrEqual(13.2);
      expect(shot.target.x).toBeLessThan(0);
    });

    it('then follows the ball from the stand', () => {
      const shot = rallyCamera(r, 1.2, null);
      expect(shot.eye.y).toBe(13.5);
    });

    it('cuts to the net side from the set to after the attack', () => {
      expect(rallyCamera(r, 1.9, null).eye.y).toBe(13.5);
      for (const t of [2, 3, 4.9]) {
        expect(rallyCamera(r, t, null).eye).toMatchObject({ y: 8.5, x: 3.5 });
      }
      expect(rallyCamera(r, 5.1, null).eye.y).toBe(13.5);
    });

    it('glides: no jump within the wide shot', () => {
      const a = rallyCamera(r, 1.2, null);
      const b = rallyCamera(r, 1.22, null);
      expect(Math.abs(a.eye.x - b.eye.x)).toBeLessThan(0.1);
    });

    it('holds without a touch placed', () => {
      expect(rallyCamera(rally(0, 0, []), 1, null).eye.y).toBe(13.5);
    });
  });

  describe('idleCamera', () => {
    it('drifts within the hall', () => {
      expect(Math.abs(idleCamera(14).eye.x)).toBeLessThanOrEqual(6);
    });
  });

  describe('replayCamera', () => {
    const r = rally(0, 0, kill(0));
    const moment = { rally: r, contact: r.contacts[3], time: 3.5, f: 0.5 };

    it("looks out of the player's eyes at the ball, not at the ceiling", () => {
      const shot = replayCamera(moment, { person: 1, x: -2, y: 1 }, null);
      expect(shot.eye).toMatchObject({ x: -2, y: 1 });
      expect(shot.eye.h).toBeGreaterThan(1.5);
      expect(shot.target.h).toBeLessThanOrEqual(1.6);
    });

    it('looks over the net with the ball at their hands', () => {
      const shot = replayCamera({ ...moment, time: 3 }, { person: 9, x: -5, y: 0 }, null);
      expect(shot.target.x).toBe(3);
    });

    it('falls back on the net side without the player', () => {
      expect(replayCamera(moment, undefined, null).eye.y).toBe(8.5);
    });
  });
});
