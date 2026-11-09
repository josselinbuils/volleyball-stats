import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('locales', () => {
  const keys = (value: unknown, prefix = ''): string[] => (value && typeof value === 'object' ? Object.entries(value).flatMap(([k, v]) => keys(v, `${prefix}${k}.`)) : [prefix.slice(0, -1)]);
  const read = (locale: string): unknown => JSON.parse(readFileSync(new URL(`./${locale}.json`, import.meta.url), 'utf8'));

  it('hold text', () => {
    expect(keys(read('fr')).length).toBeGreaterThan(100);
    expect(keys(read('en')).length).toBeGreaterThan(100);
  });

  // JSON.parse keeps the last of two equal keys: the first text is lost without a word.
  const duplicates = (text: string): string[] => {
    const out: string[] = [];
    const stack: (Set<string> | null)[] = [];
    for (const [token, key, colon] of text.matchAll(/"((?:[^"\\]|\\.)*)"\s*(:)?|[{}[\]]/g)) {
      if (token === '{' || token === '[') {
        stack.push(token === '{' ? new Set() : null);
      } else if (token === '}' || token === ']') {
        stack.pop();
      } else if (colon) {
        const keys = stack.at(-1);
        if (keys?.has(key)) {
          out.push(key);
        }
        keys?.add(key);
      }
    }
    return out;
  };

  it('give each key once', () => {
    for (const locale of ['fr', 'en']) {
      expect(duplicates(readFileSync(new URL(`./${locale}.json`, import.meta.url), 'utf8'))).toEqual([]);
    }
    expect(duplicates('{"a": {"more": "x"}, "more": "y", "b": {"more": "z", "more": "w"}}')).toEqual(['more']);
  });

  it('name the same texts in both languages', () => {
    const fr = new Set(keys(read('fr')));
    const en = new Set(keys(read('en')));
    expect([...fr].filter((k) => !en.has(k)).filter((k) => !/_(one|other|many|zero|few|two)$/.test(k))).toEqual([]);
    expect([...en].filter((k) => !fr.has(k)).filter((k) => !/_(one|other|many|zero|few|two)$/.test(k))).toEqual([]);
  });
});
