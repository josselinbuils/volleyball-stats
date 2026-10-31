import type { Contact, Group, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';

/** A set's final score (team 1, team 2), `final` when the user gave it, else estimated. */
export interface SetScore {
  set: number;
  score: [number, number];
  final: boolean;
}

/** Each set's final score in set order: from `given` ("25-21", by set) when known, else its last
 * scored rally's. Sets without either are left out. */
export function setScores(rallies: Rally[], given: (string | null)[]): SetScore[] {
  const sets = [...new Set(rallies.map((r) => r.set))].sort((a, b) => a - b);
  return sets.flatMap((set): SetScore[] => {
    const final = given[set - 1]?.match(/^(\d+)-(\d+)$/);
    if (final) {
      return [{ set, score: [Number(final[1]), Number(final[2])], final: true }];
    }
    const last = rallies.filter((r) => r.set === set && r.score !== null).at(-1);
    return last?.score ? [{ set, score: last.score, final: false }] : [];
  });
}

/** The sets each team won (team 1, team 2). */
export function setsWon(scores: SetScore[]): [number, number] {
  return [scores.filter((s) => s.score[0] > s.score[1]).length, scores.filter((s) => s.score[1] > s.score[0]).length];
}

/** The last touches of the rallies of `rallies` team `g` won: its own points (`direct`) and the other
 * team's faults (`faults`). */
export function pointSplit(rallies: Rally[], g: Group): { direct: Contact[]; faults: Contact[] } {
  const out = { direct: [] as Contact[], faults: [] as Contact[] };
  for (const r of rallies) {
    const last = r.winner === g ? r.contacts.filter(isTouch).at(-1) : undefined;
    if (last?.g === g && last.result === 'point') {
      out.direct.push(last);
    } else if (last && last.g !== g && last.result === 'error') {
      out.faults.push(last);
    }
  }
  return out;
}
