import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { onScreen, placeAt, serveSpeeds, speedAt, stamps, trailAt } from '@/components/Watch/helpers/overlay';

// The ball seen every 0.1 s from 1 s to 1.5 s moving right, then again at 2 s.
const ball = { samples: [1, 0.1, 0.5, 1.1, 0.2, 0.5, 1.2, 0.3, 0.5, 1.3, 0.4, 0.5, 1.4, 0.5, 0.5, 1.5, 0.6, 0.5, 2, 0.9, 0.5] };

describe('placeAt', () => {
  it('places the ball between the samples around', () => {
    expect(placeAt(ball, 1.2)).toEqual({ x: 0.3, y: 0.5 });
    expect(placeAt(ball, 1.25)?.x).toBeCloseTo(0.35);
  });

  it('has no place across a gap, before the first sample or after the last', () => {
    expect(placeAt(ball, 1.7)).toBeNull();
    expect(placeAt(ball, 0.9)).toBeNull();
    expect(placeAt(ball, 2.1)).toBeNull();
  });
});

describe('trailAt', () => {
  it('follows the ball back half a second, oldest first, ending where it is', () => {
    const trail = trailAt(ball, 1.45);
    expect(trail.map((p) => p.x)).toEqual([0.1, 0.2, 0.3, 0.4, 0.5, expect.closeTo(0.55)]);
    expect(trail[0].age).toBeCloseTo(0.45);
    expect(trail[trail.length - 1].age).toBe(0);
  });

  it('ends once on a sample', () => {
    expect(trailAt(ball, 1.2).map((p) => p.x)).toEqual([0.1, 0.2, 0.3]);
  });

  it('keeps the last places, ageing, while the ball is out of sight, and does not join across the gap', () => {
    expect(trailAt(ball, 1.7).map((p) => [p.x, Math.round(p.age * 10)])).toEqual([
      [0.4, 4],
      [0.5, 3],
      [0.6, 2],
    ]);
    expect(trailAt(ball, 2.05).map((p) => p.x)).toEqual([0.9]);
  });
});

describe('stamps', () => {
  it('marks a straight path evenly from its first point to its last, with their ages', () => {
    const marks = stamps(
      [
        { x: 0, y: 0, age: 1 },
        { x: 10, y: 0, age: 0 },
      ],
      2,
    );
    expect(marks.map((m) => m.x)).toEqual([0, 2, 4, 6, 8, 10].map((x) => expect.closeTo(x)));
    expect(marks.map((m) => m.age)).toEqual([1, 0.8, 0.6, 0.4, 0.2, 0].map((a) => expect.closeTo(a)));
  });

  it('rounds a corner without going past it', () => {
    const marks = stamps(
      [
        { x: 0, y: 0, age: 2 },
        { x: 10, y: 0, age: 1 },
        { x: 10, y: 10, age: 0 },
      ],
      1,
    );
    expect(marks[0]).toMatchObject({ x: 0, y: 0 });
    expect(marks[marks.length - 1]).toMatchObject({ x: 10, y: 10 });
    expect(Math.max(...marks.map((m) => m.x))).toBeLessThan(10.001);
    expect(marks.every((m, k) => k === 0 || m.age <= marks[k - 1].age)).toBe(true);
  });

  it('joins nothing under two points', () => {
    expect(stamps([{ x: 1, y: 1, age: 0 }], 1)).toEqual([]);
  });
});

describe('onScreen', () => {
  it('places the picture letterboxed, then zoomed', () => {
    // A 16/9 picture in a 1000 × 1000 box: 1000 × 562.5, 218.75 from the top.
    const whole = onScreen(1000, 1000, 1920, 1080, { scale: 1, x: 0, y: 0 });
    expect(whole.at({ x: 0.5, y: 0 })).toEqual({ x: expect.closeTo(500), y: expect.closeTo(218.75) });
    expect(whole.unit).toBeCloseTo(1000);
    const zoomed = onScreen(1000, 1000, 1920, 1080, { scale: 2, x: -100, y: -50 });
    expect(zoomed.at({ x: 0.5, y: 0 })).toEqual({ x: expect.closeTo(900), y: expect.closeTo(387.5) });
    expect(zoomed.unit).toBeCloseTo(2000);
  });
});

describe('serveSpeeds', () => {
  const touch = (t: number, type: Contact['type'], rally: number, speed?: number) => ({ t, type, rally, speed }) as Contact;

  it('shows a measured serve from just after its hit to the next touch', () => {
    const shown = serveSpeeds([touch(10, 'serve', 0, 62), touch(11.2, 'pass', 0), touch(20, 'serve', 1), touch(30, 'serve', 2, 70), touch(40, 'serve', 3, 55)]);
    expect(shown).toEqual([
      { from: 10.15, until: 11.2, speed: 62 },
      { from: 30.15, until: 32, speed: 70 },
      { from: 40.15, until: 42, speed: 55 },
    ]);
    expect(speedAt(shown, 10.5)?.speed).toBe(62);
    expect(speedAt(shown, 11.3)).toBeNull();
    expect(speedAt(shown, 10)).toBeNull();
  });
});
