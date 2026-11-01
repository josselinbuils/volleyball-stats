import type { Group, Rally } from '@/lib/match';

/** Each rally's score in its set (team 1, team 2) after it, counted from the rallies' winners;
 * null for one that counts for nothing (`skip`: no play, or joined to the one before). */
export function runningScores(rallies: { set: number; winner: Group | null; skip: boolean }[]): ([number, number] | null)[] {
  let set: number | null = null;
  let score: [number, number] = [0, 0];
  return rallies.map((r) => {
    if (r.set !== set) {
      set = r.set;
      score = [0, 0];
    }
    if (r.skip) {
      return null;
    }
    if (r.winner) {
      score = r.winner === 1 ? [score[0] + 1, score[1]] : [score[0], score[1] + 1];
    }
    return score;
  });
}

/** The rally indices at which a set's running score (`runningScores`) ends off its final score
 * the user gave (`given`, "25-21" by set), with that score. */
export function offGiven(sets: number[], scores: ([number, number] | null)[], given: (string | null)[]): Map<number, string> {
  const out = new Map<number, string>();
  for (const [n, text] of given.entries()) {
    const k = scores.findLastIndex((s, i) => s !== null && sets[i] === n + 1);
    const final = text?.match(/^(\d+)-(\d+)$/);
    if (k >= 0 && final && (scores[k]![0] !== Number(final[1]) || scores[k]![1] !== Number(final[2]))) {
      out.set(k, text!);
    }
  }
  return out;
}

/** A touch added under this long after the one before it in its rally follows it; later, it starts the next rally. */
export const NEXT_TOUCH_S = 5;

/** The touch most likely added after `before` (none: the rally's first, a serve by `server`): a
 * serve's reception, a free ball's or an attack's dig by the other team; a reception's or a dig's
 * set, a set's attack by the same team; after a block, a dig on the blockers' side. */
export function nextTouch(before: { type: string; team: Group } | undefined, server: Group): { type: string; team: Group } {
  if (!before) {
    return { type: 'serve', team: server };
  }
  const other = (3 - before.team) as Group;
  switch (before.type) {
    case 'serve':
      return { type: 'pass', team: other };
    case 'attack':
    case 'relance':
      return { type: 'dig', team: other };
    case 'pass':
    case 'dig':
      return { type: 'set', team: before.team };
    case 'set':
      return { type: 'attack', team: before.team };
    default:
      return { type: 'dig', team: before.team };
  }
}

/** A report's video starts this long before the reported moment, and a touch's replay before the touch. */
export const REPORT_LEAD_S = 2;

/** A touch counts in its rally from this long before its start, as on the page (actions.LEAD_S). */
export const LEAD_S = 0.33;

/** The index of the rally `time` falls in (from LEAD_S before it), else of the last one started
 * before it (just ended), else of the first: as the server places an added touch. */
export function rallyAt(rallies: Pick<Rally, 'start' | 'end'>[], time: number): number {
  const inside = rallies.findIndex((r) => r.start - LEAD_S <= time && time <= r.end);
  if (inside >= 0) {
    return inside;
  }
  const before = rallies.findLastIndex((r) => r.start <= time);
  return Math.max(0, before);
}

/** `rallies` each starting at a serve `added` before it, as the server files them: the touches added
 * after such a serve are that rally's; each lasting to the last touch added to it. */
export function withAdded<R extends Pick<Rally, 'start' | 'end'>>(rallies: R[], added: { time: number; type: string }[]): R[] {
  const out = rallies.map((r) => ({ ...r }));
  for (const a of added) {
    const k = a.type === 'serve' ? rallyOf(out, a.time, 'serve') : -1;
    if (out[k]) {
      out[k].start = Math.min(out[k].start, a.time);
    }
  }
  for (const a of added) {
    const r = out[rallyOf(out, a.time, a.type)];
    if (r) {
      r.end = Math.max(r.end, a.time);
    }
  }
  return out;
}

/** A rally as the editor lists it: the page's (`origin` its index), or one started by the review
 * (`added`), named by its start frame. */
export type Piece = Pick<Rally, 'start' | 'end' | 'set' | 'winner'> & { key: number; origin: number | null; added: boolean };

/** `rallies` with a rally starting at each of `splits` (frames), as the server splits them: one
 * inside a rally ends it just before, the new one its second part with its winner; one between two
 * is a rally the pipeline missed, in the set of the one before (else after). */
export function withSplits(rallies: Pick<Rally, 'start' | 'end' | 'set' | 'winner' | 'key'>[], splits: number[], fps: number): Piece[] {
  const out: Piece[] = rallies.map((r, k) => ({ start: r.start, end: r.end, set: r.set, winner: r.winner, key: r.key ?? Math.round(r.start * fps), origin: k, added: false }));
  for (const key of [...new Set(splits)].sort((a, b) => a - b)) {
    const time = key / fps;
    const k = out.findIndex((r) => r.start <= time && time <= r.end);
    if (k < 0) {
      const at = out.filter((r) => r.start < time).length;
      out.splice(at, 0, { start: time, end: time, set: (out[at - 1] ?? out[at])?.set ?? 1, winner: null, key, origin: null, added: true });
    } else if (out[k].start < time) {
      out.splice(k, 1, { ...out[k], end: time - 1 / fps, winner: null }, { ...out[k], start: time, key, added: true });
    }
  }
  return out;
}

/** The index in `pieces` of a page touch at `time` of the page's rally `origin`: the last part of
 * that rally started by then. */
export function pieceOf(pieces: Piece[], origin: number, time: number): number {
  const mine = pieces.flatMap((p, k) => (p.origin === origin ? [k] : []));
  return mine.findLast((k) => pieces[k].start <= time) ?? mine[0] ?? -1;
}

/** The index of the rally a touch of `type` added at `time` belongs to, as the server files it: the
 * one it falls in; else a serve the next one's (the rally missed it), another touch `rallyAt`'s. */
export function rallyOf(rallies: Pick<Rally, 'start' | 'end'>[], time: number, type: string): number {
  const inside = rallies.findIndex((r) => r.start - LEAD_S <= time && time <= r.end);
  const next = rallies.findIndex((r) => r.start > time);
  return inside < 0 && type === 'serve' && next >= 0 ? next : rallyAt(rallies, time);
}
