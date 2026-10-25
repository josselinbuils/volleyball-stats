import type { Contact } from '@/lib/match';
import type { Stat, Stats } from '@/components/Stats/helpers/stats';

// A rate stands out with at least MIN_TRIES attempts on both sides and a gap of GAP or more.
const MIN_TRIES = 5;
const GAP = 0.2;

/** A rate measured on an action's attempts (`of`), the touches it counts (`picked`), and whether a
 * higher one is a strength or something to work on. */
const MEASURES: { key: string; of: Stat; picked: (s: Stats) => Contact[]; strength: boolean }[] = [
  { key: 'aces', of: 'serves', picked: (s) => s.aces, strength: true },
  { key: 'serveFaults', of: 'serves', picked: (s) => s.serveFaults, strength: false },
  { key: 'goodReceptions', of: 'receptions', picked: (s) => s.receptions.filter((c) => !s.missed.includes(c) && !s.unattacked.includes(c)), strength: true },
  { key: 'receptionFaults', of: 'receptions', picked: (s) => s.missed, strength: false },
  { key: 'receptionUnattacked', of: 'receptions', picked: (s) => s.unattacked, strength: false },
  { key: 'kills', of: 'attacks', picked: (s) => s.kills, strength: true },
  { key: 'attackFaults', of: 'attacks', picked: (s) => s.attackFaults, strength: false },
  { key: 'cleanDigs', of: 'digs', picked: (s) => s.digs.filter((c) => !s.digFaults.includes(c)), strength: true },
  { key: 'digFaults', of: 'digs', picked: (s) => s.digFaults, strength: false },
  { key: 'digUnattacked', of: 'digs', picked: (s) => s.unattackedDigs, strength: false },
  { key: 'relanceFaults', of: 'relances', picked: (s) => s.relanceFaults, strength: false },
];

/** A rate of a player's set apart from the rest of their team's: `n` of their `of` attempts against
 * `restN` of the rest's `restOf`, the player's touches it counts in `picked`. */
export interface Insight {
  key: string;
  strength: boolean;
  n: number;
  of: number;
  restN: number;
  restOf: number;
  picked: Contact[];
}

/** A player's strengths and things to work on, largest gap first: each rate of theirs MIN_TRIES
 * attempts or more and GAP or more above the rest of their team's (`team`'s minus theirs). */
export function insights(player: Stats, team: Stats): Insight[] {
  const out: (Insight & { gap: number })[] = [];
  for (const { key, of, picked, strength } of MEASURES) {
    const mine = picked(player);
    const tries = player[of].length;
    const restN = picked(team).length - mine.length;
    const restOf = team[of].length - tries;
    if (tries < MIN_TRIES || restOf < MIN_TRIES) {
      continue;
    }
    const gap = mine.length / tries - restN / restOf;
    if (gap >= GAP) {
      out.push({ key, strength, n: mine.length, of: tries, restN, restOf, picked: mine, gap });
    }
  }
  return out.sort((a, b) => b.gap - a.gap).map(({ gap: _, ...insight }) => insight);
}
