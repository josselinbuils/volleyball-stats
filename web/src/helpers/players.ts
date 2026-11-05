import type { Person } from '@/lib/match';
import type { Players } from '@/lib/players';

// A player missing from a few samples, the tracker having lost them for a moment, stays where they
// were last seen for up to HOLD_S, rather than blinking out.
const HOLD_S = 0.5;

/** The place of `person` in a sample, if any. */
function placeIn(flat: number[] | undefined, person: number): [number, number] | undefined {
  for (let i = 0; flat && i < flat.length; i += 3) {
    if (flat[i] === person) {
      return [flat[i + 1], flat[i + 2]];
    }
  }
  return undefined;
}

/** Between `b` and `c` at `u`, the curve through all four keeping a player's speed even across samples. */
const between = (a: number, b: number, c: number, d: number, u: number) => b + 0.5 * u * (c - a + u * (2 * a - 5 * b + 4 * c - d + u * (3 * (b - c) + d - a)));

/** The players' feet at `time`, on their way between the samples around it, and those of the HOLD_S before missing from
 * the nearest at their last place; none past the samples. */
export function playersAt(players: Players, fps: number, time: number): { person: number; x: number; y: number }[] {
  const exact = (time * fps) / players.step;
  const at = Math.round(exact);
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
  const base = Math.floor(exact);
  const u = exact - base;
  for (const dot of seen.values()) {
    const b = placeIn(players.samples[base], dot.person);
    const c = placeIn(players.samples[base + 1], dot.person);
    if (u > 0 && b && c) {
      const a = placeIn(players.samples[base - 1], dot.person) ?? b;
      const d = placeIn(players.samples[base + 2], dot.person) ?? c;
      dot.x = between(a[0], b[0], c[0], d[0], u);
      dot.y = between(a[1], b[1], c[1], d[1], u);
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

/** A player's time on the court among `people`: their identities', in `set` or the whole match (null). */
export function timeOnCourt(person: number, set: number | null, people: Record<string, Person>): number {
  const key = playerKey(person, people);
  return Object.entries(people)
    .filter(([k]) => playerKey(Number(k), people) === key)
    .flatMap(([, p]) => Object.entries(p.seconds ?? {}))
    .reduce((sum, [n, v]) => (set === null || Number(n) === set ? sum + v : sum), 0);
}
