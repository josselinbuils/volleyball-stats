import { describe, expect, it } from 'vitest';
import { railAt, tickStep, zoomed } from '@/components/Review/helpers/timeline';

describe('tickStep', () => {
  it('spaces the labels at least 64 px apart, the longest step past it', () => {
    expect(tickStep(0.2)).toBe(600);
    expect(tickStep(1)).toBe(120);
    expect(tickStep(40)).toBe(2);
    expect(tickStep(0.01)).toBe(900);
  });
});

describe('zoomed', () => {
  it('stays between the whole match and the closest zoom', () => {
    expect(zoomed(1, 2, 0.5, 40)).toBe(2);
    expect(zoomed(1, 0.1, 0.5, 40)).toBe(0.5);
    expect(zoomed(30, 2, 0.5, 40)).toBe(40);
  });

  it('places the current time between the rows around it', () => {
    const rows = [
      { at: 10, top: 0, bottom: 20 },
      { at: 20, top: 40, bottom: 60 },
    ];

    expect(railAt([], 5)).toBe(0);
    expect(railAt(rows, 5)).toBe(0);
    expect(railAt(rows, 10)).toBe(10);
    expect(railAt(rows, 15)).toBe(30);
    expect(railAt(rows, 25)).toBe(60);
  });
});
