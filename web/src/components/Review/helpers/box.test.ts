import { describe, expect, it } from 'vitest';
import { boxAt, viewAt } from '@/components/Review/helpers/box';

describe('boxAt', () => {
  const clip = {
    start: 1,
    end: 2,
    boxes: [
      [1, 0, 0, 10, 20],
      [1.5, 5, 0, 15, 20],
    ] as [number, number, number, number, number][],
  };

  it('takes the nearest box inside the clip', () => {
    expect(boxAt(clip, 1.4)).toEqual([5, 0, 15, 20]);
  });

  it('has no box outside the clip', () => {
    expect(boxAt(clip, 0.5)).toBeNull();
    expect(boxAt(clip, 2.5)).toBeNull();
  });
});

describe('viewAt', () => {
  // A 100 px tall player walking right across a 1600 x 900 frame.
  const clip = {
    start: 0,
    end: 2,
    boxes: [
      [0, 100, 400, 140, 500],
      [1, 700, 400, 740, 500],
      [2, 1500, 400, 1540, 500],
    ] as [number, number, number, number, number][],
  };

  it('spans 4 player heights at the frame aspect ratio, centered on the player', () => {
    expect(viewAt(clip, 1, 1600, 900)).toEqual({ x: 720 - 400 / 0.5625 / 2, y: 250, w: 400 / 0.5625, h: 400 });
  });

  it('stays inside the frame', () => {
    expect(viewAt(clip, 0, 1600, 900).x).toBe(0);
    expect(viewAt(clip, 2, 1600, 900).x).toBeCloseTo(1600 - 400 / 0.5625);
  });

  it('shows the whole frame without boxes', () => {
    expect(viewAt({ start: 0, end: 1, boxes: [] }, 0, 1600, 900)).toEqual({ x: 0, y: 0, w: 1600, h: 900 });
  });
});
