import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import { changesLines } from '@/lib/hostedChanges';

describe('changesLines', () => {
  const t = ((key: string, options?: { defaultValue?: string; part?: string; keys?: string }) =>
    key === 'review.changedWhich' ? `${options?.part}: ${options?.keys}` : key === 'review.changed.views' ? 'framing' : (options?.defaultValue ?? key)) as TFunction;

  it('gives each cause its line, with which items changed, else how many, and the commits of the code below', () => {
    const lines = changesLines(
      [
        { part: 'club', count: 1, keys: ['favicon'] },
        { part: 'people', count: 2, keys: ['Ana', 'Bob'] },
        { part: 'views', count: 2 },
        { part: 'ball3d', count: null },
        { part: 'code', count: null, keys: ['page', 'list'], commits: ['the net drawn thinner', '+2'] },
      ],
      t,
    );

    expect(lines).toEqual([
      { text: 'club: favicon' },
      { text: 'people: Ana, Bob' },
      { text: 'framing (2)' },
      { text: 'ball3d' },
      { text: 'code: page, list', details: ['the net drawn thinner', '+2'] },
    ]);
  });

  it('says nothing without changes', () => {
    expect(changesLines(null, t)).toBeUndefined();
    expect(changesLines([], t)).toBeUndefined();
  });
});
