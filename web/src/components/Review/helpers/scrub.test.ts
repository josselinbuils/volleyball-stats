import { describe, expect, it } from 'vitest';
import { coarse, FINE_PX, FINE_SPAN_PX, frameTime, nudgeOf, slowStarts, stretchedTime, stretchedX } from '@/components/Review/helpers/scrub';
import { SLOW_BEFORE_S } from '@/helpers/slow';

describe('nudgeOf', () => {
  it('moves a frame every FINE_PX, none past FINE_SPAN_PX', () => {
    expect(nudgeOf(0)).toBe(0);
    expect(nudgeOf(1)).toBe(0);
    expect(nudgeOf(FINE_PX)).toBe(1);
    expect(nudgeOf(-2 * FINE_PX)).toBe(-2);
    expect(nudgeOf(FINE_SPAN_PX)).toBe(FINE_SPAN_PX / FINE_PX);
    expect(nudgeOf(FINE_SPAN_PX + 1)).toBeNull();
    expect(nudgeOf(-FINE_SPAN_PX - 1)).toBeNull();
  });
});

describe('coarse', () => {
  it('holds when a pixel spans more than a frame', () => {
    expect(coarse(9, 50)).toBe(true);
    expect(coarse(260, 50)).toBe(false);
    expect(coarse(0, 50)).toBe(false);
  });
});

describe('frameTime', () => {
  it('reads back as the same frame', () => {
    for (const frame of [0, 1, 49, 12345]) {
      expect(Math.round(frameTime(frame, 50) * 50)).toBe(frame);
    }
    expect(frameTime(-1, 50)).toBe(0);
  });
});

describe('slowStarts', () => {
  const touches = [10, 12];
  it('holds when a slowed span starts between the two times, either way', () => {
    const start = 10 - SLOW_BEFORE_S;
    expect(slowStarts(touches, start - 0.05, start)).toBe(true);
    expect(slowStarts(touches, start, start + 0.05)).toBe(false);
    expect(slowStarts(touches, start + 0.05, start - 0.05)).toBe(true);
    expect(slowStarts(touches, 10.5, 11)).toBe(false);
    expect(slowStarts(touches, 5, 20)).toBe(true);
    expect(slowStarts([], 5, 20)).toBe(false);
  });
});

describe('stretchedTime', () => {
  const fps = 50;
  it('moves a frame every FINE_PX near the press, then at the bar scale with no skip', () => {
    expect(stretchedTime(2 * FINE_PX, 10, 0.1, fps)).toEqual({ time: frameTime(502, fps), nudge: 2 });
    const edge = stretchedTime(FINE_SPAN_PX, 10, 0.1, fps).time;
    const past = stretchedTime(FINE_SPAN_PX + 1, 10, 0.1, fps).time;
    expect(past - edge).toBeLessThan(0.11);
    expect(past).toBeGreaterThan(edge);
    expect(stretchedTime(-FINE_SPAN_PX - 10, 10, 0.1, fps).time).toBeCloseTo(10 - FINE_SPAN_PX / FINE_PX / fps - 1, 5);
  });
});

describe('stretchedX', () => {
  it('puts the time back under the pointer', () => {
    for (const dx of [-80, -FINE_SPAN_PX - 5, 30, 200]) {
      const t0 = frameTime(500, 50);
      expect(stretchedX(stretchedTime(dx, t0, 0.1, 50).time, t0, 0.1, 50)).toBeCloseTo(dx, 0);
    }
  });
});
