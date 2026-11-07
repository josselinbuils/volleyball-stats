import { describe, expect, it } from 'vitest';
import type { Contact, Person, Rally } from '@/lib/match';
import { ballBeforeServe, bodyOf, keyed, posesAt, restPose } from '@/components/Watch/helpers/pose';

describe('pose', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    5: { team: 1, number: 5, jersey: null, name: 'Sam' },
    3: { team: 2, number: 3, jersey: null, name: 'Noa' },
  };

  function touch(t: number, type: Contact['type'], person: number | null = 1, extra: Partial<Contact> = {}): Contact {
    const g = person === null ? 1 : people[person].team;
    return { i: t * 10, t, type, g, team: g, side: 'left', rally: 0, set: 1, x: -2, y: 0, zone: null, result: 'play', person, player: null, name: null, ...extra };
  }

  const rally = (contacts: Contact[]): Rally => ({ i: 0, start: 0, end: 20, set: 1, left: 1, flipped: false, winner: 1, score: [1, 0], contacts });
  const at = (person: number, x = -2, y = 0) => ({ person, x, y });
  const pose = (r: Rally | undefined, time: number, dots = [at(1)], places: Map<number, { x: number; y: number; h: number }> | null = null) =>
    posesAt(r, time, dots, dots, dots, places, people).get(dots[0].person)!;

  describe('keyed', () => {
    const keys: [number, number][] = [
      [0, 1],
      [1, 3],
    ];

    it('holds outside its keys and eases between them', () => {
      expect(keyed(keys, -1)).toBe(1);
      expect(keyed(keys, 2)).toBe(3);
      expect(keyed(keys, 0.5)).toBeCloseTo(2);
      expect(keyed(keys, 0.1)).toBeLessThan(1.2);
    });
  });

  describe('restPose', () => {
    it('stands still under walking speed, running above it', () => {
      expect(restPose(1, 0.1, 0, 0).stride).toBe(0);
      const swings = [0, 0.1, 0.2, 0.3].map((t) => Math.abs(restPose(1, t, 4, 0).stride));
      expect(Math.max(...swings)).toBeGreaterThan(0.3);
    });

    it('swings the arms against each other when running', () => {
      const [a, b] = restPose(1, 0.2, 4, 0).arms;
      expect(Math.abs(a.pitch - b.pitch)).toBeGreaterThan(0.1);
    });

    it('is set for the ball in a rally, relaxed out of one', () => {
      expect(restPose(1, 0, 0, 1).crouch).toBeGreaterThan(0);
      expect(restPose(1, 0, 0, 0).crouch).toBe(0);
    });
  });

  describe('posesAt', () => {
    it('rests with no touch near', () => {
      expect(pose(rally([touch(5, 'attack')]), 1).jump).toBe(0);
      expect(pose(undefined, 1).crouch).toBe(0);
    });

    it("jumps to the height of the ball, up to the action's most", () => {
      const places = (h: number) => new Map([[50, { x: -2, y: 0, h }]]);
      const low = pose(rally([touch(5, 'attack')]), 5, [at(1)], places(1.8));
      const high = pose(rally([touch(5, 'attack')]), 5, [at(1)], places(2.6));
      const huge = pose(rally([touch(5, 'attack')]), 5, [at(1)], places(6));
      expect(low.jump).toBe(0);
      expect(high.jump).toBeCloseTo(2.6 - 1.08 - 0.48 * 1.7);
      expect(huge.jump).toBeCloseTo(0.9);
    });

    it('jumps as a parabola, back on the floor after', () => {
      const places = new Map([[50, { x: -2, y: 0, h: 3 }]]);
      const peak = pose(rally([touch(5, 'attack')]), 5, [at(1)], places).jump;
      expect(pose(rally([touch(5, 'attack')]), 5.2, [at(1)], places).jump).toBeCloseTo(peak * 0.75);
      expect(pose(rally([touch(5, 'attack')]), 5.5, [at(1)], places).jump).toBe(0);
    });

    it('leaves and finds the floor when the player did, where the jump was measured', () => {
      const places = new Map([[50, { x: -2, y: 0, h: 3 }]]);
      const measured = (time: number) => pose(rally([touch(5, 'attack', 1, { air: [-0.4, 0.2] })]), time, [at(1)], places).jump;
      const peak = pose(rally([touch(5, 'attack')]), 5, [at(1)], places).jump;
      expect(measured(4.55)).toBe(0);
      expect(measured(4.9)).toBeCloseTo(peak);
      expect(measured(5.25)).toBe(0);
    });

    it('raises the arms by action: over the head on a block, forward on a reception', () => {
      expect(pose(rally([touch(5, 'block')]), 5).arms[0].pitch).toBeGreaterThan(2.5);
      expect(pose(rally([touch(5, 'pass')]), 5).arms[0].pitch).toBeLessThan(1.6);
      expect(pose(rally([touch(5, 'pass')]), 5).crouch).toBeGreaterThan(0.4);
      expect(pose(rally([touch(5, 'dig')]), 5).crouch).toBeGreaterThan(pose(rally([touch(5, 'pass')]), 5).crouch);
    });

    it('plays a free ball as a set overhead, as a pass below', () => {
      const places = (h: number) => new Map([[50, { x: -2, y: 0, h }]]);
      expect(pose(rally([touch(5, 'relance')]), 5, [at(1)], places(2.2)).arms[0].pitch).toBeGreaterThan(2);
      expect(pose(rally([touch(5, 'relance')]), 5, [at(1)], places(0.9)).arms[0].pitch).toBeLessThan(1.4);
    });

    it('lunges towards a ball within reach, not one too far to trust', () => {
      const near = new Map([[50, { x: 0, y: 0, h: 2.5 }]]);
      const far = new Map([[50, { x: 3, y: 0, h: 2.5 }]]);
      expect(pose(rally([touch(5, 'attack')]), 5, [at(1)], near).shift.x).toBeGreaterThan(1);
      expect(pose(rally([touch(5, 'attack')]), 5, [at(1)], near).shift.x).toBeLessThanOrEqual(1.2);
      expect(pose(rally([touch(5, 'attack')]), 5, [at(1)], far).shift.x).toBe(0);
    });

    it('does not lunge on a serve', () => {
      expect(pose(rally([touch(5, 'serve')]), 5, [at(1)], new Map([[50, { x: -1, y: 0, h: 2.5 }]])).shift.x).toBe(0);
    });

    it('gives a floor or net contact no gesture', () => {
      expect(pose(rally([touch(5, 'floor', null)]), 5).crouch).toBeLessThan(0.2);
    });

    it('keeps the nearest touch in time on a body with two', () => {
      const r = rally([touch(5, 'set'), touch(5.3, 'pass')]);
      expect(pose(r, 5).arms[0].pitch).toBeGreaterThan(2);
      expect(pose(r, 5.3).arms[0].pitch).toBeLessThan(1.6);
    });

    it('is the same whenever it is asked: a function of the moment', () => {
      const r = rally([touch(5, 'attack')]);
      expect(pose(r, 5.1)).toEqual(pose(r, 5.1));
    });
  });

  describe('bodyOf', () => {
    const place = { x: 0, y: 0, h: 2 };

    it('takes the named player, by name across their identities', () => {
      expect(bodyOf(touch(1, 'set', 2), place, [at(1, 0.5), at(5, 1)], people)?.person).toBe(5);
    });

    it('takes the nearest teammate when the named player is too far', () => {
      expect(bodyOf(touch(1, 'set', 2), place, [at(1, 0.5), at(5, 8), at(3, 0.1)], people)?.person).toBe(1);
    });

    it('stays with the named player when no teammate is near', () => {
      expect(bodyOf(touch(1, 'set', 2), place, [at(1, 6), at(5, 8)], people)?.person).toBe(5);
    });

    it('gives a touch no one is on nobody', () => {
      expect(bodyOf(touch(1, 'set', null), place, [at(1, 6)], people)).toBeUndefined();
    });
  });

  describe('ballBeforeServe', () => {
    const r = rally([touch(5, 'serve', 1, { x: 8, y: 1 }), touch(6, 'pass', 3, { x: -5, y: 0 })]);
    const server = at(1, 9.5, 1);

    it('rests in the hand, then reaches where the serve is hit from', () => {
      const flown = { x: 8, y: 1, h: 2.7 };
      const rest = ballBeforeServe(r, 2, server, null, flown)!;
      expect(rest.h).toBeCloseTo(1.05);
      expect(rest.x).toBeCloseTo(9.2);
      const hit = ballBeforeServe(r, 4.999, server, null, flown)!;
      expect(hit.x).toBeCloseTo(8, 1);
    });

    it('rises above both on the way', () => {
      expect(ballBeforeServe(r, 4.65, server, null, { x: 8, y: 1, h: 2.7 })!.h).toBeGreaterThan(2.7);
    });

    it('leaves the flight alone after the serve, without a server, or without a serve', () => {
      const flown = { x: 1, y: 1, h: 1 };
      expect(ballBeforeServe(r, 5.5, server, null, flown)).toBe(flown);
      expect(ballBeforeServe(r, 2, undefined, null, flown)).toBe(flown);
      expect(ballBeforeServe(rally([touch(5, 'set')]), 2, server, null, flown)).toBe(flown);
    });
  });
});
