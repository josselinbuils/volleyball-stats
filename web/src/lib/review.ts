import type { Group } from '@/lib/match';

/** A piece of video with a player's box ([seconds, x1, y1, x2, y2] in video pixels) over it. */
export interface Clip {
  start: number;
  end: number;
  boxes: [number, number, number, number, number][];
}

/** An identity a question offers, with pictures of their clearest moments. */
export interface Choice {
  identity: number;
  crops: string[];
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

/** review.js, served by volleyball_stats.review. */
interface ReviewData {
  width: number;
  height: number;
  answered: number;
  questions: Question[];
}

declare global {
  interface Window {
    REVIEW?: ReviewData;
  }
}

export const review = window.REVIEW ?? null;

/** Sends an answer, an undo or the apply request to the review server. */
export async function post(path: 'answer' | 'undo' | 'apply', body: object = {}): Promise<void> {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
}
