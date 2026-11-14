import { describe, expect, it } from 'vitest';
import { coarse, FINE_PX, FINE_SPAN_PX, frameTime, nearTouch, nudgeOf, SLOW_AFTER_S, SLOW_BEFORE_S, slowStarts } from '@/components/Review/helpers/scrub';

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

describe('nearTouch', () => {
  const touches = [10, 12, 20];
  it('holds from SLOW_BEFORE_S before a touch to SLOW_AFTER_S after it', () => {
    expect(nearTouch(touches, 10 - SLOW_BEFORE_S - 0.01)).toBe(false);
    expect(nearTouch(touches, 10 - SLOW_BEFORE_S)).toBe(true);
    expect(nearTouch(touches, 10)).toBe(true);
    expect(nearTouch(touches, 10 + SLOW_AFTER_S)).toBe(true);
    expect(nearTouch(touches, 10 + SLOW_AFTER_S + 0.01)).toBe(false);
    expect(nearTouch(touches, 12.1)).toBe(true);
    expect(nearTouch(touches, 25)).toBe(false);
    expect(nearTouch([], 10)).toBe(false);
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
