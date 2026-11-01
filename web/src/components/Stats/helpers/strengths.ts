import type { Contact, Person, Rally } from '@/lib/match';
import { playerKey } from '@/helpers/players';
import { scoresBefore, setAttacks } from '@/helpers/plays';
import { insights, type Insight } from '@/components/Stats/helpers/insights';
import type { Line, Stats } from '@/components/Stats/helpers/stats';

// At most this many strengths a player shows, the rarest in their team first.
const SHOWN = 2;
// A rate counts from this many attempts on both sides and this far above the rest of the team.
const TRIES = 5;
const GAP = 0.1;
const TOUGH_GAP = 0.15;
// A presence counts from this many touches and this much above the rest of the team, per minute on the court.
const PRESENCE: { key: string; of: (s: Stats) => Contact[]; least: number; above: number }[] = [
  { key: 'allBalls', of: (s) => s.touches, least: 20, above: 1.15 },
  { key: 'alwaysDefending', of: (s) => s.digs, least: 6, above: 1.3 },
];
const ASSISTS_FROM = 3;
const BLOCK_POINTS_FROM = 2;
const LATE_FROM = 2;
const SCORER_FROM = 5;
// A point from this score, this close, is one when it counts.
const LATE_SCORE = 20;
const CLOSE = 2;
// Playing all around: this many kinds of touch, this many times each.
const KINDS: ((s: Stats) => Contact[])[] = [(s) => s.receptions, (s) => s.sets, (s) => s.attacks, (s) => s.digs, (s) => s.blocks, (s) => s.relances];
const VERSATILE_KINDS = 5;
const VERSATILE_EACH = 3;
const STEADY_TOUCHES = 20;
const STEADY_RATIO = 0.6;

/** A strength from a rate: `n` of `of` against `restN` of `restOf`. */
function rated(key: string, n: number, of: number, restN: number, restOf: number, picked: Contact[], gap = GAP): Insight | null {
  return of >= TRIES && restOf >= TRIES && n / of - restN / restOf >= gap ? { key, strength: true, n, of, restN, restOf, picked } : null;
}

/** A strength counted, told in words rather than against the rest of the team. */
const counted = (key: string, picked: Contact[], n = picked.length): Insight => ({ key, strength: true, n, of: n, restN: 0, restOf: 0, picked, told: true });

/** `of`'s touches of `s` without a fault among those of `faults`, as a rate of the player against the rest of their team. */
function clean(key: string, s: Stats, team: Stats, of: (x: Stats) => Contact[], faults: (x: Stats) => Contact[]): Insight | null {
  const tries = of(s).length;
  const restOf = of(team).length - tries;
  const good = of(s).filter((c) => !faults(s).includes(c));
  return rated(key, good.length, tries, restOf - (faults(team).length - faults(s).length), restOf, good);
}

/** Each player's strengths among `lines` (a team's, the whole team's last), by line id: what the rates of `insights` show,
 * plus how present they are for the time they played (`seconds`), how reliable, what they give the others and when it counts.
 * The rarest in the team come first, SHOWN at most. */
