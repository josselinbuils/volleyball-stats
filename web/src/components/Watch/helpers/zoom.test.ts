import { describe, expect, it } from 'vitest';
import { ballAt, zoomOn } from '@/components/Watch/helpers/zoom';

describe('ballAt', () => {
  // 10 fps: a sample every frame from 1 s to 2 s, the ball moving right.
  const ball = { fps: 10, samples: Array.from({ length: 11 }, (_, k) => [10 + k, 0.1 + k * 0.01, 0.5]).flat() };

  it('averages the samples within half a second', () => {
    const at = ballAt(ball, 1.5)!;
    expect(at.x).toBeCloseTo(0.15, 6);
    expect(at.y).toBeCloseTo(0.5, 6);
  });

  it('is null with no sample near', () => {
    expect(ballAt(ball, 3)).toBeNull();
  });
});

describe('zoomOn', () => {
  it('puts the ball in the middle', () => {
    expect(zoomOn({ x: 0.5, y: 0.5 }, 1600, 900, 1920, 1080)).toEqual({ scale: 2, x: -800, y: -450 });
  });

  it('keeps the picture filling its place near an edge', () => {
    const corner = zoomOn({ x: 0.05, y: 0.02 }, 1600, 900, 1920, 1080);
    expect([corner.x, corner.y]).toEqual([-0, -0]);
    expect(zoomOn({ x: 1, y: 1 }, 1600, 900, 1920, 1080)).toEqual({ scale: 2, x: -1600, y: -900 });
  });

  it('works on the letterboxed picture of a taller element', () => {
    // The picture 1000 × 562.5 in the middle of a 1000 × 1000 box (full screen on a tall screen).
    const v = zoomOn({ x: 0.5, y: 0.5 }, 1000, 1000, 1920, 1080);
    expect(v.x).toBe(-500);
    expect(v.y).toBe(-500);
  });
});
