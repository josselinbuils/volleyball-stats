/** A player's hair and skin for the 3D figures, guessed from the video (`likeness.py`) and corrected in the
 * review; each field absent leaves the figure's made-up one. */
export interface Look {
  hair?: HairColour;
  style?: HairStyle;
  /** 1 (lightest) to SKINS.length. */
  skin?: number;
}

export type HairColour = 'black' | 'dark' | 'brown' | 'blond' | 'red' | 'grey';
export type HairStyle = 'bald' | 'short' | 'mid' | 'ponytail' | 'long';

/** The hair colours the figures wear, in the review's order (likeness.HAIRS). */
export const HAIRS: Record<HairColour, string> = {
  black: '#16110e',
  dark: '#3b2618',
  brown: '#6e4a2a',
  blond: '#d2ae6c',
  red: '#a2461f',
  grey: '#b9b5ae',
};

/** The hair styles, in the review's order (likeness.STYLES). */
export const STYLES: HairStyle[] = ['bald', 'short', 'mid', 'ponytail', 'long'];

/** The skin tones, lightest first (likeness.SKINS). */
export const SKINS = ['#f2d3bb', '#e2b48e', '#c48e63', '#94603c', '#5b3925'];

/** A look's own key, to tell when a figure must be made again. */
export const lookKey = (look: Look | undefined) => (look ? `${look.hair ?? ''}:${look.style ?? ''}:${look.skin ?? ''}` : '');
