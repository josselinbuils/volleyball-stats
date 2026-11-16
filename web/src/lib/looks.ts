/** A player's hair and skin for the 3D figures, guessed from their card's picture (`likeness.py`), the hair colour
 * correctable and the figure, a man's or a woman's, set in the review's Names tab; each field absent leaves the figure's made-up one. */
export interface Look {
  hair?: Hair;
  style?: HairStyle;
  /** 1 (lightest) to SKINS.length. */
  skin?: number;
  figure?: Figure;
}

export type HairColour = 'black' | 'dark' | 'brown' | 'blond' | 'red' | 'grey';
/** A colour, or bald: set in the Names tab only, never guessed. */
export type Hair = HairColour | 'bald';
export type HairStyle = 'short' | 'mid' | 'ponytail' | 'long';
export type Figure = 'man' | 'woman';

/** The hair colours the figures wear (likeness.HAIRS). */
export const HAIRS: Record<HairColour, string> = {
  black: '#16110e',
  dark: '#3b2618',
  brown: '#6e4a2a',
  blond: '#d2ae6c',
  red: '#a2461f',
  grey: '#b9b5ae',
};

/** The skin tones, lightest first (likeness.SKINS). */
export const SKINS = ['#f2d3bb', '#e2b48e', '#c48e63', '#94603c', '#5b3925'];

/** The figures, in the Names tab's order (likeness.FIGURES). */
export const FIGURES: Figure[] = ['man', 'woman'];

/** A look's own key, to tell when a figure must be made again. */
export const lookKey = (look: Look | undefined) => (look ? `${look.hair ?? ''}:${look.style ?? ''}:${look.skin ?? ''}:${look.figure ?? ''}` : '');
