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

const capital = (letters: string[]) => letters.map((l, k) => (k ? l : l.toLocaleUpperCase())).join('');

/** Each name's initials, one letter a word; names that would share them take more letters of their first word. */
export function initials(names: string[]): Map<string, string> {
  const words = (name: string) =>
    name
      .trim()
      .split(/[\s-]+/)
      .filter(Boolean)
      .map((w) => [...w]);
  const mark = (name: string, n: number) => {
    const [first, ...rest] = words(name);
    return capital(first.slice(0, n)) + rest.map((w) => w[0].toLocaleUpperCase()).join('');
  };
  const different = [...new Set(names)].filter((name) => words(name).length);
  return new Map(
    different.map((name) => {
      let n = 1;
      while (n < words(name)[0].length && different.some((o) => o !== name && mark(o, n) === mark(name, n))) {
        n += 1;
      }
      return [name, mark(name, n)];
    }),
  );
}

/** What each player shows on a dot or a shirt, by key in `people`: their jersey number, else their initials, which
 * no jersey can clash with and which part them from their team's other players without a jersey, else their number
 * for the match; null for a track that is no identified player. */
export function playerMarks(people: Record<string, Person>): Record<string, string | null> {
  const without = (team: number) => Object.values(people).flatMap((p) => (p.team === team && p.jersey == null && p.name ? [p.name] : []));
  const byTeam = new Map([1, 2].map((team) => [team, initials(without(team))]));
  return Object.fromEntries(
    Object.entries(people).map(([key, p]) => {
      const known = p.jersey ?? (p.name ? byTeam.get(p.team)?.get(p.name) : null) ?? p.number;
      return [key, known == null ? null : String(known)];
    }),
  );
}

/** A player: their team and name, else jersey number, else number for the match, which is each
 * identity's own. The identities the user gave one name or jersey number share it. Null for a track
 * that is no identified player. */
export function playerKey(person: number | null | undefined, people: Record<string, Person>): string | null {
  const p = person == null ? undefined : people[person];
  return p?.number == null ? null : `${p.team}:${p.name ? `name ${p.name}` : p.jersey != null ? `jersey ${p.jersey}` : `number ${p.number}`}`;
}
