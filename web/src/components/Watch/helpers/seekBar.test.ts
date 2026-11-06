import { describe, expect, it } from 'vitest';
import { around, isDownload, merged, placer, seekLine, unshifted } from '@/components/Watch/helpers/seekBar';

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

describe('placer', () => {
  // A 100 s video: its frames from 10% of the file, the first 50 s in a fifth of it, the rest in the rest.
  const place = placer(100, [
    [0, 0.1],
    [50, 0.3],
    [90, 0.9],
  ]);

  it("reads Chromium's places back through the file's index", () => {
    // Chromium puts the byte at 30% of the file at 30 s: the index says 50 s; at 60%, 70 s; past the last point, the rest.
    expect([place(30), place(60), place(95)]).toEqual([50, 70, 95]);
  });

  it('puts the bytes before the frames at the start', () => {
    expect(place(5)).toBe(0);
  });
});

describe('unshifted', () => {
  // Chromium's places 10 s early: the bytes lag behind the time.
  const late = (t: number) => t + 10;

  it('reads every range back, the one around the copy ending no further than either reading', () => {
    expect(
      unshifted(
        [
          [40, 47],
          [70, 80],
        ],
        late,
        43,
      ),
    ).toEqual([
      [40, 47],
      [80, 90],
    ]);
  });
});

describe('isDownload', () => {
  // Chromium's places 30 s late: the index at the file's start.
  const early = (t: number) => t - 30;

  it("tells the copy's own growing download from its exact seconds and older downloads", () => {
    // At 100 s: its exact seconds 99-101 s, the estimate of its download 129-140 s (129-135 s before), an older one 160-170 s.
    const before: [number, number][] = [
      [129, 135],
      [160, 170],
    ];
    expect(
      (
        [
          [99, 101],
          [129, 140],
          [160, 170],
        ] as [number, number][]
      ).map((r) => isDownload(r, before, early, 100)),
    ).toEqual([false, true, false]);
  });

  it('is no download while it has not grown', () => {
    expect(isDownload([129, 140], [[129, 140]], early, 100)).toBe(false);
  });
});

describe('around', () => {
  it('keeps what is loaded from where the video stands and from the next clips', () => {
    const ranges: [number, number][] = [
      [10, 30],
      [101, 120],
      [300, 305],
    ];
    expect(around(ranges, [25, 100])).toEqual([
      [10, 30],
      [101, 120],
    ]);
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
