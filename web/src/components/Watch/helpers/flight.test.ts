import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { ball3dAt, trail3dAt } from '@/components/Watch/helpers/flight';

describe('ball3dAt', () => {
  const touch = (t: number, type: string, x: number | null, person: number | null = null) => ({ t, type, x, y: x === null ? null : 0, person }) as Contact;

  it('rises the arc gravity gives the flight between two touches', () => {
    // A set at 2.4 m to an attack at 2.9 m, 1 s later: g T² / 8 = 1.23 m above the straight line.
    const at = ball3dAt([touch(0, 'set', 0), touch(1, 'attack', 4)], 0.5)!;
    expect([at.x, at.y]).toEqual([2, 0]);
    expect(at.h).toBeCloseTo(2.65 + 1.226, 2);
  });

  it('keeps the arc of a flight hiding a missed touch, and waits on the floor after a landing', () => {
    const long = ball3dAt([touch(0, 'pass', 0), touch(6, 'pass', 6)], 3)!;
    expect(long.h).toBeCloseTo(0.9 + (9.81 * 2.2 * 2.2) / 8, 2);
    expect(ball3dAt([touch(1, 'serve', -8), touch(2, 'floor', 5)], 9)).toEqual({ x: 5, y: 0, h: 0.11 });
    expect(ball3dAt([touch(1, 'serve', null)], 1)).toBeNull();
  });

  it('falls to the floor after the last touch in the air, where its result sends it', () => {
    const touch3 = (t: number, type: string, x: number, result: Contact['result']) => ({ t, type, x, y: 1, person: null, result }) as Contact;
    // A winning attack lands 5 m into the other court half a second later and stays there.
    const kill = [touch3(0, 'set', -1, 'play'), touch3(1, 'attack', -2, 'point')];
    expect(ball3dAt(kill, 1.25)!.h).toBeGreaterThan(0.11);
    expect(ball3dAt(kill, 1.5)).toEqual({ x: 5, y: 1, h: 0.11 });
    expect(ball3dAt(kill, 9)).toEqual({ x: 5, y: 1, h: 0.11 });
    // An attack out lands past the other end line; a dig missed falls on, the way the ball came.
    expect(ball3dAt([touch3(1, 'attack', -2, 'error')], 3)!.x).toBe(10.5);
    const missed = ball3dAt([touch3(0, 'attack', -2, 'play'), touch3(1, 'dig', 6, 'error')], 3)!;
    expect([missed.x, missed.h]).toEqual([7.5, 0.11]);
    // A ball in the net drops straight down.
    const net = ball3dAt([touch3(0, 'attack', -2, 'play'), touch3(1, 'net', -0.3, 'play')], 1.3)!;
    expect(net.x).toBeCloseTo(-0.3, 5);
    expect(net.h).toBeLessThan(2.2);
  });

  it('clears the net when the flight crosses it, not when it ends in it', () => {
    // A dig at 0.7 m 2 m before the net to a pass 4 m past it: the arc alone crosses at 1.46 m.
    const over = ball3dAt([touch(0, 'dig', -2), touch(0.8, 'pass', 4)], 0.8 / 3)!;
    expect(over.x).toBeCloseTo(0, 5);
    expect(over.h).toBeCloseTo(2.6, 5);
    expect(ball3dAt([touch(0, 'dig', -2), touch(0.8, 'pass', 4)], 0.7)!.h).toBeLessThan(2.6);
    const into = ball3dAt([touch(0, 'dig', -2), touch(0.8, 'net', 4)], 0.8 / 3)!;
    expect(into.h).toBeLessThan(2);
  });

  it('follows the ball back in time for its trail', () => {
    const trail = trail3dAt([touch(0, 'set', 0), touch(1, 'attack', 4)], 0.5, null, 0.2, 3);
    expect(trail.map((p) => p.x)).toEqual([1.2, 1.6, 2]);
  });
});
