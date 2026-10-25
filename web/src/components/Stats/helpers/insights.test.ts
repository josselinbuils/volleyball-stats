import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { STATS, type Stats } from '@/components/Stats/helpers/stats';
import { insights } from '@/components/Stats/helpers/insights';

describe('insights', () => {
  // `counts` touches per stat, the player's first `mine` of each.
  const stats = (counts: Partial<Record<string, number>>) => {
    const touches: Record<string, Contact[]> = {};
    for (const s of STATS) {
      touches[s] = Array.from({ length: counts[s] ?? 0 }, (_, i) => ({ i }) as Contact);
    }
    return touches as Stats;
  };
  const share = (all: Stats, take: Partial<Record<string, number>>) => Object.fromEntries(Object.entries(all).map(([k, v]) => [k, v.slice(0, take[k] ?? 0)])) as Stats;

  it('lists a rate 20 points or more above the rest of the team, largest gap first', () => {
    const team = stats({ serves: 20, aces: 4, serveFaults: 6, attacks: 10, kills: 3 });
    const player = share(team, { serves: 8, aces: 4, serveFaults: 4, attacks: 5, kills: 1 });

    expect(insights(player, team).map(({ key, strength, n, of, restN, restOf }) => [key, strength, n, of, restN, restOf])).toEqual([
      ['aces', true, 4, 8, 0, 12],
      ['serveFaults', false, 4, 8, 2, 12],
    ]);
  });

  it('says nothing under 5 attempts on either side', () => {
    const team = stats({ serves: 8, aces: 4 });

    expect(insights(share(team, { serves: 4, aces: 4 }), team)).toEqual([]);
    expect(insights(share(team, { serves: 5, aces: 4 }), team)).toEqual([]);
  });
});
