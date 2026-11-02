import { ofName } from '@/lib/format';
import type { Contact, Group, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { scoresBefore, scoringTouch } from '@/helpers/plays';

/** A line of commentary: `key` under `broadcast.lines`, `vars` its values, shown from `t`. `strong` lines are spoken over
 * the one going on. */
export interface Line {
  t: number;
  key: string;
  vars: Record<string, string | number>;
  strong: boolean;
}

/** How to name a player and a team in a language that needs it. */
export interface Names {
  player: (person: number | null) => string | null;
  team: (g: Group) => string;
}

// A line stays this long, or until the next one.
const SHOWN_S = 5;
const LONG_RALLY = 8;
// How many ways a line can be said: picked by the moment so that it stays the same on a replay of the moment.
const WAYS: Record<string, number> = { serve: 3, pass: 2, set: 2, attack: 3, dig: 2, block: 2, relance: 1 };
const FAULTS = ['serve', 'attack', 'pass', 'set', 'dig', 'block', 'relance', 'fault'];
const SET_AT = 25;
const LAST_SET_AT = 15;

function vars(extra: Record<string, string | number>): Record<string, string | number> {
  const out = { ...extra };
  for (const key of ['name', 'team', 'other']) {
    if (typeof out[key] === 'string') {
      out[`of${key[0].toUpperCase()}${key.slice(1)}`] = ofName(out[key] as string);
    }
  }
  return out;
}

/** The touch-by-touch line, naming who did it; none for what the rally's end says or for a touch no one is named on. */
function touchLine(c: Contact, names: Names): Line | null {
  const name = names.player(c.person);
  const ways = WAYS[c.type];
  if (!ways || !name) {
    return null;
  }
  return { t: c.t, key: `${c.type}_${c.i % ways}`, vars: vars({ name, team: names.team(c.g) }), strong: c.type === 'attack' || c.type === 'block' };
}

/** What the rally's end says: who scored, or who gave the point away, by name when known. */
function endLine(rally: Rally, names: Names, set: boolean): Line | null {
  const winner = rally.winner;
  const touches = rally.contacts.filter((c) => isTouch(c) || c.type === 'fault');
  const last = touches.at(-1);
  if (rally.redo) {
    return { t: rally.end - 0.2, key: 'redo', vars: {}, strong: true };
  }
  if (!winner || !last) {
    return null;
  }
  const scored = scoringTouch(rally);
  const score = rally.score ? (winner === 1 ? rally.score : [rally.score[1], rally.score[0]]).join('-') : '';
  const common = { team: names.team(winner), other: names.team((3 - winner) as Group), score };
  const t = Math.max(last.t + 0.2, Math.min(rally.end, (scored?.t ?? last.t) + 0.6));
  const suffix = set ? 'Set' : '';
  if (scored && scored.g === winner && ['serve', 'attack', 'block'].includes(scored.type)) {
    const name = names.player(scored.person);
    return { t, key: `${scored.type}Point${name ? '' : 'Team'}${suffix}`, vars: vars({ ...common, name: name ?? '' }), strong: true };
  }
  if (last.g !== winner && last.result === 'error') {
    const kind = FAULTS.includes(last.type) ? last.type : 'other';
    const name = names.player(last.person);
    return { t, key: `${kind}Fault${name && kind !== 'other' ? 'Named' : ''}${suffix}`, vars: vars({ ...common, name: name ?? '' }), strong: true };
  }
  return { t, key: `point${suffix}`, vars: vars(common), strong: true };
}

/** What is at stake before the serve, a tie or a set point, from the score before the rally. */
function stakes(rally: Rally, before: [number, number] | undefined, names: Names, lastSet: boolean): Line | null {
  if (!before) {
    return null;
  }
  const to = lastSet ? LAST_SET_AT : SET_AT;
  const [a, b] = before;
  const t = rally.start - 0.6;
  if ((a >= to - 1 || b >= to - 1) && a !== b) {
    return { t, key: 'setPoint', vars: vars({ team: names.team(a > b ? 1 : 2) }), strong: true };
  }
  if (a === b && a >= to - 5) {
    return { t, key: 'tie', vars: { n: a }, strong: true };
  }
  return null;
}

/** The commentary of each of `rallies` by index: the stakes, a line a touch, a word on a long rally, the end. `replayed`
 * names who a replay follows, with when it starts. */
export function commentary(rallies: Rally[], names: Names, sets: number): Map<number, Line[]> {
  const before = scoresBefore(rallies);
  const out = new Map<number, Line[]>();
  rallies.forEach((r, k) => {
    const lines: Line[] = [];
    const stake = stakes(r, before.get(r.i), names, r.set === sets && sets >= 5);
    if (stake) {
      lines.push(stake);
    }
    const touches = r.contacts.filter(isTouch);
    const scored = scoringTouch(r);
    touches.forEach((c, n) => {
      // The rally's end tells its last touch and the one that scored.
      if (c === scored || (n === touches.length - 1 && c.result === 'error')) {
        return;
      }
      const line = touchLine(c, names);
      if (line) {
        lines.push(line);
      }
      if (n + 1 === LONG_RALLY) {
        lines.push({ t: c.t + 0.3, key: 'longRally', vars: {}, strong: false });
      }
    });
    const end = endLine(r, names, rallies[k + 1]?.set !== r.set && r.score !== null);
    if (end) {
      lines.push(end);
    }
    out.set(
      r.i,
      lines.sort((a, b) => a.t - b.t),
    );
  });
  return out;
}

/** The line to show at `time` among `lines`. */
export function lineAt(lines: Line[] | undefined, time: number): Line | null {
  const line = lines?.findLast((l) => l.t <= time);
  return line && time - line.t < SHOWN_S ? line : null;
}
