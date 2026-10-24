import type { Rally } from '@/lib/match';
import { PAD } from '@/lib/playlist';

/** A set's score (team 1, team 2) at a moment, `final` when it is the set's final score as the
 * user gave it, else estimated. */
export interface Score {
  set: number;
  score: [number, number];
  final: boolean;
}

/** The score at `time`: while a rally is played the score before it, after it the score after it;
 * after a set's last rally its final score from `given` ("25-21") when known. Null without scores. */
export function scoreAt(rallies: Rally[], time: number, given: (string | null)[]): Score | null {
  const scored = rallies.filter((r) => r.score !== null);
  if (!scored.length) {
    return null;
  }
  const k = scored.findLastIndex((r) => r.start - PAD <= time);
  const current = scored[Math.max(k, 0)];
  if (k === -1 || time < current.end) {
    const before = scored[k - 1];
    return { set: current.set, score: before?.set === current.set && before.score ? before.score : [0, 0], final: false };
  }
  const last = scored[k + 1]?.set !== current.set;
  const final = last ? given[current.set - 1]?.match(/^(\d+)-(\d+)$/) : null;
  return { set: current.set, score: final ? [Number(final[1]), Number(final[2])] : (current.score as [number, number]), final: Boolean(final) };
}
