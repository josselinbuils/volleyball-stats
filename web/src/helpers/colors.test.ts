import { describe, expect, it } from 'vitest';
import { contrast, distance, ring, teamColors, textOn } from '@/helpers/colors';

describe('team colours', () => {
  const light = ['#ffffff', '#ecebe5'];
  const dark = ['#1b1b1a', '#262624'];

  it('measures contrast as WCAG does', () => {
    expect(contrast('#ffffff', '#000000')).toBeCloseTo(21);
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 1);
  });

  it('keeps the jerseys and swaps team 2 for a distinct colour only when the two look alike', () => {
    expect(teamColors(['#f4f4f4', '#1b2a4a'])).toEqual(['#f4f4f4', '#1b2a4a']);
    expect(teamColors(['#d22630', '#7a1426'])).toEqual(['#d22630', '#7a1426']);
    const [black, other] = teamColors(['#151515', '#1b2a4a']);
    expect(black).toBe('#151515');
    expect(distance(black, other)).toBeGreaterThan(0.12);
  });

  it('outlines white in dark grey on the light theme and navy in light grey on the dark theme', () => {
    expect(ring('#f4f4f4', light, false)).toBe('#5f5d58');
    expect(ring('#f4f4f4', dark, true)).toBeNull();
    expect(ring('#1b2a4a', dark, true)).toBe('#a8a69d');
    expect(ring('#151515', dark, true)).toBe('#a8a69d');
    expect(ring('#1b2a4a', light, false)).toBeNull();
  });

  it('does not outline a colour that stands out from every background', () => {
    expect(ring('#d22630', light, false)).toBeNull();
    expect(ring('#2a78d6', dark, true)).toBeNull();
    // Fine on the card, too pale on the court.
    expect(ring('#c8c8c8', ['#1b1b1a', '#c0c0c0'], true)).toBe('#a8a69d');
  });

  it('gives the outline at least the non-text contrast against the background', () => {
    for (const bg of light) {
      expect(contrast('#5f5d58', bg)).toBeGreaterThanOrEqual(3);
    }
    for (const bg of dark) {
      expect(contrast('#a8a69d', bg)).toBeGreaterThanOrEqual(3);
    }
  });

  it('writes dark on light fills and white on dark ones, whichever contrasts more', () => {
    expect(textOn('#f4f4f4')).toBe('#141413');
    expect(textOn('#eda100')).toBe('#141413');
    expect(textOn('#1b2a4a')).toBe('#ffffff');
    expect(textOn('#d22630')).toBe('#ffffff');
    for (const fill of ['#f4f4f4', '#eda100', '#1b2a4a', '#d22630', '#808080']) {
      const other = textOn(fill) === '#ffffff' ? '#141413' : '#ffffff';
      expect(contrast(textOn(fill), fill)).toBeGreaterThanOrEqual(contrast(other, fill));
    }
  });
});
