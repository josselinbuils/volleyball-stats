import type { Contact, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';
import { scoresBefore, scoringTouch, teamFirst } from '@/helpers/plays';

// A point in a rally this long is a moment.
const LONG_RALLY = 7;
// From this many points a tie is a late one.
const LATE = 20;
// A team's best count of a stat is told from this many.
const TOP_FROM = 3;

/** A point of `key`'s worth retelling, `score` after it theirs first. */
export interface Highlight {
  kind: 'setWon' | 'longRally' | 'lateTie' | 'ace' | 'block';
  contact: Contact;
  score: [number, number];
  touches: number;
}

const KINDS: Highlight['kind'][] = ['setWon', 'longRally', 'lateTie', 'ace', 'block'];

/** `key`'s best points, at most `most`: winning a set, ending a long rally, breaking or making a late
 * tie, then aces and blocks, in that order, each of the same kind by time. */
export function highlights(rallies: Rally[], key: string, people: Record<string, Person>, most = 4): Highlight[] {
  const before = scoresBefore(rallies);
  const out: Highlight[] = [];
  for (const [k, r] of rallies.entries()) {
    const c = scoringTouch(r);
    if (!c || r.winner !== c.g || !r.score || playerKey(c.person, people) !== key) {
      continue;
    }
    const was = before.get(r.i) as [number, number];
    const touches = r.contacts.filter(isTouch).length;
    const score = teamFirst(r.score, c.g);
    const late = Math.max(...r.score) >= LATE && Math.abs(r.score[0] - r.score[1]) <= 1 && Math.abs(was[0] - was[1]) <= 1;
    const kind: Highlight['kind'] | null =
      rallies[k + 1]?.set !== r.set && score[0] > score[1] ? 'setWon' : touches >= LONG_RALLY ? 'longRally' : late ? 'lateTie' : c.type === 'serve' ? 'ace' : c.type === 'block' ? 'block' : null;
    if (kind) {
      out.push({ kind, contact: c, score, touches });
    }
  }
  return out.sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind) || a.contact.t - b.contact.t).slice(0, most);
}

/** The stats where `mine` holds the team's most, from TOP_FROM, largest first, `others` the counts
 * of the rest of the team by stat. */
export function tops<S extends string>(mine: Record<S, Contact[]>, others: Record<S, Contact[]>[], names: readonly S[]): S[] {
  return names.filter((stat) => mine[stat].length >= TOP_FROM && others.every((o) => o[stat].length <= mine[stat].length)).sort((a, b) => mine[b].length - mine[a].length);
}
