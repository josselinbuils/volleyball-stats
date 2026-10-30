import type { Group } from '@/lib/match';

/** A piece of video with a player's box ([seconds, x1, y1, x2, y2] in video pixels) over it. */
export interface Clip {
  start: number;
  end: number;
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
 * identities never seen together are one player (`merge`, `other` the second one's clip). */
export interface Question {
  id: string;
  kind: 'piece' | 'merge';
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

/** review.js, served by volleyball_stats.review. */
interface ReviewData {
  width: number;
  height: number;
  answered: number;
  questions: Question[];
  players: Named[];
  /** The roster's players of each team, for typing a name. */
  roster: [Suggestion[], Suggestion[]];
  /** The pieces marked as showing someone else than their identity's other pictures, by `track:frame`,
   * with the player they were said to be (`team:identity`), if any. */
  odd: Record<string, string | null>;
}

declare global {
  interface Window {
    REVIEW?: ReviewData;
  }
}

export const review = window.REVIEW ?? null;

/** What the review server tells after a request: the answers saved, whether the identities and the
 * pages were rebuilt, and the answer an undo removed. */
export interface Saved {
  answered?: number;
  rebuilt?: boolean;
  undone?: string | null;
}

/** Sends an answer, a name, pictures marked as someone else, an undo or the apply request to the
 * review server. */
export async function post(path: 'answer' | 'name' | 'odd' | 'undo' | 'apply', body: object = {}): Promise<Saved> {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
  return (await response.json()) as Saved;
}

/** A piece's key in `odd`. */
export const pieceKey = (p: Piece) => `${p.track}:${p.frame}`;

/** Pieces marked as someone else, with the player (`team:identity`) they were said to be, kept up
 * to date by every picture strip. */
export const marked = new Map(Object.entries(review?.odd ?? {}));

/** Whether every picture of a player is marked as someone else: no one left to propose. */
export const allMarked = (p: { pieces: Piece[] }) => p.pieces.length > 0 && p.pieces.every((piece) => marked.has(pieceKey(piece)));
