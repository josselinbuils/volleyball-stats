import { describe, expect, it } from 'vitest';
import { merged, seekLine, unshifted } from '@/components/Watch/helpers/seekBar';

describe('seekLine', () => {
  const colors = { played: 'P', heldColor: 'H', rest: 'R' };

  it('draws the played part, then the loaded stretches inside the bar, over the rest', () => {
    // The bar spans 100 s to 200 s; loaded: 50-120 s (cut at the bar's start), 150-160 s, 300-310 s (past its end).
    const line = seekLine(
      125,
      100,
      200,
      [
        [50, 120],
        [150, 160],
        [300, 310],
      ],
      colors,
    );
    expect(line.backgroundImage).toBe(
      'linear-gradient(P, P), linear-gradient(to right, transparent 0%, H 0% 20%, transparent 20%, transparent 50%, H 50% 60%, transparent 60%), linear-gradient(R, R)',
    );
    expect(line.backgroundSize).toBe('25% 4px, 100% 4px, 100% 4px');
  });

  it('has no loaded layer before anything loads', () => {
    expect(seekLine(0, 0, 10, [], colors).backgroundImage).toBe('linear-gradient(P, P), linear-gradient(R, R)');
  });
});

describe('unshifted', () => {
  it("takes the index's bytes out of Chromium's places", () => {
    // A 1000 s video whose first 10% is its index: Chromium puts its frames' 0-100 s at 100-190 s.
    const [[a, b]] = unshifted([[100, 190]], 1000, 0.1);
    expect(a).toBeCloseTo(0, 6);
    expect(b).toBeCloseTo(100, 6);
  });

  it('keeps the places inside the video', () => {
    expect(unshifted([[0, 50]], 1000, 0.1)).toEqual([[0, 0]]);
  });
});

describe('merged', () => {
  it('joins the ranges of both copies of the video that overlap or touch, in order', () => {
    expect(
      merged([
        [5, 8],
        [0, 2],
        [1, 3],
        [8, 9],
      ]),
    ).toEqual([
      [0, 3],
      [5, 9],
    ]);
  });
});
