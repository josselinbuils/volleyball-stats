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
 * touch left is a rally (`rally`). */
export interface Question {
  id: string;
  kind: 'piece' | 'merge' | 'touch' | 'rally';
  set?: number | null;
  action?: string;
  time?: number;
  reason?: 'unknown' | 'twice' | 'close' | 'ace';
  proposed?: number | null;
  team: Group;
  identity: number | null;
  seconds: number;
  contacts: number;
  clip: Clip;
  other?: Clip;
  crops: string[];
  choices: Choice[];
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
  answered: number;
  /** Answers not applied yet; whether the answers (or the jersey numbers read), and the names, differ
   * from what the players were last computed from. */
  pending: number;
  changed: boolean;
  namesPending: boolean;
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
  /** The hosted pages' last update after a change (when the match is hosted): its time, and why it failed. */
  hosted?: { at: string; error: string | null } | null;
}

declare global {
  interface Window {
    REVIEW?: ReviewData;
  }
}

export const review = window.REVIEW ?? null;

/** What the review server tells after a request: the answers saved, those and the names not applied
 * yet, whether the identities and the pages were rebuilt, and the answer an undo removed. */
export interface Saved {
  answered?: number;
  pending?: number;
  changed?: boolean;
  namesPending?: boolean;
  rebuilt?: boolean;
  undone?: string | null;
  /** The user declined an answer joining two players of different names: nothing saved. */
  cancelled?: boolean;
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
export async function post(path: 'answer' | 'name' | 'odd' | 'undo' | 'apply' | 'cut' | 'forget' | 'more' | 'repin' | 'team' | 'photo', body: object = {}): Promise<Saved> {
  const response = await tracked('saving', fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
  // An answer joining two players of different names: saved only once the user confirms.
  if (response.status === 409) {
    const { merges } = (await response.json()) as { merges: string[][] };
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
