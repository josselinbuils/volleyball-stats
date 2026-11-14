import { describe, expect, it } from 'vitest';
import { AHEAD_S, ballAt, frameAt, smoothFrameAt, spring, zoomOn } from '@/components/Watch/helpers/zoom';

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

describe('frameAt', () => {
  const views: [number, number, number, number][] = [
    [0, 0.2, 0, 0.6],
    [10, 0, 0, 1],
  ];

  it("frames the review's view of the players", () => {
    expect(frameAt(views, 5, null)).toEqual({ x: 0.5, y: 0.3, zoom: 1 / 0.6 });
    expect(frameAt(views, 12, null)).toEqual({ x: 0.5, y: 0.5, zoom: 1 });
  });

  it('stays still while the ball is well inside', () => {
    expect(frameAt(views, 5, { x: 0.4, y: 0.3 })).toEqual(frameAt(views, 5, null));
  });

  it('moves just enough to keep the ball off its edges', () => {
    // The view spans 0.2 to 0.8: the ball at 0.85 needs its right edge at 0.85 + 0.15 × 0.6.
    const f = frameAt(views, 5, { x: 0.85, y: 0.3 });
    expect(f.x + 0.3).toBeCloseTo(0.94, 6);
    // Never past the picture's edge.
    expect(frameAt(views, 5, { x: 1, y: 0.3 }).x).toBeCloseTo(0.7, 6);
  });
});

describe('spring', () => {
  it('reaches its target without passing it', () => {
    const now = { x: 0, y: 0, zoom: 1 };
    const speed = { x: 0, y: 0, zoom: 0 };
    let most = 0;
    for (let k = 0; k < 120; k += 1) {
      spring(now, speed, { x: 1, y: 0, zoom: 1 }, 1 / 60);
      most = Math.max(most, now.x);
    }
    expect(now.x).toBeGreaterThan(0.99);
    expect(most).toBeLessThanOrEqual(1);
  });
});

describe('zoomOn', () => {
  it('puts the ball in the middle', () => {
    expect(zoomOn({ x: 0.5, y: 0.5 }, 1600, 900, 1920, 1080, 2)).toEqual({ scale: 2, x: -800, y: -450 });
  });

  it('keeps the picture filling its place near an edge', () => {
    const corner = zoomOn({ x: 0.05, y: 0.02 }, 1600, 900, 1920, 1080, 2);
    expect([corner.x, corner.y]).toEqual([-0, -0]);
    expect(zoomOn({ x: 1, y: 1 }, 1600, 900, 1920, 1080, 2)).toEqual({ scale: 2, x: -1600, y: -900 });
  });

  it('works on the letterboxed picture of a taller element', () => {
    // The picture 1000 × 562.5 in the middle of a 1000 × 1000 box (full screen on a tall screen).
    const v = zoomOn({ x: 0.5, y: 0.5 }, 1000, 1000, 1920, 1080, 2);
    expect(v.x).toBe(-500);
    expect(v.y).toBe(-500);
  });
});

describe('smoothFrameAt', () => {
  const views: [number, number, number, number][] = [
    [0, 0.2, 0, 0.6],
    [10, 0, 0, 0.6],
    [10.5, 0.4, 0, 0.6],
  ];

  it('holds a view away from any change', () => {
    expect(smoothFrameAt(views, 5, null).x).toBeCloseTo(0.5, 6);
  });

  it('sets off before a change', () => {
    expect(smoothFrameAt(views, 10 - AHEAD_S / 2, null).x).toBeLessThan(0.5);
    expect(smoothFrameAt(views, 10 - AHEAD_S - 0.1, null).x).toBeCloseTo(0.5, 6);
  });

  it('turns a view shown briefly into a small detour', () => {
    // Half a second at 0.3, between 0.5 and 0.7: the camera goes back left by a quarter of the way at most.
    const xs = Array.from({ length: 41 }, (_, k) => smoothFrameAt(views, 8 + k * 0.1, null).x);
    expect(Math.min(...xs)).toBeGreaterThan(0.5 - 0.2 / 4 - 1e-6);
    expect(xs[40]).toBeCloseTo(0.7, 6);
  });
});
