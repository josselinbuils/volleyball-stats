import type { Brand, Team } from '@/lib/match';
import { CARD_SHADE, ring, teamColors, textOn, textOnShade } from '@/helpers/colors';

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

/** A colour scheme's variables: each team's `-ring`, the outline its colour needs there (transparent
 * when none), and `-edge`, the dots' outline (that ring, else the card's colour parting overlapping
 * dots); then the club theme. */
function block(colours: string[], brand: Brand | null, scheme: 'light' | 'dark'): string {
  const backgrounds = brand ? [brand[scheme].card ?? BACKGROUNDS[scheme][0], BACKGROUNDS[scheme][1]] : BACKGROUNDS[scheme];
  const vars = colours.flatMap((c, k) => {
    const outline = ring(c, backgrounds, scheme === 'dark');
    return [`--team${k + 1}-ring:${outline ?? 'transparent'}`, `--team${k + 1}-edge:${outline ?? 'var(--card)'}`];
  });
  for (const [token, value] of Object.entries(brand?.[scheme] ?? {})) {
    vars.push(...(TOKENS[token] ?? []).map((name) => `${name}:${value}`));
  }
  return vars.join(';');
}

/** The team colours, outlined where a colour scheme needs it, and the club theme, as a stylesheet;
 * set before the first render so nothing repaints. */
export function applyTheme(teams: [Team, Team] | null, brand: Brand | null) {
  const colours = teamColors(teams ? [teams[0].colour, teams[1].colour] : SIDES);
  const fills = colours.flatMap((c, k) => [`--team${k + 1}:${c}`, `--team${k + 1}-text:${textOn(c)}`, `--team${k + 1}-card-text:${textOnShade(c, CARD_SHADE)}`]);
  const style = document.createElement('style');
  style.textContent = [
    `:root{${[...fills, block(colours, brand, 'light')].join(';')}}`,
    `.dark{${block(colours, brand, 'dark')}}`,
    brand?.font ? `html{font-family:${brand.font}}` : '',
    brand ? `[data-slot=card]{border-radius:${brand.radius ?? '10px'};box-shadow:var(--card-shadow);border-bottom:4px solid var(--primary)}` : '',
  ].join('');
  document.head.append(style);
  if (brand) {
    document.documentElement.dataset.brand = '';
  }
}
