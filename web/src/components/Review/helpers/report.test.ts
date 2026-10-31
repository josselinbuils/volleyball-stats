import { describe, expect, it } from 'vitest';
import { rallyAt } from '@/components/Review/helpers/report';

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
