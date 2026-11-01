import { describe, expect, it } from 'vitest';
import { freeFrame, nextTouch, offGiven, pieceOf, rallyAt, rallyOf, runningScores, withAdded, withSplits } from '@/components/Review/helpers/report';

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

describe('freeFrame', () => {
  it('keeps a frame next to a touch, and moves on from one holding a touch', () => {
    expect(freeFrame([100], 101)).toBe(101);
    expect(freeFrame([100, 101], 100)).toBe(102);
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

  it('leaves "to replay" and the referee\'s error on the part of a rally keeping its key', () => {
    const out = withSplits([{ start: 10, end: 20, set: 1, winner: null, redo: true, wrongCall: true, key: 100 }], [150], 10);

    expect(out.map((r) => [r.key, r.redo, r.wrongCall])).toEqual([
      [100, true, true],
      [150, undefined, undefined],
    ]);
  });

  it('files a page touch under the part of its rally started by then', () => {
    const out = withSplits(rallies, [150], 10);

    expect([pieceOf(out, 0, 12), pieceOf(out, 0, 16), pieceOf(out, 0, 9.8), pieceOf(out, 1, 55)]).toEqual([0, 1, 0, 2]);
  });
});

describe('nextTouch', () => {
  it('follows the touch before as a rally goes, a serve by the server first', () => {
    expect(nextTouch(undefined, 2)).toEqual({ type: 'serve', team: 2 });
    expect(nextTouch({ type: 'serve', team: 1 }, 1)).toEqual({ type: 'pass', team: 2 });
    expect(nextTouch({ type: 'pass', team: 2 }, 1)).toEqual({ type: 'set', team: 2 });
    expect(nextTouch({ type: 'set', team: 2 }, 1)).toEqual({ type: 'attack', team: 2 });
    expect(nextTouch({ type: 'attack', team: 2 }, 1)).toEqual({ type: 'dig', team: 1 });
    expect(nextTouch({ type: 'relance', team: 1 }, 1)).toEqual({ type: 'dig', team: 2 });
    expect(nextTouch({ type: 'dig', team: 1 }, 1)).toEqual({ type: 'set', team: 1 });
    expect(nextTouch({ type: 'block', team: 1 }, 1)).toEqual({ type: 'dig', team: 1 });
  });
});

describe('runningScores', () => {
  it('counts each set from 0, a rally of no play or joined to the one before for nothing', () => {
    const scores = runningScores([
      { set: 1, winner: 1, skip: false },
      { set: 1, winner: 2, skip: true },
      { set: 1, winner: 2, skip: false },
      { set: 1, winner: null, skip: false },
      { set: 2, winner: 2, skip: false },
    ]);

    expect(scores).toEqual([[1, 0], null, [1, 1], [1, 1], [0, 1]]);
    expect(offGiven([1, 1, 1, 1, 2], scores, ['1-1', '1-0', null])).toEqual(new Map([[4, '1-0']]));
  });
});
