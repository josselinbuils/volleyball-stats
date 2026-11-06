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

  it('leaves out the parts and gaps of a few pixels', () => {
    // On a 1000 s bar: 0.2 s loaded alone, and two parts 0.2 s apart drawn as one.
    const line = seekLine(
      0,
      0,
      1000,
      [
        [100, 100.2],
        [500, 520],
        [520.2, 540],
      ],
      colors,
    );
    expect(line.backgroundImage).toBe('linear-gradient(P, P), linear-gradient(to right, transparent 50%, H 50% 54%, transparent 54%), linear-gradient(R, R)');
  });

  it('has no loaded layer before anything loads', () => {
    expect(seekLine(0, 0, 10, [], colors).backgroundImage).toBe('linear-gradient(P, P), linear-gradient(R, R)');
  });
});

describe('unshifted', () => {
  // A 100 s video: its frames from 10% of the file, the first 50 s in a fifth of it, the rest in the rest.
  const index: [number, number][] = [
    [0, 0.1],
    [50, 0.3],
    [90, 0.9],
  ];

  it("reads Chromium's places back through the file's index", () => {
    // Chromium puts the byte at 30% of the file at 30 s: the index says 50 s; at 60%, 70 s; past the last point, the rest.
    expect(
      unshifted(
        [
          [30, 60],
          [95, 100],
        ],
        100,
        index,
        -1,
      ),
    ).toEqual([
      [50, 70],
      [95, 100],
    ]);
  });

  it('puts the bytes before the frames at the start', () => {
    expect(unshifted([[0, 5]], 100, index, -1)).toEqual([[0, 0]]);
  });

  it('leaves where the copy stands as read', () => {
    expect(unshifted([[40, 47]], 100, index, 43)).toEqual([[40, 47]]);
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
