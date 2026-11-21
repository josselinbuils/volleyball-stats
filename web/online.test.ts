import { describe, expect, it } from 'vitest';
import { resolve } from 'node:path';
import { normalizePath } from 'vite';
import { keptTexts, namedKeys, sourceGraph } from './online';

const src = (path: string) => normalizePath(resolve(import.meta.dirname, 'src', path));

describe('sourceGraph', () => {
  it('follows the online pages to their own code and never to the app', () => {
    const page = sourceGraph(src('main.tsx'));
    expect(page.has(src('App.tsx'))).toBe(true);
    expect(page.has(src('reviewApp.tsx'))).toBe(false);
    const list = sourceGraph(src('matches.tsx'));
    expect(list.has(src('components/Matches.tsx'))).toBe(true);
    expect(list.has(src('components/AppMatches.tsx'))).toBe(false);
  });

  it('skips the type-only imports', () => {
    // Matches.tsx takes only the type Due from Update.tsx.
    expect(sourceGraph(src('matches.tsx')).has(src('components/Update.tsx'))).toBe(false);
  });
});

describe('namedKeys', () => {
  it('reads the literals and the starts of the keys built', () => {
    const named = namedKeys(["t('a.b'); t('c.' + x); t(`d.${x}`); t('e.')"]);
    expect([...named.exact]).toEqual(['a.b']);
    expect([...named.starts].sort()).toEqual(['c.', 'd.', 'e.']);
  });
});

describe('keptTexts', () => {
  it('keeps the texts named, their plural forms and their touch versions', () => {
    const texts = { a: { b: 'B', c: 'C', n_one: '1', n_other: 'N' }, d: { x: 'X' }, touch: { a: { b: 'tap B', c: 'tap C' } } };
    expect(keptTexts(texts, { exact: new Set(['a.b', 'a.n']), starts: new Set(['d.']) })).toEqual({
      a: { b: 'B', n_one: '1', n_other: 'N' },
      d: { x: 'X' },
      touch: { a: { b: 'tap B' } },
    });
  });
});
