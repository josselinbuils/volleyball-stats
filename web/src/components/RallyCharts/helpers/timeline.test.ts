import { describe, expect, it } from 'vitest';
import { setBreaks, span, ticks } from '@/components/RallyCharts/helpers/timeline';

describe('timeline', () => {
  const rallies = [
    { start: 5, end: 20, set: 1 },
    { start: 300, end: 320, set: 1 },
    { start: 700, end: 710, set: 2 },
  ];

  it("spans a set's rallies with a margin, within the video", () => {
    expect(span(rallies, 715)).toEqual([0, 715]);
    expect(span(rallies.slice(1), 1000)).toEqual([290, 720]);
    expect(span([], 60)).toEqual([0, 60]);
  });

  it('puts each set break halfway between the sets', () => {
    expect(setBreaks(rallies)).toEqual([{ time: 510, set: 2 }]);
    expect(setBreaks(rallies.slice(0, 2))).toEqual([]);
  });

  it('ticks round minutes, about six of them', () => {
    expect(ticks(0, 600)).toEqual([0, 120, 240, 360, 480, 600]);
    expect(ticks(290, 720)).toEqual([360, 480, 600, 720]);
  });
});
