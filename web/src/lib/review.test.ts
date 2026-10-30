import { afterEach, describe, expect, it, vi } from 'vitest';
import { allMarked, marked } from '@/lib/review';

// review.ts reads window.REVIEW on import.
vi.hoisted(() => {
  Object.assign(globalThis, { window: {} });
});

describe('allMarked', () => {
  const pieces = [
    { track: 1, frame: 10 },
    { track: 2, frame: 20 },
  ];

  afterEach(() => marked.clear());

  it('holds once every picture is marked as someone else', () => {
    marked.set('1:10', null);
    expect(allMarked({ pieces })).toBe(false);
    marked.set('2:20', '1:3');
    expect(allMarked({ pieces })).toBe(true);
  });

  it('never holds for a player without pictures', () => {
    expect(allMarked({ pieces: [] })).toBe(false);
  });
});
