import { describe, expect, it } from 'vitest';
import { turnedTo } from '@/scene3d/turn';

describe('turnedTo', () => {
  it('turns part of the way in a frame, nearly all in a second', () => {
    const frame = turnedTo(0, 1, 1 / 60);
    expect(frame).toBeGreaterThan(0.05);
    expect(frame).toBeLessThan(0.3);
    expect(turnedTo(0, 1, 1)).toBeCloseTo(1, 2);
  });

  it('goes the short way round', () => {
    expect(turnedTo(3, -3, 1)).toBeGreaterThan(3);
  });
});
