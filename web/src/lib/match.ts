import type { TFunction } from 'i18next';

export const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'floor', 'net'] as const;
/** The two teams, or without player tracks the two sides of the net: 1 left, 2 right. */
export const GROUPS = [1, 2] as const;

export type ActionType = (typeof TYPES)[number];
export type Side = 'left' | 'right';
export type Group = (typeof GROUPS)[number];
export type Result = 'point' | 'error' | 'play';

/** One touch of the ball, `i` its index in `contacts`, `g` its team (its side without teams). */
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
  /** Key of the attributed player in `match.people`. */
  person: number | null;
  /** The number that player shows. */
  player: number | null;
  /** That player's name, when the user gave one. */
  name: string | null;
  /** For an ace, key of the receiver who missed it: the review's answer, else the nearest to where it
   * landed; null when the review says no one did, absent when unknown. */
  receiver?: number | null;
}

/** A rally, `left` the team on the left of the net, `flipped` when the teams play on the other ends
 * than at the first rally, `winner` its estimated winner and `score` the estimated score of its set
 * after it (team 1, team 2), null without teams. */
export interface Rally {
  i: number;
  start: number;
  end: number;
  set: number;
  left: Group;
  flipped: boolean;
  winner: Group | null;
  score: [number, number] | null;
  contacts: Contact[];
}

/** A player on the page: an identity for the whole match with its `number` in its team, or a player
 * track without one (`number` null); `name` and `jersey` as the user gave them. */
export interface Person {
  team: Group;
  number: number | null;
  jersey: number | null;
  name?: string | null;
  /** A picture of them from the video, beside data.js. */
  photo?: string;
  /** Seconds on the court during the rallies, by set number. */
  seconds?: Record<string, number>;
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
export interface Sponsor {
  name: string;
  logo?: string;
  background: string;
  text?: string;
}

export interface Brand {
  name: string;
  url?: string;
  logo?: string;
  font?: string;
  radius?: string;
  /** Boards in the 3D view: the name, a picture (a data: URL), their colours; without a text colour, the picture alone. */
  sponsors?: Sponsor[];
  light: Record<string, string>;
  dark: Record<string, string>;
}

/** The match as data.js writes it. */
interface Data {
  name: string;
  /** The video's file, null when the page holds none. */
  video: string | null;
  /** Its AV1 copy, lighter, played first where the browser can. */
  av1?: string | null;
  /** On a page without the video, where the same page with it is, behind a password. */
  videoPage?: string | null;
  /** Where viewers send what they found wrong in a moment, null to not ask. */
  feedback?: string | null;
  poster?: string;
  fps: number;
  duration: number;
  teams: [Team, Team] | null;
  rallies: { start: number; end: number; set: number; left: Group | null; winner?: Group | null; score?: [number, number] | null }[];
  contacts: Omit<Contact, 'i' | 'g' | 'player' | 'name'>[];
  zones: ZoneCell[];
  people: Record<string, Person>;
  /** Each set's final score as the user gave it, "25-21" team 1 first, null when unknown. */
  scores?: (string | null)[] | null;
  brand?: Brand | null;
  /** yyyy-mm-dd, with teams. */
  date?: string | null;
  /** The title the user typed, null for the default one. */
  title?: string | null;
  /** The build's hash, in the unhashed scripts' URLs. */
  v?: string;
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
  av1: data.av1 ?? null,
  videoPage: data.videoPage ?? null,
  feedback: data.feedback ?? null,
  poster: data.poster,
  fps: data.fps,
  duration: data.duration,
  zones: data.zones,
  people: data.people,
  scores: data.scores ?? [],
  brand: data.brand ?? null,
  date: data.date ?? null,
  title: data.title ?? null,
};
/** `file`, beside the page, at this build's URL: a cache never serves another build's. */
export const versioned = (file: string) => (data.v ? `${file}?v=${data.v}` : file);
export const teams = data.teams;
export const hasTeams = teams !== null;
const firstLeft = data.rallies.find((r) => r.left !== null)?.left ?? 1;
export const rallies: Rally[] = data.rallies.map((r, i) => ({
  ...r,
  i,
  left: r.left ?? firstLeft,
  flipped: (r.left ?? firstLeft) !== firstLeft,
  winner: r.winner ?? null,
  score: r.score ?? null,
  contacts: [],
}));
export const contacts: Contact[] = data.contacts.map((c, i) => ({
  ...c,
  i,
  g: (hasTeams && c.team) || (c.side === 'left' ? 1 : 2),
  player: playerNumber(c.person),
  name: c.person === null ? null : (data.people[c.person]?.name ?? null),
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

/** The number a player shows: their jersey number when known, else their number for the match. */
export function playerNumber(person: number | null): number | null {
  if (person === null) {
    return null;
  }
  return match.people[person]?.jersey ?? match.people[person]?.number ?? null;
}

/** Whether the user named any player. */
export const hasNames = Object.values(data.people).some((p) => p.name);

/** A player in text: their name, else their number ("no. 4"); null when neither is known. */
export function playerLabel(t: TFunction, person: number | null): string | null {
  const name = person === null ? null : match.people[person]?.name;
  const n = playerNumber(person);
  return name || (n === null ? null : t('player', { n }));
}

export const color = (key: string) => `var(--${key})`;
export const teamColor = (g: Group) => `var(--team${g})`;
/** The outline a team's colour needs on the current theme, transparent when none. */
export const teamRing = (g: Group) => `var(--team${g}-ring)`;
/** A team dot's outline: its ring, else the card's colour parting overlapping dots. */
export const teamEdge = (g: Group) => `var(--team${g}-edge)`;
