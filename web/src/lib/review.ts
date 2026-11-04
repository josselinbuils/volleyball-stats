import i18n from 'i18next';
import type { Group } from '@/lib/match';

/** A piece of video with a player's box ([seconds, x1, y1, x2, y2] in video pixels) over it. */
export interface Clip {
  start: number;
  end: number;
  /** Seconds played before and after it, AROUND without. */
  around?: number;
  /** The playback rate inside it, at most, the context around played at the speed picked. */
  slow?: number;
  boxes: [number, number, number, number, number][];
}

/** A piece of a player's track, as answers refer to it: its track and a frame. */
export interface Piece {
  track: number;
  frame: number;
}

/** An identity a question offers, with pictures of their clearest moments and the pieces they come from. */
export interface Choice {
  identity: number;
  crops: string[];
  pieces: Piece[];
}

/** A doubt of the identity step: who an outlined piece of track is (`piece`), or whether two
 * identities never seen together are one player (`merge`, `other` the second one's clip); or who
 * made a doubtful touch (`touch`: its `action` at `time`, the ball outlined, why it is asked and
 * the player it is given to, `proposed`, when one is); or whether a rally window of `set` with no
 * touch left is a rally (`rally`); or what a viewer reported about a rally (`report`). */
export interface Question {
  id: string;
  kind: 'piece' | 'merge' | 'touch' | 'rally' | 'report';
  set?: number | null;
  action?: string;
  time?: number;
  reason?: 'unknown' | 'brief' | 'twice' | 'close' | 'ace';
  proposed?: number | null;
  team: Group;
  identity: number | null;
  seconds: number;
  contacts: number;
  clip: Clip;
  other?: Clip;
  crops: string[];
  choices: Choice[];
  /** Viewers' reports on a rally (`report`): what each reported, the rally's touches and its winner. */
  reports?: { kind: string | null; shown: string | null; comment: string; time: number; received?: string | null }[];
  /** A report's rally, by the key the answers name it by. */
  rally?: number | null;
  touches?: ReportTouch[];
  winner?: Group | null;
}

/** A touch of a reported rally: its player as "TEAM:IDENTITY" when known. */
export interface ReportTouch {
  frame: number;
  time: number;
  type: string;
  team: Group;
  player: string | null;
  result: string | null;
}

/** The corrections made on a report: by touch (by frame) its player ("TEAM:IDENTITY", "none" for no
 * touch), action or result; the rally's winner, or no play. */
export interface ReportChanges {
  touches: { frame: number; player?: string; type?: string; result?: string }[];
  /** Touches the rallies missed, at their frame. */
  added?: { frame: number; team: Group; type: string; result: string; player?: string }[];
  /** Rallies by their start frame: their winner, no play, their end frame, to replay, or the referee wrong. */
  rallies?: { start: number; winner?: Group; play?: false; end?: number; join?: true; redo?: boolean; wrong?: boolean }[];
  /** Rallies started at these frames: one missed, or the second of two taken for one. */
  splits?: number[];
}

/** A player to name: an identity with pictures of their clearest moments, their time on court, their
 * touches, the name and jersey number given, and the roster's players who look most like them. */
export interface Named {
  team: Group;
  identity: number;
  seconds: number;
  contacts: number;
  crops: string[];
  pieces: Piece[];
  name: string | null;
  jersey: number | null;
  /** The jersey number read on the footage. */
  read: number | null;
  suggestions: Suggestion[];
}

/** A player of the roster: the players named in earlier matches. */
export interface Suggestion {
  name: string;
  jersey: number | null;
}

/** An answer joining two names in one player: a piece of track (its clip and pictures), or
 * pictures marked as someone else. */
export type Linking =
  | { id: string; kind: 'piece' | 'split'; clip: Clip; crops: string[]; moments: Moment[]; claim: string | null; strip: { time: number; crop: string }[] }
  | { id: string; kind: 'odd'; crops: string[]; claims: (string | null)[] };

/** A moment of a piece where another answer, or a name, puts someone: its time, who they were said
 * to be (null: someone else), and its picture. */
export interface Moment {
  time: number;
  name: string | null;
  crop: string;
}

/** A player holding two names or more after the last apply, and the answers joining them. */
export interface Conflict {
  team: Group;
  identity: number;
  names: string[];
  answers: Linking[];
  /** The question answers pinning a piece on one of the names: a picture of the piece, its time, the name. */
  pinned: { id: string; crop: string; time: number; claim: string }[];
}

/** A moment for a player's card picture: its frame, the player's box and the picture of it. */
export interface PhotoMoment {
  frame: number;
  box: number[];
  crop: string;
}

/** review.js, served by volleyball_stats.review. */
interface ReviewData {
  width: number;
  height: number;
  /** The end of the match given, as written. */
  matchEnd?: string | null;
  answered: number;
  /** Answers not applied yet; whether the answers (or the jersey numbers read), and the names, differ
   * from what the players were last computed from. */
  pending: number;
  changed: boolean;
  namesPending: boolean;
  /** The corrections of the reports answered, not applied yet: where each report starts from. */
  corrections: Partial<ReportChanges>;
  /** The rallies checked, by their key. */
  checked: number[];
  /** The owner's notes on the rallies, by their key: in the review only. */
  comments: Record<number, string>;
  timeouts: Timeout[];
  questions: Question[];
  players: Named[];
  /** The roster's players of each team, for typing a name. */
  roster: [Suggestion[], Suggestion[]];
  /** The pieces marked as showing someone else than their identity's other pictures, by `track:frame`,
   * with the player they were said to be (`team:identity`), if any. */
  odd: Record<string, string | null>;
  conflicts: Conflict[];
  /** Each player's (`team:identity`) card picture first, then the other moments to pick for it. */
  photos?: Record<string, PhotoMoment[]>;
  /** The hosted pages (when the match is hosted): their last update's time (none yet since the server started), why it failed, whether a change came since. */
  hosted?: Hosted | null;
  films?: FilmCounts;
  filmsError?: string | null;
  /** The analysis runs' scores on the answers (learn.json): each measure's right and total. */
  learning?: LearnRun[];
  comparison?: Comparison | null;
  /** The last fetch of the viewers' reports from the hosting: when, how many for this match, why it failed. */
  fetched?: { at: string; count: number; error: string | null } | null;
  /** The last copy of the data on the hosting server: when, why it failed. */
  backup?: { at: string; error: string | null } | null;
}

