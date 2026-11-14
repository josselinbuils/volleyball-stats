import { describe, expect, it } from 'vitest';
import { nearTouch, SLOW_AFTER_S, SLOW_BEFORE_S } from '@/helpers/slow';

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
