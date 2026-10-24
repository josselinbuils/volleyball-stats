import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { arrows } from '@/components/CourtChart/helpers/arrows';

describe('arrows', () => {
  const contact = (i: number, rally: number, type: string, x: number | null, y: number | null, result = 'play') =>
    ({ i, rally, type, x, y, result, t: i, side: 'left', zone: null, person: null }) as Contact;

  it('draws serves and attacks to the next touch with their outcome', () => {
    const all = [contact(0, 0, 'serve', -9, 0), contact(1, 0, 'pass', 6, 0), contact(2, 0, 'set', 2, 0), contact(3, 0, 'attack', 1, 0, 'point'), contact(4, 0, 'floor', -5, 0)];
    const out = arrows(all, all);
    expect(out.map((a) => [a.from.type, a.to.type, a.result, a.landing])).toEqual([
      ['serve', 'pass', 'play', false],
      ['attack', 'floor', 'point', true],
    ]);
    // The tip stops 0.4 m before a touch, 0.75 m before a landing, the line 0.3 m before the tip.
    expect(out[0].line).toEqual([-9, 0, 5.3, 0]);
    expect(out[0].head.split(' ')[0]).toBe('5.6,0');
    expect(out[1].line).toEqual([1, 0, -3.95, 0]);
  });

  it('skips a touch without a placed next touch in its rally', () => {
    const all = [contact(0, 0, 'serve', -9, 0), contact(1, 1, 'serve', 9, 0), contact(2, 1, 'floor', null, null)];
    expect(arrows(all, all)).toEqual([]);
  });

  it('only draws the shown touches, followed in the whole match', () => {
    const all = [contact(0, 0, 'serve', -9, 0), contact(1, 0, 'pass', 6, 0)];
    expect(arrows([all[0]], all)).toHaveLength(1);
    expect(arrows([all[1]], all)).toHaveLength(0);
  });
});
