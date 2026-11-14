import { describe, expect, it } from 'vitest';
import { markY } from '@/components/Story/helpers/marks';

describe('markY', () => {
  it('stands away from the line when free', () => {
    expect(markY(80, -1, [], 144, 14, 26)).toBe(66);
    expect(markY(80, 1, [], 144, 14, 26)).toBe(94);
  });

  it('takes the other side when its own is out of the chart', () => {
    expect(markY(20, -1, [], 144, 14, 26)).toBe(34);
  });

  it('keeps clear of the marks around it, inside the chart', () => {
    const taken: number[] = [];
    for (let k = 0; k < 4; k++) {
      taken.push(markY(80, -1, taken, 144, 14, 26));
    }
    expect(taken).toEqual([66, 94, 40, 120]);
    expect(taken.every((y) => y >= 14 && y <= 130)).toBe(true);
  });
});
