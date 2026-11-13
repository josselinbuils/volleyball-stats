import { describe, expect, it } from 'vitest';
import { clampView, MAX_SCALE, zoomAt } from './zoom';

describe('zoomAt', () => {
  it('keeps the point zoomed on in place', () => {
    const z = zoomAt({ scale: 1, x: 0, y: 0 }, 2, { x: 30, y: 40 }, 100, 100);
    expect(z).toEqual({ scale: 2, x: -30, y: -40 });
    // The point (30, 40) of the box shows the same spot of the picture: (30 + 30) / 2 = 30.
    expect((30 - z.x) / z.scale).toBe(30);
  });

  it('never shows past the picture, nor zooms out of it or past the most', () => {
    expect(zoomAt({ scale: 1, x: 0, y: 0 }, 2, { x: 100, y: 100 }, 100, 100)).toEqual({ scale: 2, x: -100, y: -100 });
    expect(zoomAt({ scale: 2, x: -50, y: -50 }, 0.4, { x: 10, y: 10 }, 100, 100)).toEqual({ scale: 1, x: 0, y: 0 });
    expect(zoomAt({ scale: 6, x: 0, y: 0 }, 4, { x: 0, y: 0 }, 100, 100).scale).toBe(MAX_SCALE);
    expect(clampView({ scale: 2, x: 20, y: -500 }, 100, 100)).toEqual({ scale: 2, x: 0, y: -100 });
  });
});
