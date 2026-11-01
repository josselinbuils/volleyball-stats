import type { Contact, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';
import { longestRally, serveRun, setAttacks } from '@/helpers/plays';
import type { Line, Stat } from '@/components/Stats/helpers/stats';

/** The counts that win a trophy, each from a minimum so that none goes to next to nothing. */
const COUNTED: { stat: Stat; least: number }[] = [
  { stat: 'touches', least: 10 },
  { stat: 'kills', least: 3 },
  { stat: 'blockPoints', least: 2 },
  { stat: 'aces', least: 2 },
  { stat: 'digs', least: 5 },
  { stat: 'sets', least: 5 },
  { stat: 'perfect', least: 3 },
];
const SERVE_RUN_FROM = 3;
const DUO_FROM = 3;

/** A trophy: `people` its winners (a tie shares it), `contacts` or `rallies` the moments it replays. */
export type Trophy =
  | { kind: Stat; people: number[]; n: number; contacts: Contact[] }
  | { kind: 'serveRun'; people: number[]; n: number; rallies: number[] }
  | { kind: 'duo'; setter: number; attacker: number; n: number; of: number; contacts: Contact[] }
  | { kind: 'longest'; rally: Rally; n: number; seconds: number };

/** The trophies of `found` (both teams' lines), of `contacts` and `rallies`. Only what a player did well
 * wins one. */
export function trophies(found: Line[], contacts: Contact[], rallies: Rally[], people: Record<string, Person>): Trophy[] {
  const players = found.filter((l): l is Line & { id: number } => typeof l.id === 'number');
  const out: Trophy[] = [];
  for (const { stat, least } of COUNTED) {
    const n = Math.max(0, ...players.map((l) => l.stats[stat].length));
    if (n >= least) {
      const won = players.filter((l) => l.stats[stat].length === n);
      out.push({ kind: stat, people: won.map((l) => l.id), n, contacts: won.flatMap((l) => l.stats[stat]).sort((a, b) => a.t - b.t) });
    }
  }
  const runs = players.flatMap((l) => {
    const key = playerKey(l.id, people);
    const run = key === null ? null : serveRun(rallies, key, people);
    return run ? [{ person: l.id, run }] : [];
  });
  const longestRun = Math.max(0, ...runs.map((r) => r.run.rallies.length));
  if (longestRun >= SERVE_RUN_FROM) {
    const won = runs.filter((r) => r.run.rallies.length === longestRun);
    out.push({ kind: 'serveRun', people: won.map((r) => r.person), n: longestRun, rallies: won.flatMap((r) => r.run.rallies) });
  }
  const pairs = new Map<string, { setter: number; attacker: number; attacks: Contact[] }>();
  for (const { set, attack } of setAttacks(contacts)) {
    const [setter, attacker] = [playerKey(set.person, people), playerKey(attack.person, people)];
    if (setter !== null && attacker !== null && setter !== attacker) {
      const pair = pairs.get(`${setter}>${attacker}`) ?? { setter: set.person as number, attacker: attack.person as number, attacks: [] };
      pair.attacks.push(attack);
      pairs.set(`${setter}>${attacker}`, pair);
    }
  }
  const wins = (a: Contact[]) => a.filter((c) => c.result === 'point').length;
  const duo = [...pairs.values()].sort((a, b) => wins(b.attacks) - wins(a.attacks) || a.attacks.length - b.attacks.length)[0];
  if (duo && wins(duo.attacks) >= DUO_FROM) {
    out.push({ kind: 'duo', setter: duo.setter, attacker: duo.attacker, n: wins(duo.attacks), of: duo.attacks.length, contacts: duo.attacks });
  }
  const rally = longestRally(rallies);
  if (rally) {
    out.push({ kind: 'longest', rally, n: rally.contacts.filter(isTouch).length, seconds: rally.end - rally.start });
  }
  return out;
}
