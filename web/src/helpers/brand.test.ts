import { describe, expect, it } from 'vitest';
import { fitted } from './brand';

describe('brand', () => {
  it('shrinks pictures to their height, never enlarging them', () => {
    expect(fitted(1000, 500, 250)).toEqual([500, 250]);
    expect(fitted(100, 50, 250)).toEqual([100, 50]);
  });
});
