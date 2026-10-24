import { describe, expect, it } from 'vitest';
import { boxAt } from '@/components/Review/helpers/box';

describe('boxAt', () => {
  const clip = { start: 1, end: 2, boxes: [[1, 0, 0, 10, 20], [1.5, 5, 0, 15, 20]] as [number, number, number, number, number][] };

  it('takes the nearest box inside the clip', () => {
    expect(boxAt(clip, 1.4)).toEqual([5, 0, 15, 20]);
  });

  it('has no box outside the clip', () => {
    expect(boxAt(clip, 0.5)).toBeNull();
    expect(boxAt(clip, 2.5)).toBeNull();
  });
});