export type Scores = Record<string, [number, number]>;

export type LearnRun = { time: string; commit: string; match?: string; scores: Scores };

/** This match's last run and the results it replaced, on the same answers. */
export type Comparison = { before: Scores; after: Scores };

/** By kind of film: how many there should be, how many are missing or out of date. */
export type FilmCounts = Record<'players' | 'highlights', { total: number; stale: number }>;

export type Hosted = { at: string | null; day?: string | null; error: string | null; behind: boolean };

declare global {
  interface Window {
    REVIEW?: ReviewData;
  }
}

export const review = window.REVIEW ?? null;

/** What the review server tells after a request: the answers saved, those and the names not applied
 * yet, whether the identities and the pages were rebuilt, and the answer an undo removed. */
/** A timeout, in frames; its team once the owner picked it. */
export interface Timeout {
  start: number;
  end: number;
  team: Group | null;
}

/** A timeout added at a frame, or one's team, bounds or removal. */
export type TimeoutChange = { frame: number } | { start: number; end: number; team: Group | null } | { start: number; end: number; removed: true };

export interface Saved {
  answered?: number;
  pending?: number;
  changed?: boolean;
  namesPending?: boolean;
  corrections?: Partial<ReportChanges>;
  checked?: number[];
  rebuilt?: boolean;
  undone?: string | null;
  /** The user declined an answer joining two players of different names: nothing saved. */
  cancelled?: boolean;
  /** The names an answer would join because earlier answers say another player of its piece: nothing saved. */
  conflict?: string[];
  /** The match's new name, after a team's: the server is restarting on it. */
  renamed?: string;
  timeouts?: Timeout[];
}

// The requests to the review server under way, by kind, for the page's indicator.
const running = { saving: 0, loading: 0 };
const listeners = new Set<() => void>();

async function tracked<T>(kind: keyof typeof running, request: Promise<T>): Promise<T> {
  running[kind] += 1;
  listeners.forEach((listener) => listener());
  try {
    return await request;
  } finally {
    running[kind] -= 1;
    listeners.forEach((listener) => listener());
  }
}

/** What the review server is doing for the user: saving, loading, or nothing (null). */
export const serverBusy = () => (running.saving ? 'saving' : running.loading ? 'loading' : null);

/** Calls `listener` whenever `serverBusy` may have changed; returns the unsubscribe. */
export function onServerBusy(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Sends an answer, a name, pictures marked as someone else, a team's name and colour, an undo or
 * the apply request to the review server. */
/** What stopped the server's last run, until dismissed: null without one, or without a server. */
export async function readFailure(): Promise<Failure | null> {
  try {
    const failure = (await (await fetch('failure')).json()) as Partial<Failure>;
    return failure.step && failure.error ? { step: failure.step, error: failure.error } : null;
  } catch {
    return null;
  }
}

export type Failure = { step: string; error: string };

export async function post(
  path:
    | 'answer'
    | 'comment'
    | 'timeout'
    | 'name'
    | 'odd'
    | 'undo'
    | 'apply'
    | 'rerun'
    | 'host'
    | 'reports'
    | 'films'
    | 'highlights'
    | 'cut'
    | 'separate'
    | 'end'
    | 'forget'
    | 'more'
    | 'repin'
    | 'team'
    | 'photo'
    | 'failure',
  body: object = {},
): Promise<Saved> {
  const response = await tracked('saving', fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
  // An answer joining two players of different names: saved only once the user confirms.
  if (response.status === 409) {
    const { merges, conflict } = (await response.json()) as { merges: string[][]; conflict?: string[] };
    if (conflict) {
      return { conflict };
    }
    const list = new Intl.ListFormat(i18n.language, { type: 'conjunction' });
    if (window.confirm(i18n.t('review.mergeWarn', { names: merges.map((m) => list.format(m)).join(' ; ') }))) {
      return post(path, { ...body, force: true });
    }
    return { cancelled: true };
  }
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
  return (await response.json()) as Saved;
}

/** A piece of track looking like a player, with its picture. */
export interface Found extends Piece {
  crop: string;
}

/** The pieces looking most like identity `identity` of `team`, not confirmed nor rejected yet. */
export async function lookAlikes(team: Group, identity: number): Promise<Found[]> {
  const response = await tracked('loading', fetch(`more?team=${team}&identity=${identity}`));
  if (!response.ok) {
    throw new Error(`more: ${response.status}`);
  }
  return (await response.json()) as Found[];
}

/** A piece's key in `odd`. */
export const pieceKey = (p: Piece) => `${p.track}:${p.frame}`;

/** Pieces marked as someone else, with the player (`team:identity`) they were said to be, kept up
 * to date by every picture strip. */
export const marked = new Map(Object.entries(review?.odd ?? {}));

/** Whether every picture of a player is marked as someone else: no one left to propose. */
export const allMarked = (p: { pieces: Piece[] }) => p.pieces.length > 0 && p.pieces.every((piece) => marked.has(pieceKey(piece)));
