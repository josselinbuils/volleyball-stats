import { describe, expect, it } from 'vitest';
import { onScreen } from '@/components/Watch/helpers/overlay';
import { WHOLE, cameraAt, throughCut, zoomOn } from '@/components/Watch/helpers/zoom';

describe('cameraAt', () => {
  // From 2 s, every 0.1 s: [0.5, 0.5, 1], then [0.4, 0.5, 1.5], then [0.4, 0.45, 2], written as framing.camera_spans does.
  const spans = [[2, 5000, 5000, 10000, -1000, 0, 5000, 0, -500, 5000]];

  it('reads the samples, added up from their changes', () => {
    const first = cameraAt(spans, 2);
    expect([first.x, first.y, first.zoom].map((v) => +v.toFixed(6))).toEqual([0.5, 0.5, 1]);
    const second = cameraAt(spans, 2.1);
    expect([second.x, second.y, second.zoom].map((v) => +v.toFixed(6))).toEqual([0.4, 0.5, 1.5]);
    const last = cameraAt(spans, 2.2);
    expect([last.x, last.y, last.zoom].map((v) => +v.toFixed(6))).toEqual([0.4, 0.45, 2]);
  });

  it('goes in a line between them, as the copies are cut', () => {
    const half = cameraAt(spans, 2.15);
    expect(half.y).toBeCloseTo(0.475, 6);
    expect(half.zoom).toBeCloseTo(1.75, 6);
  });

  it('shows the whole picture outside its runs', () => {
    expect(cameraAt(spans, 1.9)).toEqual(WHOLE);
    expect(cameraAt(spans, 2.3)).toEqual(WHOLE);
    expect(cameraAt([], 5)).toEqual(WHOLE);
  });
});

describe('throughCut', () => {
  it('draws a point of the picture where the cut copy shows it', () => {
    const cut = { x: 0.6, y: 0.4, zoom: 2 };
    const css = zoomOn({ x: 0.3, y: 0.6 }, 1600, 900, 2560, 1440, 1.5);
    const point = { x: 0.55, y: 0.45 };
    // In the copy: its fraction of the cut, then the page's own zoom.
    const inCopy = { x: (point.x - 0.35) / 0.5, y: (point.y - 0.15) / 0.5 };
    const expected = onScreen(1600, 900, 2560, 1440, css).at(inCopy);
    const drawn = onScreen(1600, 900, 2560, 1440, throughCut(css, cut, 1600, 900, 2560, 1440)).at(point);
    expect(drawn.x).toBeCloseTo(expected.x, 6);
    expect(drawn.y).toBeCloseTo(expected.y, 6);
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
