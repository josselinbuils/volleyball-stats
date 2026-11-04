import { describe, expect, it } from 'vitest';
import { railAt, shiftOf, tickStep, zoomed } from '@/components/Review/helpers/timeline';

describe('tickStep', () => {
  it('spaces the labels at least 64 px apart, the longest step past it', () => {
    expect(tickStep(0.2)).toBe(600);
    expect(tickStep(1)).toBe(120);
    expect(tickStep(40)).toBe(2);
    expect(tickStep(0.01)).toBe(900);
  });
});

describe('shiftOf', () => {
  it('measures the move of the first row listed on both sides', () => {
    const before = new Map([
      ['r1', 0],
      ['r2', 450],
      ['t5', 490],
    ]);

    expect(
      shiftOf(
        before,
        new Map([
          ['r2', 0],
          ['t5', 40],
          ['r3', 90],
        ]),
      ),
    ).toBe(-450);
    expect(shiftOf(before, new Map([['r9', 0]]))).toBe(0);
  });
});

describe('zoomed', () => {
  it('stays between the whole match and the closest zoom', () => {
    expect(zoomed(1, 2, 0.5, 40)).toBe(2);
    expect(zoomed(1, 0.1, 0.5, 40)).toBe(0.5);
    expect(zoomed(30, 2, 0.5, 40)).toBe(40);
  });

  it("reaches a row's top at its time", () => {
    const rows = [
      { at: 10, top: 0, bottom: 20 },
      { at: 20, top: 40, bottom: 60 },
    ];

    expect(railAt([], 5)).toBe(0);
    expect(railAt(rows, 5)).toBe(0);
    expect(railAt(rows, 10)).toBe(0);
    expect(railAt(rows, 15)).toBe(20);
    expect(railAt(rows, 20)).toBe(60);
    expect(railAt(rows, 25)).toBe(60);
  });

  it("passes a row whose time comes after the next row's", () => {
    const rows = [
      { at: 0, top: 0, bottom: 20 },
      { at: 12, top: 100, bottom: 120 },
      { at: 10, top: 140, bottom: 160 },
      { at: 20, top: 240, bottom: 260 },
    ];

    expect(railAt(rows, 5)).toBe(50);
    expect(railAt(rows, 10)).toBe(140);
    expect(railAt(rows, 15)).toBe(190);
  });
});
