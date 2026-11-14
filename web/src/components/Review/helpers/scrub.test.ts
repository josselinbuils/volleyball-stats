import { describe, expect, it } from 'vitest';
import { coarse, FINE_PX, FINE_SPAN_PX, frameTime, nudgeOf } from '@/components/Review/helpers/scrub';

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
