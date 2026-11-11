import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import { changesLines } from '@/lib/hostedChanges';

describe('changesLines', () => {
  const t = ((key: string, options?: { defaultValue?: string; part?: string; keys?: string }) =>
    key === 'review.changedWhich' ? `${options?.part}: ${options?.keys}` : key === 'review.changed.views' ? 'framing' : (options?.defaultValue ?? key)) as TFunction;

  it('gives each cause its line, with which items changed, else how many', () => {
    const lines = changesLines(
      [
        { part: 'club', count: 1, keys: ['favicon'] },
        { part: 'people', count: 2, keys: ['Ana', 'Bob'] },
        { part: 'views', count: 2 },
        { part: 'ball3d', count: null },
        { part: 'code', count: null, keys: ['page', 'list'] },
      ],
      t,
    );

    expect(lines).toEqual(['club: favicon', 'people: Ana, Bob', 'framing (2)', 'ball3d', 'code: page, list']);
  });

  it('says nothing without changes', () => {
    expect(changesLines(null, t)).toBeUndefined();
    expect(changesLines([], t)).toBeUndefined();
  });
});
