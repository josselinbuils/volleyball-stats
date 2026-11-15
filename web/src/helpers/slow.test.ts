import { describe, expect, it } from 'vitest';
import { SLOW_AFTER_S, SLOW_BEFORE_S, SOUND_FADE_S, fadedVolume, nearTouch } from '@/helpers/slow';

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

describe('fadedVolume', () => {
  it('fades the sound out while slowed and back after, over SOUND_FADE_S', () => {
    expect(fadedVolume(1, true, SOUND_FADE_S / 2)).toBeCloseTo(0.5);
    expect(fadedVolume(0.5, true, SOUND_FADE_S)).toBe(0);
    expect(fadedVolume(0, false, SOUND_FADE_S / 4)).toBeCloseTo(0.25);
    expect(fadedVolume(0.9, false, 1)).toBe(1);
    expect(fadedVolume(1, false, -1)).toBe(1);
  });
});
