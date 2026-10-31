import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import { pointSplit, setScores, setsWon } from '@/components/Header/helpers/score';

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

describe('pointSplit', () => {
  const touch = (type: string, g: number, result: string) => ({ type, g, result }) as Contact;
  const rally = (winner: number | null, ...contacts: Contact[]) => ({ winner, contacts }) as Rally;

  it("splits a team's rallies won by its last touch: its own point or the other team's fault", () => {
    const ace = touch('serve', 1, 'point');
    const out = touch('attack', 2, 'error');
    const rallies = [rally(1, ace, touch('floor', 2, 'play')), rally(1, touch('serve', 1, 'play'), out), rally(1), rally(2, touch('attack', 2, 'point'))];
    expect(pointSplit(rallies, 1)).toEqual({ direct: [ace], faults: [out] });
  });
});
