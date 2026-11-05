import type { ListedMatch } from '@/components/Matches';
import type { Insight } from '@/components/Stats/helpers/insights';
import { lines, meanAttackRating, meanDigRating, meanRating, meanServeRating, type Stats } from '@/components/Stats/helpers/stats';
import { strengths, toWorkOn } from '@/components/Stats/helpers/strengths';
import { timeOnCourt } from '@/helpers/players';
import type { Contact, Data, Group } from '@/lib/match';

export const MEASURES = ['points', 'serve', 'reception', 'attack', 'dig'] as const;
export type Measure = (typeof MEASURES)[number];
export type Values = Record<Measure, (number | null)[]>;

export interface Played {
  path: string;
  date: string | null;
  opponent: string | null;
  /** The team's colour and the opponent's. */
  colours: [string | null, string | null];
  /** Each set's points, the team's first. */
  scores: [number, number][];
  /** Sets won and lost. */
  won: number;
  lost: number;
}

/** A strength of the match pages over the season: its counts summed over the `matches` it showed in. */
export interface SeasonStrength {
  key: string;
  n: number;
  of: number;
  matches: number;
}

/** A measure that went up from a player's first match measured to their last. */
export interface Rise {
  measure: Measure;
  from: number;
  to: number;
}

export interface SeasonPlayer {
  key: string;
  name: string | null;
  jersey: number | null;
  values: Values;
  /** The matches they played. */
  matches: number;
  /** Those shown most often first, SHOWN at most. */
  strengths: SeasonStrength[];
  /** Largest first, SHOWN at most: never a fall. */
  rising: Rise[];
  /** What their last match's page gave them to work on. */
  work: Insight | null;
}

export interface SeasonData {
  team: string;
  colour: string | null;
  /** Oldest first: `values` hold one entry per match, in this order. */
  played: Played[];
  /** Most touches first. */
  players: SeasonPlayer[];
}

// Fewer in a match say too little of a player.
const MIN_SAMPLE = 5;

/** A season follows a team over at least this many matches. */
const MIN_MATCHES = 2;

// At most this many strengths and rises a player shows.
const SHOWN = 2;
// A rise counts from this much: half a grade out of 5, a point per set.
const RISE: Record<Measure, number> = { points: 1, serve: 0.5, reception: 0.5, attack: 0.5, dig: 0.5 };

/** The named teams with a season among the listed matches, most matches first. */
export function seasonTeams(matches: ListedMatch[]): string[] {
  const counts = new Map<string, number>();
  for (const m of matches) {
    if (m.rallies > 0) {
      for (const name of new Set(m.teams?.map((team) => team.name))) {
        if (name) {
          counts.set(name, (counts.get(name) ?? 0) + 1);
        }
      }
    }
  }
  return [...counts]
    .filter(([, count]) => count >= MIN_MATCHES)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name]) => name);
}

/** The matches of `team`, oldest first. */
export function matchesOf(matches: ListedMatch[], team: string): ListedMatch[] {
  return matches.filter((m) => m.rallies > 0 && m.teams?.some((t) => t.name === team)).sort((a, b) => (a.date ?? '').localeCompare(b.date ?? ''));
}

function values(s: Stats): Record<Measure, number | null> {
  const enough = (rated: Contact[], value: number | null) => (rated.length >= MIN_SAMPLE ? value : null);
  const sets = new Set(s.touches.map((c) => c.set)).size;
  return {
    points: enough(s.touches, s.points.length / sets),
    serve: enough(s.serveRated, meanServeRating(s)),
    reception: enough(s.rated, meanRating(s)),
    attack: enough(s.attackRated, meanAttackRating(s)),
    dig: enough(s.digRated, meanDigRating(s)),
  };
}

/** Each set's final points, team 1's first: as given, else from its last rally. */
function setScores(data: Data): [number, number][] {
  const last = new Map(data.rallies.flatMap((r) => (r.score ? [[r.set, r.score] as const] : [])));
  const numbers = [...new Set(data.rallies.map((r) => r.set))].sort((a, b) => a - b);
  return Array.from({ length: Math.max(numbers.length, data.scores?.length ?? 0) }).flatMap((_, k) => {
    const given = data.scores?.[k]?.split('-').map(Number) as [number, number] | undefined;
    const score = given ?? last.get(numbers[k]);
    return score ? [score] : [];
  });
}

