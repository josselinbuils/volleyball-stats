import { describe, expect, it } from 'vitest';
import type { Rally } from '@/lib/match';
import { exactSet, justScored, scoreAt } from '@/components/Watch/helpers/score';

describe('scoreAt', () => {
  const rally = (start: number, set: number, score: [number, number] | null) => ({ start, end: start + 5, set, score }) as Rally;
  const rallies = [rally(10, 1, [1, 0]), rally(30, 1, [1, 1]), rally(100, 2, [0, 1]), rally(130, 2, [1, 1])];

  it('shows the score before a rally while it is played, and after it once it ends', () => {
    expect(scoreAt(rallies, 32, [])).toEqual({ set: 1, score: [1, 0], final: false });
    expect(scoreAt(rallies, 50, [])).toEqual({ set: 1, score: [1, 1], final: false });
  });

  it('starts each set at 0-0, before the match too', () => {
    expect(scoreAt(rallies, 0, [])).toEqual({ set: 1, score: [0, 0], final: false });
    expect(scoreAt(rallies, 101, [])).toEqual({ set: 2, score: [0, 0], final: false });
  });

  it('shows the given final score after a set is over', () => {
    expect(scoreAt(rallies, 50, ['25-21', null])).toEqual({ set: 1, score: [25, 21], final: true });
    expect(scoreAt(rallies, 200, ['25-21', null])).toEqual({ set: 2, score: [1, 1], final: false });
  });

  it('has no score without one', () => {
    expect(scoreAt([rally(10, 1, null)], 20, [])).toBeNull();
  });
});

describe('justScored', () => {
  const rallies = [
    { start: 10, end: 15, set: 1, score: [1, 0], winner: 1 },
    { start: 30, end: 35, set: 1, score: [1, 1], winner: 2 },
  ] as Rally[];

  it("names the team whose point just landed, for a while after the rally's end", () => {
    expect(justScored(rallies, 36, 1.5)).toBe(2);
    expect(justScored(rallies, 37, 1.5)).toBeNull();
    expect(justScored(rallies, 32, 1.5)).toBeNull();
    expect(justScored(rallies, 5, 1.5)).toBeNull();
  });
});

describe('exactSet', () => {
  const rallies = [
    { set: 1, score: [1, 0] },
    { set: 1, score: [1, 1] },
    { set: 2, score: [0, 1] },
  ] as Rally[];

  it('holds when a set adds up to its final score', () => {
    expect(exactSet(rallies, ['1-1', '25-20'], 1)).toBe(true);
    expect(exactSet(rallies, ['1-1', '25-20'], 2)).toBe(false);
    expect(exactSet(rallies, [], 1)).toBe(false);
  });
});
