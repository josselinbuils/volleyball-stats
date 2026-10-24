type Lab = [number, number, number];

const channel = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const gamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/** Linear sRGB channels of #rrggbb. */
function linear(hex: string): [number, number, number] {
  return [1, 3, 5].map((k) => channel(parseInt(hex.slice(k, k + 2), 16) / 255)) as [number, number, number];
}

/** #rrggbb of linear sRGB channels, clipped to the gamut. */
function toHex(rgb: number[]): string {
  return `#${rgb.map((c) => Math.round(255 * gamma(Math.min(1, Math.max(0, c)))).toString(16).padStart(2, '0')).join('')}`;
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
export function oklab(hex: string): Lab {
  const [r, g, b] = linear(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function fromOklab([L, a, b]: Lab): string {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return toHex([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s]);
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

/** `hex` with its hue and chroma, darkened (light theme) or lightened (dark theme) until it stands
 * out from every one of `backgrounds` at the non-text contrast. */
export function display(hex: string, backgrounds: string[], dark: boolean): string {
  const [L, a, b] = oklab(hex);
  let out = hex;
  for (let step = 0; step <= 50 && backgrounds.some((bg) => contrast(out, bg) < MARK); step++) {
    out = fromOklab([L + (dark ? 1 : -1) * 0.02 * step, a, b]);
  }
  return out;
}

/** The two teams' colours on a theme's `backgrounds`: each one readable on them, team 2 swapped for
 * the fallback farthest from team 1 when the two look alike. */
export function teamColors(colours: [string, string], backgrounds: string[], dark: boolean): [string, string] {
  const one = display(colours[0], backgrounds, dark);
  let two = display(colours[1], backgrounds, dark);
  if (distance(one, two) < CLOSE) {
    const options = FALLBACKS.map((c) => display(c, backgrounds, dark));
    two = options.reduce((best, c) => (distance(one, c) > distance(one, best) ? c : best));
  }
  return [one, two];
}

/** Black or white, whichever reads better on `hex`. */
export function textOn(hex: string): string {
  return contrast(hex, '#141413') >= contrast(hex, '#ffffff') ? '#141413' : '#ffffff';
}
