import { describe, expect, it } from 'vitest';
import { tickStep, zoomed } from '@/components/Review/helpers/timeline';

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
});
