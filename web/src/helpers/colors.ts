const channel = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

/** Linear sRGB channels of #rrggbb. */
function linear(hex: string): [number, number, number] {
  return [1, 3, 5].map((k) => channel(parseInt(hex.slice(k, k + 2), 16) / 255)) as [number, number, number];
}

/** #rrggbb mixed with black at `share` in OKLCH, as CSS `color-mix` makes it: OKLab scaled by `share`
 * is linear sRGB scaled by `share`³. */
export function shade(hex: string, share: number): string {
  const gamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
  return `#${linear(hex)
    .map((c) =>
      Math.round(255 * gamma(c * share ** 3))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`;
}

/** WCAG relative luminance. */
export function luminance(hex: string): number {
  const [r, g, b] = linear(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio of two colours. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** OKLab of #rrggbb. */
export function oklab(hex: string): [number, number, number] {
  const [r, g, b] = linear(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

/** Perceptual distance of two colours (OKLab): under ~0.12 two dots are hard to tell apart. */
export function distance(a: string, b: string): number {
  return Math.hypot(...oklab(a).map((v, k) => v - oklab(b)[k]));
}

/** Non-text contrast WCAG asks of a mark against its background. */
const MARK = 3;
const CLOSE = 0.12;
/** Team 2's colours when its own is too close to team 1's, first the farthest from it. */
const FALLBACKS = ['#e2612d', '#1baf7a', '#8e44ad', '#eda100', '#2a78d6'];
/** Outlines of a colour too close to the background: dark grey on the light theme, light grey on the dark one. */
const RINGS = { light: '#5f5d58', dark: '#a8a69d' };

/** The two teams' colours, the same on every theme: team 2's swapped for the fallback farthest from
 * team 1's when the two look alike. */
export function teamColors([one, two]: [string, string]): [string, string] {
  if (distance(one, two) >= CLOSE) {
    return [one, two];
  }
  return [one, FALLBACKS.reduce((best, c) => (distance(one, c) > distance(one, best) ? c : best))];
}

/** The outline `hex` needs to stand out from every one of a theme's `backgrounds`, null when it already does. */
export function ring(hex: string, backgrounds: string[], dark: boolean): string | null {
  return backgrounds.some((bg) => contrast(hex, bg) < MARK) ? RINGS[dark ? 'dark' : 'light'] : null;
}

/** Dark or white, whichever reads better on `hex`. */
export function textOn(hex: string): string {
  return contrast(hex, '#141413') >= contrast(hex, '#ffffff') ? '#141413' : '#ffffff';
}

/** A player card's share of its team colour where it is darkest, mixed with black in OKLCH. */
export const CARD_SHADE = 0.55;

/** `textOn` for a fill fading from `hex` to its mix with black at `share` in OKLCH (which scales its
 * luminance by `share`³): the text whose worst contrast along the way is the highest. */
export function textOnShade(hex: string, share: number): string {
  const top = luminance(hex);
  const ratio = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const worst = (text: string) => Math.min(ratio(top, luminance(text)), ratio(top * share ** 3, luminance(text)));
  return worst('#141413') >= worst('#ffffff') ? '#141413' : '#ffffff';
}
