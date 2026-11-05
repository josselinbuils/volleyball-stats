import { contacts, GROUPS, match } from '@/lib/match';
import { playerKey, timeOnCourt } from '@/helpers/players';
import { lines, mvp, type Stats } from '@/components/Stats/helpers/stats';

/** A player's time on the court: their identities', in `set` or the whole match (null). */
export function playingTime(person: number, set: number | null): number {
  return timeOnCourt(person, set, match.people);
}

/** The match's MVP: their `playerKey`, stats and time on the court over the whole match. */
export interface Best {
  key: string | null;
  stats: Stats;
  seconds: number;
}

/** The whole match's MVP, whatever the set shown: a player, as their identities may differ by set. */
export function bestPlayer(): Best | null {
  const all = GROUPS.flatMap((g) => lines(contacts, match.people, g));
  const id = mvp(all, (p) => playingTime(p, null));
  const line = all.find((l) => l.id === id);
  return id === null || !line ? null : { key: playerKey(id, match.people), stats: line.stats, seconds: playingTime(id, null) };
}
