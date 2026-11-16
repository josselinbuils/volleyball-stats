import { describe, expect, it } from 'vitest';
import { onScreen } from '@/components/Watch/helpers/overlay';
import { WHOLE, between, cameraAt, sampleNear, spring, throughCut, within, zoomOn } from '@/components/Watch/helpers/zoom';

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

describe('between', () => {
  it('goes from one view to the other by their widths', () => {
    const half = between({ x: 0.5, y: 0.5, zoom: 1 }, { x: 0.3, y: 0.3, zoom: 4 }, 0.5);
    expect(half.x).toBeCloseTo(0.4, 6);
    expect(1 / half.zoom).toBeCloseTo(0.625, 6);
  });
});

describe('within', () => {
  const cut = { x: 0.6, y: 0.5, zoom: 2 };

  it('is the whole copy for the view it was cut by', () => {
    const seen = within(cut, cut);
    expect([seen.x, seen.y, seen.zoom].map((v) => +v.toFixed(6))).toEqual([0.5, 0.5, 1]);
  });

  it('zooms further on a closer view, kept inside the cut', () => {
    const seen = within({ x: 0.8, y: 0.5, zoom: 4 }, cut);
    // Its quarter of the picture on the right half of the cut, 0.35 to 0.85: from 0.6 to 0.85 at most.
    expect(seen.zoom).toBeCloseTo(2, 6);
    expect(seen.x).toBeCloseTo((0.725 - 0.35) / 0.5, 6);
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

describe('spring', () => {
  it('reaches its target without passing it', () => {
    const now = { value: 0, speed: 0 };
    let most = 0;
    for (let k = 0; k < 120; k += 1) {
      spring(now, 1, 1 / 60);
      most = Math.max(most, now.value);
    }
    expect(now.value).toBeGreaterThan(0.99);
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

describe('sampleNear', () => {
  const ball = { samples: [1, 0.1, 0.5, 1.08, 0.2, 0.5, 1.5, 0.3, 0.4] };

  it('takes the nearest sample within its seconds', () => {
    expect(sampleNear(ball, 1.05, 0.1)).toEqual({ x: 0.2, y: 0.5 });
    expect(sampleNear(ball, 1.3, 0.1)).toBeNull();
  });
});
