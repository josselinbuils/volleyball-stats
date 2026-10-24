import type { TFunction } from 'i18next';

export const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'floor', 'net'] as const;
/** The two teams, or without player tracks the two sides of the net: 1 left, 2 right. */
export const GROUPS = [1, 2] as const;

export type ActionType = (typeof TYPES)[number];
export type Side = 'left' | 'right';
export type Group = (typeof GROUPS)[number];
export type Result = 'point' | 'error' | 'play';

/** One touch of the ball, `i` its index in `contacts`, `track` the player track that played it and
 * `player` that player's number, `g` its team (its side without teams). */
export interface Contact {
  i: number;
  t: number;
  type: ActionType;
  side: Side;
  team: Group | null;
  g: Group;
  rally: number;
  set: number;
  x: number | null;
  y: number | null;
  zone: number | null;
  result: Result;
  track: number | null;
  player: number | null;
}

/** A rally, `left` the team on the left of the net, `flipped` when the teams play on the other ends
 * than at the first rally, `numbers` the number of each team's player tracks during it. */
export interface Rally {
  i: number;
  start: number;
  end: number;
  set: number;
  left: Group;
  flipped: boolean;
  numbers: Record<string, number>;
  contacts: Contact[];
}

export interface ZoneCell {
  zone: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A team as named in the pipeline: `name` null for the default one, `colour` its jersey colour,
 * detected or given. */
export interface Team {
  name: string | null;
  colour: string;
}

/** A club theme: colour tokens per colour scheme, as branding/NAME/brand.json holds them. */
export interface Brand {
  name: string;
  url?: string;
  logo?: string;
  font?: string;
  radius?: string;
  light: Record<string, string>;
  dark: Record<string, string>;
}

/** The match as data.js writes it. */
interface Data {
  name: string;
  video: string;
  poster?: string;
  fps: number;
  duration: number;
  teams: [Team, Team] | null;
  rallies: { start: number; end: number; set: number; left: Group | null; numbers: Record<string, number> }[];
  contacts: Omit<Contact, 'i' | 'g' | 'player'>[];
  zones: ZoneCell[];
  tracks: Record<string, { team: Group; jersey: number | null }>;
  brand?: Brand | null;
  /** yyyy-mm-dd, with teams. */
  date?: string | null;
  /** The title the user typed, null for the default one. */
  title?: string | null;
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
  tracks: data.tracks,
  brand: data.brand ?? null,
  date: data.date ?? null,
  title: data.title ?? null,
};
export const teams = data.teams;
export const hasTeams = teams !== null;
const firstLeft = data.rallies.find((r) => r.left !== null)?.left ?? 1;
export const rallies: Rally[] = data.rallies.map((r, i) => ({ ...r, i, left: r.left ?? firstLeft, flipped: (r.left ?? firstLeft) !== firstLeft, contacts: [] }));
export const contacts: Contact[] = data.contacts.map((c, i) => ({
  ...c,
  i,
  g: (hasTeams && c.team) || (c.side === 'left' ? 1 : 2),
  player: playerNumber(c.track, rallies[c.rally]),
}));
for (const c of contacts) {
  rallies[c.rally].contacts.push(c);
}
/** The set numbers of the match, in order. */
export const sets = [...new Set(rallies.map((r) => r.set))].sort((a, b) => a - b);

export type Placed = Contact & { x: number; y: number };

export function placed(c: Contact): c is Placed {
  return c.x !== null && c.y !== null;
}

/** A team's name (a side's without teams). */
export function groupName(t: TFunction, g: Group): string {
  if (!teams) {
    return t(g === 1 ? 'leftSide' : 'rightSide');
  }
  return teams[g - 1].name ?? t('team', { n: g });
}

/** The number a player track shows in a rally: its jersey number when known, else its number in
 * the rally. */
export function playerNumber(track: number | null, rally: Rally): number | null {
  if (track === null) {
    return null;
  }
  return match.tracks[track]?.jersey ?? rally.numbers[track] ?? null;
}

export const color = (key: string) => `var(--${key})`;
export const teamColor = (g: Group) => `var(--team${g})`;
/** The outline a team's colour needs on the current theme, transparent when none. */
export const teamRing = (g: Group) => `var(--team${g}-ring)`;
/** A team dot's outline: its ring, else the card's colour parting overlapping dots. */
export const teamEdge = (g: Group) => `var(--team${g}-edge)`;