const emptyValues = (n: number) => Object.fromEntries(MEASURES.map((m) => [m, Array<number | null>(n).fill(null)])) as Values;

function risesOf(values: Values): Rise[] {
  return MEASURES.flatMap((measure) => {
    const known = values[measure].filter((v) => v !== null);
    const [from, to] = [known[0], known[known.length - 1]];
    return known.length >= 2 && to - from >= RISE[measure] ? [{ measure, from, to }] : [];
  })
    .sort((a, b) => (b.to - b.from) / RISE[b.measure] - (a.to - a.from) / RISE[a.measure])
    .slice(0, SHOWN);
}

/** What `team` did over its `played` matches, oldest first, with the stats and the strengths of the match pages. */
export function buildSeason(team: string, played: { match: ListedMatch; data: Data }[]): SeasonData {
  const players = new Map<string, SeasonPlayer & { touches: number; found: Map<string, SeasonStrength> }>();
  let colour: string | null = null;
  const results = played.map(({ match, data }, k): Played => {
    const at = data.teams?.findIndex((t) => t.name === team) ?? -1;
    const g = (at + 1) as Group;
    colour = data.teams?.[at]?.colour ?? colour;
    const contacts: Contact[] = data.contacts.map((c, i) => ({ ...c, i, g: c.team ?? (c.side === 'left' ? 1 : 2), player: null, name: null }));
    const found = lines(contacts, data.people, g);
    const teamStats = found[found.length - 1].stats;
    const earned = strengths(
      found,
      (p) => timeOnCourt(p, null, data.people),
      data.rallies.map((r, i) => ({ i, set: r.set, score: r.score ?? null })),
    );
    for (const line of found) {
      if (typeof line.id !== 'number') {
        continue;
      }
      const person = data.people[line.id];
      // A match's own number for an unnamed player says nothing of the next match.
      const key = person.name ? `name ${person.name}` : person.jersey != null ? `jersey ${person.jersey}` : null;
      if (key) {
        const player = players.get(key) ?? {
          key,
          name: person.name ?? null,
          jersey: person.jersey,
          values: emptyValues(played.length),
          matches: 0,
          strengths: [],
          rising: [],
          work: null,
          touches: 0,
          found: new Map(),
        };
        player.touches += line.stats.touches.length;
        player.matches += 1;
        for (const [measure, value] of Object.entries(values(line.stats))) {
          player.values[measure as Measure][k] = value;
        }
        for (const i of earned.get(line.id) ?? []) {
          const had = player.found.get(i.key) ?? { key: i.key, n: 0, of: 0, matches: 0 };
          // Kinds of touch are not added up from one match to the next.
          player.found.set(i.key, { key: i.key, n: i.key === 'versatile' ? Math.max(had.n, i.n) : had.n + i.n, of: had.of + i.of, matches: had.matches + 1 });
        }
        player.work = toWorkOn(line.stats, teamStats)[0] ?? null;
        players.set(key, player);
      }
    }
    const scores = setScores(data).map(([one, two]): [number, number] => (g === 1 ? [one, two] : [two, one]));
    return {
      path: match.path,
      date: match.date,
      opponent: data.teams?.[2 - g]?.name ?? null,
      colours: [data.teams?.[at]?.colour ?? null, data.teams?.[2 - g]?.colour ?? null],
      scores,
      won: scores.filter(([us, them]) => us > them).length,
      lost: scores.filter(([us, them]) => us < them).length,
    };
  });
  return {
    team,
    colour,
    played: results,
    players: [...players.values()]
      .sort((a, b) => b.touches - a.touches)
      .map(({ touches: _, found, ...player }) => ({
        ...player,
        strengths: [...found.values()].sort((a, b) => b.matches - a.matches || b.n - a.n).slice(0, SHOWN),
        rising: risesOf(player.values),
      })),
  };
}
