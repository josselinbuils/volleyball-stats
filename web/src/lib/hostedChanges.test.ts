import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import { changesLabel } from '@/lib/hostedChanges';

describe('changesLabel', () => {
  const t = ((key: string) => key.replace('review.changed.', '')) as TFunction;

  it('names the known parts with their count, then the rest in one word', () => {
    const label = changesLabel(
      [
        { part: 'contacts', count: 3 },
        { part: 'views', count: 2 },
        { part: 'index', count: 1 },
        { part: 'code', count: null },
      ],
      t,
    );

    expect(label).toBe('contacts (3) · code · other');
  });

  it('says nothing without changes', () => {
    expect(changesLabel(null, t)).toBeUndefined();
    expect(changesLabel([], t)).toBeUndefined();
  });
});