export function strengths(found: Line[], seconds: (person: number) => number, contacts: Contact[], rallies: Rally[], people: Record<string, Person>): Map<number, Insight[]> {
  const team = found[found.length - 1].stats;
  const players = found.filter((l): l is Line & { id: number } => typeof l.id === 'number');
  const before = scoresBefore(rallies);
  const attacked = setAttacks(contacts);
  const kills = attacked.filter(({ attack }) => attack.result === 'point');
  const used = new Set(attacked.map(({ set }) => set));
  const teamSeconds = players.reduce((sum, l) => sum + seconds(l.id), 0);
  const late = (c: Contact) => {
    const was = before.get(c.rally);
    return was !== undefined && Math.max(...was) >= LATE_SCORE && Math.abs(was[0] - was[1]) <= CLOSE;
  };
  const most = (value: (s: Stats) => number) => Math.max(...players.map((l) => value(l.stats)));

  const all = new Map(
    players.map((line) => {
      const s = line.stats;
      const key = playerKey(line.id, people);
      const mine = seconds(line.id);
      const restSeconds = teamSeconds - mine;
      const earned: (Insight | null)[] = insights(s, team).filter((i) => i.strength);
      // Present for the time on the court.
      for (const { key: name, of, least, above } of PRESENCE) {
        const n = of(s).length;
        const rest = of(team).length - n;
        if (mine > 0 && restSeconds > 0 && n >= least && n / mine >= (above * rest) / restSeconds) {
          earned.push({ ...counted(name, of(s)), told: true, perMinute: [(60 * n) / mine, (60 * rest) / restSeconds] });
        }
      }
      // Reliable.
      earned.push(
        clean(
          'safeServes',
          s,
          team,
          (x) => x.serves,
          (x) => x.serveFaults,
        ),
      );
      earned.push(
        clean(
          'safeAttacks',
          s,
          team,
          (x) => x.attacks,
          (x) => x.attackFaults,
        ),
      );
      const restTouches = team.touches.length - s.touches.length;
      const restFaults = team.faults.length - s.faults.length;
      if (s.touches.length >= STEADY_TOUCHES && restTouches > 0 && s.faults.length / s.touches.length <= (STEADY_RATIO * restFaults) / restTouches) {
        const good = s.touches.filter((c) => !s.faults.includes(c));
        earned.push({ key: 'steady', strength: true, n: s.faults.length, of: s.touches.length, restN: restFaults, restOf: restTouches, picked: good, lowerIsBetter: true });
      }
      // How hard their serves are to take.
      const tough = (x: Stats) => x.serveRated.length - x.serveFair.length - x.serveEasy.length - x.serveFaults.length;
      const toughOnes = s.serveRated.filter((c) => !s.serveFair.includes(c) && !s.serveEasy.includes(c) && !s.serveFaults.includes(c));
      earned.push(rated('toughServes', tough(s), s.serveRated.length, tough(team) - tough(s), team.serveRated.length - s.serveRated.length, toughOnes, TOUGH_GAP));
      // What they give the others.
      const usedSets = s.sets.filter((c) => used.has(c));
      earned.push(rated('usedSets', usedSets.length, s.sets.length, team.sets.filter((c) => used.has(c)).length - usedSets.length, team.sets.length - s.sets.length, usedSets));
      const given = kills.filter(({ set, attack }) => playerKey(set.person, people) === key && playerKey(attack.person, people) !== key).map(({ attack }) => attack);
      if (given.length >= ASSISTS_FROM) {
        earned.push(counted('assists', given));
      }
      // Scoring, and when it counts.
      if (s.blockPoints.length >= BLOCK_POINTS_FROM) {
        earned.push(counted('blockPoints', s.blockPoints));
      }
      if (s.points.length >= SCORER_FROM && s.points.length === most((x) => x.points.length)) {
        earned.push(counted('topScorer', s.points));
      }
      const clutch = s.points.filter(late);
      if (clutch.length >= LATE_FROM) {
        earned.push(counted('clutch', clutch));
      }
      const kinds = KINDS.filter((of) => of(s).length >= VERSATILE_EACH).length;
      if (kinds >= VERSATILE_KINDS) {
        earned.push(counted('versatile', s.touches, kinds));
      }
      return [line.id, earned.filter((i): i is Insight => i !== null)];
    }),
  );
  const holders = new Map<string, number>();
  for (const list of all.values()) {
    for (const i of list) {
      holders.set(i.key, (holders.get(i.key) ?? 0) + 1);
    }
  }
  return new Map([...all].map(([id, list]) => [id, [...list].sort((a, b) => (holders.get(a.key) ?? 0) - (holders.get(b.key) ?? 0)).slice(0, SHOWN)]));
}

/** The one thing a player has to work on most, its largest gap with the rest of their team; none without one. */
export function toWorkOn(player: Stats, team: Stats): Insight[] {
  return insights(player, team)
    .filter((i) => !i.strength)
    .slice(0, 1);
}
