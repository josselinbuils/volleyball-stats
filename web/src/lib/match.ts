export const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'floor', 'net'] as const;
export const SIDES = ['left', 'right'] as const;

export type ActionType = (typeof TYPES)[number];
export type Side = (typeof SIDES)[number];
export type Result = 'point' | 'error' | 'play';

/** One touch of the ball, `i` its index in `contacts`, `track` the player track that played it. */
export interface Contact {
  i: number;
  t: number;
  type: ActionType;
  side: Side;
  rally: number;
  x: number | null;
  y: number | null;
  zone: number | null;
  result: Result;
  track: number | null;
}

export interface Rally {
  i: number;
  start: number;
  end: number;
  contacts: Contact[];
}

export interface ZoneCell {
  zone: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Player feet sampled every `step` frames: a span's samples start at sample index `from`, each
 * one the flat [x, y, ...] court positions of the left team, then of the right team. */
export interface Players {
  step: number;
  spans: { from: number; samples: number[][][] }[];
}

/** The match as data.js writes it. */
interface Data {
  name: string;
  video: string;
  poster?: string;
  fps: number;
  duration: number;
  rallies: { start: number; end: number }[];
  contacts: Omit<Contact, 'i'>[];
  zones: ZoneCell[];
  players: Players;
}

declare global {
  interface Window {
    MATCH: Data;
  }
}

const data = window.MATCH;

export const match = {
  name: data.name,
  video: data.video,
  poster: data.poster,
  fps: data.fps,
  duration: data.duration,
  zones: data.zones,
  players: data.players,
};
export const contacts: Contact[] = data.contacts.map((c, i) => ({ ...c, i }));
export const rallies: Rally[] = data.rallies.map((r, i) => ({ ...r, i, contacts: [] }));
for (const c of contacts) {
  rallies[c.rally].contacts.push(c);
}
/** The action types the match has, in TYPES order. */
export const present = TYPES.filter((type) => contacts.some((c) => c.type === type));

export type Placed = Contact & { x: number; y: number };

export function placed(c: Contact): c is Placed {
  return c.x !== null && c.y !== null;
}

/** Type colours on which white letters are unreadable. */
export const DARK_TEXT = new Set<ActionType>(['pass', 'set', 'attack', 'relance', 'floor']);

export const color = (key: string) => `var(--${key})`;
