import type { ListedMatch } from '@/components/Matches';
import { lines, meanAttackRating, meanDigRating, meanRating, meanServeRating, type Stats } from '@/components/Stats/helpers/stats';
import type { Contact, Data, Group } from '@/lib/match';

export const MEASURES = ['points', 'serve', 'reception', 'attack', 'dig'] as const;
export type Measure = (typeof MEASURES)[number];
export type Values = Record<Measure, (number | null)[]>;

export interface Played {
  path: string;
  date: string | null;
  opponent: string | null;
  /** Each set's points, the team's first. */
  scores: [number, number][];
  /** Sets won and lost. */
  won: number;
  lost: number;
}

export interface SeasonPlayer {
  key: string;
  name: string | null;
  jersey: number | null;
  values: Values;
}

export interface SeasonData {
  team: string;
  colour: string | null;
  /** Oldest first: `values` hold one entry per match, in this order. */
  played: Played[];
  total: Values;
  /** Most touches first. */
  players: SeasonPlayer[];
}

// Fewer in a match say too little of a player.
const MIN_SAMPLE = 5;

/** A season follows a team over at least this many matches. */
const MIN_MATCHES = 2;

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

/** What `team` did over its `played` matches, oldest first, with the stats of the match pages. */
export function buildSeason(team: string, played: { match: ListedMatch; data: Data }[]): SeasonData {
  const total = emptyValues(played.length);
  const players = new Map<string, SeasonPlayer & { touches: number }>();
  let colour: string | null = null;
  const results = played.map(({ match, data }, k) => {
    const at = data.teams?.findIndex((t) => t.name === team) ?? -1;
    const g = (at + 1) as Group;
    colour = data.teams?.[at]?.colour ?? colour;
    const contacts: Contact[] = data.contacts.map((c, i) => ({ ...c, i, g: c.team ?? (c.side === 'left' ? 1 : 2), player: null, name: null }));
    for (const line of lines(contacts, data.people, g)) {
      if (line.id === 'total') {
        for (const [measure, value] of Object.entries(values(line.stats))) {
          total[measure as Measure][k] = value;
        }
      } else if (line.id !== 'rest') {
        const person = data.people[line.id];
        // A match's own number for an unnamed player says nothing of the next match.
        const key = person.name ? `name ${person.name}` : person.jersey != null ? `jersey ${person.jersey}` : null;
        if (key) {
          const player = players.get(key) ?? { key, name: person.name ?? null, jersey: person.jersey, values: emptyValues(played.length), touches: 0 };
          player.touches += line.stats.touches.length;
          for (const [measure, value] of Object.entries(values(line.stats))) {
            player.values[measure as Measure][k] = value;
          }
          players.set(key, player);
        }
      }
    }
    const scores = setScores(data).map(([one, two]): [number, number] => (g === 1 ? [one, two] : [two, one]));
    return {
      path: match.path,
      date: match.date,
      opponent: data.teams?.[2 - g]?.name ?? null,
      scores,
      won: scores.filter(([us, them]) => us > them).length,
      lost: scores.filter(([us, them]) => us < them).length,
    };
  });
  return { team, colour, played: results, total, players: [...players.values()].sort((a, b) => b.touches - a.touches) };
}
