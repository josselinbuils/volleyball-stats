import { describe, expect, it } from 'vitest';
import type { Rally } from '@/lib/match';
import { setScores, setsWon } from '@/components/Header/helpers/score';

describe('setScores', () => {
  const rally = (set: number, score: [number, number] | null) => ({ set, score }) as Rally;
  const rallies = [rally(1, [1, 0]), rally(1, [1, 1]), rally(2, [0, 1]), rally(2, [2, 1]), rally(3, null)];

  it('takes the given final scores, else the last rally of the set', () => {
    expect(setScores(rallies, ['25-21', null, null])).toEqual([
      { set: 1, score: [25, 21], final: true },
      { set: 2, score: [2, 1], final: false },
    ]);
  });

  it('keeps a given score for a set without a scored rally', () => {
    expect(setScores(rallies, [null, null, '19-25'])).toContainEqual({ set: 3, score: [19, 25], final: true });
  });

  it('counts the sets each team won', () => {
    expect(setsWon(setScores(rallies, ['25-21', '23-25', '20-20']))).toEqual([1, 1]);
  });
});
