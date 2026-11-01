import { describe, expect, it } from 'vitest';
import { rallyAt, rallyOf, withServes } from '@/components/Review/helpers/report';

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

describe('withServes', () => {
  it('starts a rally at a serve added before it, so the touches added after it are its own', () => {
    const rallies = withServes(
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
    expect(rallyOf(rallies, 36, 'pass')).toBe(1);
  });
});
