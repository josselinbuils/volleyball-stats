import type { Brand, Team } from '@/lib/match';
import { teamColors, textOn } from '@/helpers/colors';

/** The page's backgrounds a mark sits on, card and court, per colour scheme. */
const BACKGROUNDS = { light: ['#ffffff', '#ecebe5'], dark: ['#1b1b1a', '#262624'] };
/** Group colours without teams: the two sides of the net. */
const SIDES: [string, string] = ['#2a78d6', '#e2612d'];
/** brand.json tokens to the page's CSS variables. */
const TOKENS: Record<string, string[]> = {
  accent: ['--primary', '--ring'],
  accentHover: ['--primary-hover'],
  accentText: ['--link'],
  header: ['--brand-header'],
  background: ['--background'],
  card: ['--card', '--popover'],
  text: ['--foreground', '--card-foreground', '--popover-foreground', '--secondary-foreground', '--accent-foreground'],
  muted: ['--muted-foreground'],
  cardShadow: ['--card-shadow'],
};

function block(teams: [Team, Team] | null, brand: Brand | null, scheme: 'light' | 'dark'): string {
  const backgrounds = brand ? [brand[scheme].card ?? BACKGROUNDS[scheme][0], BACKGROUNDS[scheme][1]] : BACKGROUNDS[scheme];
  const colours = teamColors(teams ? [teams[0].colour, teams[1].colour] : SIDES, backgrounds, scheme === 'dark');
  const vars = colours.flatMap((c, k) => [`--team${k + 1}:${c}`, `--team${k + 1}-text:${textOn(c)}`]);
  for (const [token, value] of Object.entries(brand?.[scheme] ?? {})) {
    vars.push(...(TOKENS[token] ?? []).map((name) => `${name}:${value}`));
  }
  return `:root{${vars.join(';')}}`;
}

/** The team colours, readable on each colour scheme, and the club theme, as a stylesheet; set before
 * the first render so nothing repaints. */
export function applyTheme(teams: [Team, Team] | null, brand: Brand | null) {
  const style = document.createElement('style');
  style.textContent = [
    block(teams, brand, 'light'),
    `@media (prefers-color-scheme: dark){${block(teams, brand, 'dark')}}`,
    brand?.font ? `html{font-family:${brand.font}}` : '',
    brand ? `[data-slot=card]{border-radius:${brand.radius ?? '10px'};box-shadow:var(--card-shadow);border-bottom:4px solid var(--primary)}` : '',
  ].join('');
  document.head.append(style);
  if (brand) {
    document.documentElement.dataset.brand = '';
  }
}
