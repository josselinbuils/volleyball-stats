import { describe, expect, it } from 'vitest';
import { pieceOf, rallyAt, rallyOf, withAdded, withSplits } from '@/components/Review/helpers/report';

describe('rallyAt', () => {
  const rallies = [
    { start: 10, end: 20 },
    { start: 30, end: 40 },
  ];

  it('takes the rally the moment falls in, from a little before its start', () => {
    expect(rallyAt(rallies, 15)).toBe(0);
    expect(rallyAt(rallies, 29.8)).toBe(1);
  });

  it('takes the rally just ended between two, the first before any', () => {
    expect(rallyAt(rallies, 25)).toBe(0);
    expect(rallyAt(rallies, 50)).toBe(1);
    expect(rallyAt(rallies, 2)).toBe(0);
  });
});

describe('rallyOf', () => {
  const rallies = [
    { start: 10, end: 20 },
    { start: 40, end: 50 },
  ];

  it('files a serve outside the rallies under the next one, another touch under the one before', () => {
    expect(rallyOf(rallies, 35, 'serve')).toBe(1);
    expect(rallyOf(rallies, 5, 'serve')).toBe(0);
    expect(rallyOf(rallies, 35, 'dig')).toBe(0);
    expect(rallyOf(rallies, 15, 'serve')).toBe(0);
    expect(rallyOf(rallies, 60, 'serve')).toBe(1);
  });
});

describe('withAdded', () => {
  it('starts a rally at a serve added before it, so the touches added after it are its own', () => {
    const rallies = withAdded(
      [
        { start: 10, end: 20 },
        { start: 40, end: 50 },
      ],
      [
        { time: 35, type: 'serve' },
        { time: 36, type: 'pass' },
      ],
    );
    expect(rallies.map((r) => r.start)).toEqual([10, 35]);
    expect(rallies.map((r) => r.end)).toEqual([20, 50]);
    expect(rallyOf(rallies, 36, 'pass')).toBe(1);
  });
});

describe('withSplits', () => {
  const rallies = [
    { start: 10, end: 20, set: 1, winner: 1 as const, key: 100 },
    { start: 50, end: 60, set: 2, winner: 2 as const, key: 500 },
  ];

  it('starts a rally inside one or between two as the server does, the others keeping their key', () => {
    const out = withSplits(
      rallies,
      [15, 30, 50, 5].map((s) => s * 10),
      10,
    );

    expect(out.map((r) => [r.start, r.end, r.set, r.winner, r.key, r.origin, r.added])).toEqual([
      [5, 5, 1, null, 50, null, true],
      [10, 14.9, 1, null, 100, 0, false],
      [15, 20, 1, 1, 150, 0, true],
      [30, 30, 1, null, 300, null, true],
      [50, 60, 2, 2, 500, 1, false],
    ]);
  });

  it('files a page touch under the part of its rally started by then', () => {
    const out = withSplits(rallies, [150], 10);

    expect([pieceOf(out, 0, 12), pieceOf(out, 0, 16), pieceOf(out, 0, 9.8), pieceOf(out, 1, 55)]).toEqual([0, 1, 0, 2]);
  });
});
