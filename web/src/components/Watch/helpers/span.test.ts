import { describe, expect, it } from 'vitest';
import type { Rally } from '@/lib/match';
import { span } from '@/components/Watch/helpers/span';

describe('span', () => {
  const rally = (start: number, end: number) => ({ start, end }) as Rally;

  it('allows the whole video with every set', () => {
    expect(span([rally(10, 20)], true, 600)).toEqual({ start: 0, end: 600 });
  });

  it('allows a set from just before its first rally to just after its last', () => {
    expect(span([rally(100, 110), rally(300, 320)], false, 600)).toEqual({ start: 99, end: 321.5 });
    expect(span([rally(1, 5), rally(595, 599)], false, 600)).toEqual({ start: 0, end: 600 });
  });
});
