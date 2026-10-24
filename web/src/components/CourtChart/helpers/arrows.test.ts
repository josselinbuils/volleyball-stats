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
    // The flight leaves the player and stops 0.45 m before a touch, 0.38 m before a landing.
    expect(out[0].curve).toMatch(/^M-9,0Q.* 5\.55,0$/);
    expect(out[1].curve).toMatch(/^M1,0Q.* -4\.62,0$/);
  });

  it('widens from the player to the end, thinner for a ball still in play', () => {
    const all = [contact(0, 0, 'serve', 0, 0), contact(1, 0, 'pass', 10, 0), contact(2, 1, 'attack', 0, 0, 'point'), contact(3, 1, 'floor', 10, 0)];
    const width = (shape: string, k: number) => {
      const pts = shape.slice(1, -1).split('L').map((p) => p.split(',').map(Number));
      return Math.hypot(pts[k][0] - pts[pts.length - 1 - k][0], pts[k][1] - pts[pts.length - 1 - k][1]);
    };
    const [play, point] = arrows(all, all);
    expect(width(point.shape, 0)).toBeCloseTo(0.06);
    expect(width(point.shape, 16)).toBeCloseTo(0.38);
    expect(width(play.shape, 16)).toBeCloseTo(0.228);
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
