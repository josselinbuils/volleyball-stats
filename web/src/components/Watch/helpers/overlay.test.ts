import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { CARD_S, ease, onScreen, outBack, placeAt, shownAt, stamps, statCards, trailAt } from '@/components/Watch/helpers/overlay';

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

describe('statCards', () => {
  const touch = (t: number, more: Partial<Contact> = {}) => ({ t, type: 'pass', ...more }) as Contact;

  it("shows a serve's speed after its hit and an attack's numbers at its hit, until the next card", () => {
    const contacts = [touch(10, { type: 'serve', speed: 40 }), touch(11), touch(12, { type: 'attack', reach: 3.1 }), touch(20, { type: 'attack' }), touch(30, { type: 'attack', jump: 0.4 })];
    expect(statCards(contacts).map((c) => [c.contact, c.from, c.until])).toEqual([
      [0, 10.15, 12],
      [2, 12, 12 + CARD_S],
      [4, 30, 30 + CARD_S],
    ]);
    expect(shownAt(statCards(contacts), 11)?.contact).toBe(0);
    expect(shownAt(statCards(contacts), 25)).toBeNull();
  });

  it('has none for a serve whose speed is unmeasured, nor one the next card follows at once', () => {
    expect(statCards([touch(10, { type: 'serve' })])).toEqual([]);
    expect(statCards([touch(10, { type: 'serve', speed: 40 }), touch(10.1, { type: 'attack', jump: 0.3 })]).map((c) => c.contact)).toEqual([1]);
  });
});

describe('outBack and ease', () => {
  it('goes past its end then back, and eases from 0 to 1', () => {
    expect([outBack(0), outBack(1)]).toEqual([0, 1]);
    expect(outBack(0.7)).toBeGreaterThan(1);
    expect([ease(0, 1, -1), ease(0, 1, 0.5), ease(0, 1, 2)]).toEqual([0, 0.5, 1]);
  });
});
