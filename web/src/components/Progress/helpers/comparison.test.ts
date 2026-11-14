import { describe, expect, it } from 'vitest';
import { compared } from './comparison';

describe('compared', () => {
  it('sorts the measures by their change', () => {
    const before = { up: [1, 2], down: [3, 4], still: [5, 6] } as Record<string, [number, number]>;
    const after = { up: [2, 2], down: [2, 4], still: [5, 6] } as Record<string, [number, number]>;
    expect(compared({ before, after }, ['up', 'down', 'still'])).toEqual({ better: ['up'], worse: ['down'], same: 1 });
  });

  it('compares shares when the totals differ', () => {
    const before = { a: [1, 2], b: [1, 2] } as Record<string, [number, number]>;
    const after = { a: [2, 4], b: [2, 3] } as Record<string, [number, number]>;
    expect(compared({ before, after }, ['a', 'b'])).toEqual({ better: ['b'], worse: [], same: 1 });
  });

  it('leaves out a measure missing or empty on either side', () => {
    const before = { empty: [0, 0], gone: [1, 1] } as Record<string, [number, number]>;
    const after = { empty: [1, 1], fresh: [1, 1] } as Record<string, [number, number]>;
    expect(compared({ before, after }, ['empty', 'gone', 'fresh', 'unknown'])).toEqual({ better: [], worse: [], same: 0 });
  });
});
