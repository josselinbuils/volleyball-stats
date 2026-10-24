import { describe, expect, it } from 'vitest';
import { contrast, display, distance, teamColors, textOn } from '@/helpers/colors';

describe('team colours', () => {
  const light = ['#ffffff', '#ecebe5'];
  const dark = ['#1b1b1a', '#262624'];

  it('measures contrast as WCAG does', () => {
    expect(contrast('#ffffff', '#000000')).toBeCloseTo(21);
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 1);
  });

  it('darkens a white jersey on the light theme and lightens a navy one on the dark theme, keeping the hue', () => {
    const white = display('#f4f4f4', light, false);
    expect(Math.min(...light.map((bg) => contrast(white, bg)))).toBeGreaterThanOrEqual(3);
    expect(display('#f4f4f4', dark, true)).toBe('#f4f4f4');
    const navy = display('#1b2a4a', dark, true);
    expect(Math.min(...dark.map((bg) => contrast(navy, bg)))).toBeGreaterThanOrEqual(3);
    const [r, g, b] = [1, 3, 5].map((k) => parseInt(navy.slice(k, k + 2), 16));
    expect(b).toBeGreaterThan(r);
    expect(b).toBeGreaterThan(g);
    expect(display('#1b2a4a', light, false)).toBe('#1b2a4a');
  });

  it('keeps two distinct jerseys and swaps team 2 for a distinct colour when the two look alike', () => {
    for (const [bgs, isDark] of [[light, false], [dark, true]] as const) {
      const [white, navy] = teamColors(['#f4f4f4', '#1b2a4a'], [...bgs], isDark);
      expect(navy).toBe(display('#1b2a4a', [...bgs], isDark));
      expect(distance(white, navy)).toBeGreaterThan(0.12);
      const [black, blue] = teamColors(['#151515', '#1b2a4a'], [...bgs], isDark);
      expect(black).toBe(display('#151515', [...bgs], isDark));
      expect(distance(black, blue)).toBeGreaterThan(0.12);
    }
    expect(teamColors(['#d22630', '#7a1426'], light, false)).toEqual(['#d22630', '#7a1426']);
    const [red, darkRed] = teamColors(['#d22630', '#7a1426'], dark, true);
    expect(distance(red, darkRed)).toBeGreaterThan(0.12);
  });

  it('writes black on light colours and white on dark ones', () => {
    expect(textOn('#f4f4f4')).toBe('#141413');
    expect(textOn('#1b2a4a')).toBe('#ffffff');
  });
});
