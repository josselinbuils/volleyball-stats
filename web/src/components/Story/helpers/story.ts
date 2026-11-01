import type { Contact, Group, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';

// Points in a row, a deficit caught up and a touch count that make a moment.
const RUN = 5;
const COMEBACK = 4;
// A set's shape: a final gap this small is tight, this large one-sided.
const TIGHT = 3;
const ONE_SIDED = 8;
const SET_POINTS = 25;
// The share of a run's serves one player must hold to be named.
const SERVER_SHARE = 0.75;

export type Score = [number, number];

/** A moment of a set: its `rallies` (indexes on the page), `team` the one it is about, the scores
 * team-first: `from` before its first rally, `to` after its last. */
export interface Moment {
  kind: 'run' | 'comeback' | 'setPoints' | 'longest';
  rallies: number[];
  team: Group | null;
  from: Score;
  to: Score;
  /** Points of a run, points caught up, set points saved, or a longest rally's touches. */
  n: number;
  /** A run's server, a longest rally's scorer, when known. */
  person: number | null;
  /** A longest rally's seconds. */
  seconds: number;
}

/** A set as a story: `shape` how it went, `points` each scored rally with the gap (team 1 minus team 2)
 * after it. */
export interface Chapter {
  set: number;
  winner: Group | null;
  /** The final score, winner first. */
  score: Score;
  shape: 'tight' | 'oneSided' | 'comeback' | 'steady';
  /** The winner's largest deficit. */
  deficit: number;
  /** The player with the most points of the set, 3 or more. */
  top: { person: number; points: number } | null;
  points: { rally: number; gap: number }[];
  moments: Moment[];
}

const other = (team: Group): Group => (team === 1 ? 2 : 1);
const teamFirst = (score: Score, team: Group): Score => (team === 1 ? score : [score[1], score[0]]);

/** The team a rally's score moved for, null when it did not move. */
function scorer(before: Score, after: Score): Group | null {
  return after[0] > before[0] ? 1 : after[1] > before[1] ? 2 : null;
}

interface Step {
  rally: Rally;
  before: Score;
  after: Score;
  won: Group;
}

/** The rallies of a set that moved its score. */
function steps(rallies: Rally[]): Step[] {
  const out: Step[] = [];
  let before: Score = [0, 0];
  for (const rally of rallies) {
    if (rally.score) {
      const won = scorer(before, rally.score);
      if (won) {
        out.push({ rally, before, after: rally.score, won });
      }
      before = rally.score;
    }
  }
  return out;
}

/** Who served most of `run`'s rallies for `team`, when one player holds SERVER_SHARE of them. */
function runServer(run: Step[], team: Group): number | null {
  const serves = run.map((s) => s.rally.contacts.find((c) => c.type === 'serve')).filter((c): c is Contact => c?.g === team && c.person !== null);
  const counts = new Map<number, number>();
  for (const c of serves) {
    counts.set(c.person as number, (counts.get(c.person as number) ?? 0) + 1);
  }
  const [person, n] = [...counts].sort((a, b) => b[1] - a[1])[0] ?? [null, 0];
  return person !== null && n >= SERVER_SHARE * (run.length - 1) ? person : null;
}

function runs(all: Step[]): Moment[] {
  const out: Moment[] = [];
  let start = 0;
  for (let k = 1; k <= all.length; k++) {
    if (k === all.length || all[k].won !== all[start].won) {
      const run = all.slice(start, k);
      if (run.length >= RUN) {
        const team = run[0].won;
        out.push({
          kind: 'run',
          rallies: run.map((s) => s.rally.i),
          team,
          from: teamFirst(run[0].before, team),
          to: teamFirst(run[run.length - 1].after, team),
          n: run.length,
          person: runServer(run, team),
          seconds: 0,
        });
      }
      start = k;
    }
  }
  return out;
}

/** Each team's largest deficit in the set caught up to a tie or better. */
function comebacks(all: Step[]): Moment[] {
  const out: Moment[] = [];
  for (const team of [1, 2] as const) {
    let worst = 0;
    let at = 0;
    let best: Moment | null = null;
    for (const [k, s] of all.entries()) {
      const [mine, theirs] = teamFirst(s.after, team);
      if (theirs - mine > worst) {
        worst = theirs - mine;
        at = k;
      }
      if (mine >= theirs) {
        if (worst >= COMEBACK && worst > (best?.n ?? 0)) {
          best = {
            kind: 'comeback',
            rallies: all.slice(at + 1, k + 1).map((x) => x.rally.i),
            team,
            from: teamFirst(all[at].after, team),
            to: teamFirst(s.after, team),
            n: worst,
            person: null,
            seconds: 0,
          };
        }
        worst = 0;
      }
    }
    if (best) {
      out.push(best);
    }
  }
  return out;
}

/** The set points saved, those in a row as one, `target` the points a set is played to. */
function setPoints(all: Step[], target: number): Moment[] {
  const out: Moment[] = [];
  for (const s of all) {
    const leader = s.before[0] > s.before[1] ? 1 : s.before[1] > s.before[0] ? 2 : null;
    if (leader === null || Math.max(...s.before) < target - 1 || s.won === leader) {
      continue;
    }
    const last = out[out.length - 1];
    if (last?.team === s.won && last.rallies[last.rallies.length - 1] === all[all.indexOf(s) - 1]?.rally.i) {
      last.rallies.push(s.rally.i);
      last.n++;
      last.to = teamFirst(s.after, s.won);
    } else {
      out.push({ kind: 'setPoints', rallies: [s.rally.i], team: s.won, from: teamFirst(s.before, s.won), to: teamFirst(s.after, s.won), n: 1, person: null, seconds: 0 });
    }
  }
  return out;
}

/** The longest of `rallies` in touches, then seconds, `person` scoring its last touch when a point. */
function longest(rallies: Rally[]): Moment | null {
  const touches = (r: Rally) => r.contacts.filter(isTouch).length;
  const seen = rallies.filter((r) => r.score && touches(r) > 0);
  const rally = [...seen].sort((a, b) => touches(b) - touches(a) || b.end - b.start - (a.end - a.start))[0];
  if (!rally?.score) {
    return null;
  }
  const last = rally.contacts.filter(isTouch).at(-1);
  const k = rallies.indexOf(rally);
  const before = rallies[k - 1]?.set === rally.set ? (rallies[k - 1].score ?? ([0, 0] as Score)) : ([0, 0] as Score);
  const team = rally.winner;
  return {
    kind: 'longest',
    rallies: [rally.i],
    team,
    from: team ? teamFirst(before, team) : before,
    to: team ? teamFirst(rally.score, team) : rally.score,
    n: touches(rally),
    person: last?.result === 'point' && last.g === team ? last.person : null,
    seconds: rally.end - rally.start,
  };
}

function topScorer(rallies: Rally[], key: (person: number) => string | null): Chapter['top'] {
  const counts = new Map<string, { person: number; points: number }>();
  for (const c of rallies.flatMap((r) => r.contacts)) {
    const k = c.person === null || !isTouch(c) || c.result !== 'point' ? null : key(c.person);
    if (k !== null) {
      const seen = counts.get(k);
      counts.set(k, { person: seen?.person ?? (c.person as number), points: (seen?.points ?? 0) + 1 });
    }
  }
  const best = [...counts.values()].sort((a, b) => b.points - a.points)[0];
  return best && best.points >= 3 ? best : null;
}

/** The story of `rallies`, one chapter per set, `finals` each set's final score (team 1, team 2),
 * `key` naming a player whatever their identity. The longest rally is told once, in its set. */
export function story(rallies: Rally[], finals: { set: number; score: Score }[], key: (person: number) => string | null): Chapter[] {
  const longestOne = longest(rallies);
  return [...new Set(rallies.map((r) => r.set))]
    .sort((a, b) => a - b)
    .flatMap((set): Chapter[] => {
      const of = rallies.filter((r) => r.set === set);
      const all = steps(of);
      if (!all.length) {
        return [];
      }
      const final = finals.find((s) => s.set === set)?.score ?? all[all.length - 1].after;
      const winner = final[0] > final[1] ? 1 : final[1] > final[0] ? 2 : null;
      const score: Score = winner ? teamFirst(final, winner) : final;
      const streaks = runs(all);
      // A comeback made within one run: the run tells it.
      const caughtUp = comebacks(all).filter((c) => !streaks.some((r) => r.team === c.team && c.rallies.every((i) => r.rallies.includes(i))));
      const moments = [...streaks, ...caughtUp, ...setPoints(all, Math.min(SET_POINTS, Math.max(...final)))];
      if (longestOne && of.some((r) => r.i === longestOne.rallies[0])) {
        moments.push(longestOne);
      }
      const deficit = winner ? Math.max(0, ...all.map((s) => teamFirst(s.after, other(winner))[0] - teamFirst(s.after, other(winner))[1])) : 0;
      const gap = score[0] - score[1];
      return [
        {
          set,
          winner,
          score,
          shape: deficit >= COMEBACK ? 'comeback' : gap <= TIGHT ? 'tight' : gap >= ONE_SIDED ? 'oneSided' : 'steady',
          deficit,
          top: topScorer(of, key),
          points: all.map((s) => ({ rally: s.rally.i, gap: s.after[0] - s.after[1] })),
          moments: moments.sort((a, b) => a.rallies[a.rallies.length - 1] - b.rallies[b.rallies.length - 1]),
        },
      ];
    });
}
