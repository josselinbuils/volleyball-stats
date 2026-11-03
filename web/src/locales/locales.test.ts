import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('locales', () => {
  const keys = (value: unknown, prefix = ''): string[] => (value && typeof value === 'object' ? Object.entries(value).flatMap(([k, v]) => keys(v, `${prefix}${k}.`)) : [prefix.slice(0, -1)]);
  const read = (locale: string): unknown => JSON.parse(readFileSync(new URL(`./${locale}.json`, import.meta.url), 'utf8'));

  it('hold text', () => {
    expect(keys(read('fr')).length).toBeGreaterThan(100);
    expect(keys(read('en')).length).toBeGreaterThan(100);
  });

  it('name the same texts in both languages', () => {
    const fr = new Set(keys(read('fr')));
    const en = new Set(keys(read('en')));
    expect([...fr].filter((k) => !en.has(k)).filter((k) => !/_(one|other|many|zero|few|two)$/.test(k))).toEqual([]);
    expect([...en].filter((k) => !fr.has(k)).filter((k) => !/_(one|other|many|zero|few|two)$/.test(k))).toEqual([]);
  });
});
