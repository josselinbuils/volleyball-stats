import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { ball3dAt, jumpAt, trail3dAt } from '@/components/Watch/helpers/flight';

describe('ball3dAt', () => {
  const touch = (t: number, type: string, x: number | null, person: number | null = null) => ({ t, type, x, y: x === null ? null : 0, person }) as Contact;

  it('rises the arc gravity gives the flight between two touches', () => {
    // A set at 2.4 m to an attack at 2.9 m, 1 s later: g T² / 8 = 1.23 m above the straight line.
    const at = ball3dAt([touch(0, 'set', 0), touch(1, 'attack', 4)], 0.5)!;
    expect([at.x, at.y]).toEqual([2, 0]);
    expect(at.h).toBeCloseTo(2.65 + 1.226, 2);
  });

  it('keeps the arc of a flight hiding a missed touch, and waits at the ends', () => {
    const long = ball3dAt([touch(0, 'pass', 0), touch(6, 'pass', 6)], 3)!;
    expect(long.h).toBeCloseTo(0.9 + (9.81 * 2.2 * 2.2) / 8, 2);
    expect(ball3dAt([touch(1, 'serve', -8), touch(2, 'floor', 5)], 9)).toEqual({ x: 5, y: 0, h: 0.11 });
    expect(ball3dAt([touch(1, 'serve', null)], 1)).toBeNull();
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
    const trail = trail3dAt([touch(0, 'set', 0), touch(1, 'attack', 4)], 0.5, 0.2, 3);
    expect(trail.map((p) => p.x)).toEqual([1.2, 1.6, 2]);
  });
});

describe('jumpAt', () => {
  const touch = (t: number, type: string, person: number) => ({ t, type, person }) as Contact;

  it('jumps a player around their attacks and blocks only', () => {
    const rally = [touch(1, 'attack', 3), touch(2, 'dig', 4)];
    expect(jumpAt(rally, 3, 1)).toBeCloseTo(0.55);
    expect(jumpAt(rally, 3, 1.2)).toBeCloseTo(0.55 * 0.75);
    expect(jumpAt(rally, 3, 1.5)).toBe(0);
    expect(jumpAt(rally, 4, 2)).toBe(0);
  });
});
