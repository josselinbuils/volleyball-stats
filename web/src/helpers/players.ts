import type { Person } from '@/lib/match';
import type { Players } from '@/lib/players';

// A player missing from a few samples, the tracker having lost them for a moment, stays where they
// were last seen for up to HOLD_S, rather than blinking out.
const HOLD_S = 0.5;

/** The players' feet at the sample nearest to `time`, and those of the HOLD_S before missing from
 * it at their last place; none past the samples. */
export function playersAt(players: Players, fps: number, time: number): { person: number; x: number; y: number }[] {
  const at = Math.round((time * fps) / players.step);
  const back = Math.round((HOLD_S * fps) / players.step);
  const seen = new Map<number, { person: number; x: number; y: number }>();
  for (let k = at; k >= Math.max(0, at - back); k--) {
    const flat = players.samples[k] ?? [];
    for (let i = 0; i < flat.length; i += 3) {
      if (!seen.has(flat[i])) {
        seen.set(flat[i], { person: flat[i], x: flat[i + 1], y: flat[i + 2] });
      }
    }
    // Past the samples, nobody.
    if (k === at && players.samples[k] === undefined) {
      return [];
    }
  }
  return [...seen.values()];
}

/** A player: their team and name, else jersey number, else number for the match, which is each
 * identity's own. The identities the user gave one name or jersey number share it. Null for a track
 * that is no identified player. */
export function playerKey(person: number | null | undefined, people: Record<string, Person>): string | null {
  const p = person == null ? undefined : people[person];
  return p?.number == null ? null : `${p.team}:${p.name ? `name ${p.name}` : p.jersey != null ? `jersey ${p.jersey}` : `number ${p.number}`}`;
}
