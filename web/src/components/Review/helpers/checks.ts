/** What looks wrong in a rally, as the review's automatic reports find it (review.unusual). */
export type Problem =
  | 'empty'
  | 'noServe'
  | 'twoServes'
  | 'passWithoutServe'
  | 'serveNotReceived'
  | 'fourTouches'
  | 'samePlayer'
  | 'relanceFirst'
  | 'relanceSecond'
  | 'setOver'
  | 'afterFault'
  | 'afterPoint'
  | 'server'
  | 'noWinner'
  | 'gap'
  | DoubtfulProblem;

/** What may well be right after all, in an amateur match: a rally checked shows none of them. */
type DoubtfulProblem = 'doubleTouch' | 'overThenSameTeam' | 'setToOtherTeam' | 'setFirst' | 'digLater' | 'twoSets' | 'endsOnSet' | 'pointOnTouch' | HeightDoubt;

/** A touch whose ball's height doubts of its action (`review.odd_heights`): reported by the server, not found here. */
export type HeightDoubt = 'highRelance';

// Over this long between two touches, in seconds, one is often missing (review.GAP_S).
const GAP_S = 2.5;
// Under this long after a team's touch, in seconds, a touch is often the same one seen twice.
const DOUBLE_SAME_TEAM_S = 0.3;
const DOUBLE_OTHER_TEAM_S = 0.25;

/** A touch as the editor lists it: its player "TEAM:IDENTITY", '' when unknown. */
export interface Checked {
  type: string;
  team: number;
  player: string;
  result: string;
  /** In seconds. */
  time?: number;
}

/** Where a rally's warnings sit on the match bar, in seconds: on each touch showing one, at its `start` for no touch, at its `end` for how it ended. */
export function warningTimes(found: { rally: Problem[]; touch: Map<number, Problem[]> } | undefined, touches: { time: number }[], start: number, end: number, off: boolean): number[] {
  const times = [...(found?.touch.keys() ?? [])].map((k) => touches[k].time);
  return [...new Set([...(found?.rally.includes('empty') ? [start] : []), ...times, ...(off || found?.rally.includes('noWinner') ? [end] : [])])];
}

/** The problems of a rally's touches (in order, the removed ones left out; a playing fault is no touch
 * of the ball in their order, and ends the rally as a fault does): those of the rally, and
 * those of each touch by its index, on the touch that shows them. `winner` is the rally's,
 * `previous` the winner of the rally before in the same set (null: none, or unknown), `teams`
 * whether the match has teams (no winner then is a problem; a rally to replay says false),
 * `validated` whether the rally is checked as it stands. */
export function problems(touches: Checked[], winner: number | null, previous: number | null, teams: boolean, validated = false): { rally: Problem[]; touch: Map<number, Problem[]> } {
  const rally: Problem[] = [];
  const touch = new Map<number, Problem[]>();
  const mark = (k: number, p: Problem) => touch.set(k, [...(touch.get(k) ?? []), p]);
  // The touches of the ball by their index, playing faults aside.
  const played = touches.flatMap((c, k) => (c.type === 'fault' ? [] : [k]));
  if (!touches.length) {
    rally.push('empty');
  } else if (played.length && touches[played[0]].type !== 'serve') {
    mark(played[0], 'noServe');
  }
  const serves = played.filter((k) => touches[k].type === 'serve');
  serves.slice(1).forEach((k) => mark(k, 'twoServes'));
  played.forEach((k, n) => {
    const c = touches[k];
    const b = n > 0 ? played[n - 1] : undefined;
    const before = b === undefined ? undefined : touches[b];
    if (c.type === 'pass' && before?.type !== 'serve') {
      mark(k, 'passWithoutServe');
    }
    if (before?.type === 'serve' && c.type !== 'pass') {
      mark(b!, 'serveNotReceived');
    }
    if (before && before.type !== 'block' && before.player && before.player === c.player) {
      mark(k, 'samePlayer');
    }
    // A team's first touch (after the other team's touch but a serve, or after a block) is a dig, never a relance.
    if (c.type === 'relance' && before && (before.type === 'block' || (before.team !== c.team && before.type !== 'serve'))) {
      mark(k, 'relanceFirst');
    }
    if (before?.time !== undefined && c.time !== undefined && c.time - before.time > GAP_S) {
      mark(k, 'gap');
    }
  });
  touches.forEach((_, k) => {
    const before = touches[k - 1];
    if (before?.result === 'error') {
      mark(k, 'afterFault');
    }
    if (before?.result === 'point') {
      mark(k, 'afterPoint');
    }
  });
  let run = 0;
  played.forEach((k, n) => {
    const c = touches[k];
    run = c.type === 'block' ? 0 : n && touches[played[n - 1]].team === c.team ? run + 1 : 1;
    if (run === 4) {
      mark(k, 'fourTouches');
    }
    // Both hands on a team's second touch make a relance when the other team plays next, a set when its own plays on.
    const after = n + 1 < played.length ? touches[played[n + 1]] : undefined;
    if (run === 2 && after) {
      const on = after.type !== 'block' && after.team === c.team;
      if (c.type === 'relance' && on) {
        mark(k, 'relanceSecond');
      } else if (c.type === 'set' && !on && validated) {
        mark(k, 'setOver');
      }
    }
  });
  if (serves.length && previous !== null && touches[serves[0]].team !== previous) {
    mark(serves[0], 'server');
  }
  if (teams && winner === null) {
    rally.push('noWinner');
  }
  if (!validated) {
    doubtful(touches, played, teams, mark);
  }
  return { rally, touch };
}

/** Marks what `DoubtfulProblem` lists on `played`, the touches of the ball by their index. On the two matches reviewed, 82-100% of these flags sit on a correction. */
function doubtful(touches: Checked[], played: number[], teams: boolean, mark: (k: number, p: Problem) => void): void {
  // Each touch's rank in its team's run: a relance on a team's 2nd touch its team plays on is already a problem (relanceSecond).
  const runs: number[] = [];
  played.forEach((k, n) => runs.push(touches[k].type === 'block' ? 0 : n && touches[played[n - 1]].team === touches[k].team ? runs[n - 1] + 1 : 1));
  played.forEach((k, n) => {
    if (!n) {
      return;
    }
    const b = played[n - 1]!;
    const before = touches[b]!;
    const c = touches[k]!;
    const same = before.team === c.team;
    const blocked = before.type === 'block' || c.type === 'block';
    if (before.time !== undefined && c.time !== undefined) {
      const apart = c.time - before.time;
      if (same ? apart <= DOUBLE_SAME_TEAM_S : apart <= DOUBLE_OTHER_TEAM_S && !blocked) {
        mark(k, 'doubleTouch');
      }
    }
    if (blocked) {
      return;
    }
    if (same && (before.type === 'attack' || (before.type === 'relance' && runs[n - 1] !== 2))) {
      mark(k, 'overThenSameTeam');
    }
    if (!same && before.type === 'set') {
      mark(b, 'setToOtherTeam');
    }
    if (!same && c.type === 'set') {
      mark(k, 'setFirst');
    }
    if (same && (c.type === 'dig' || c.type === 'pass')) {
      mark(k, 'digLater');
    }
    if (same && before.type === 'set' && c.type === 'set') {
      mark(k, 'twoSets');
    }
  });
  const end = played.at(-1);
  // A playing fault after it ends the rally.
  if (!teams || end === undefined || end !== touches.length - 1) {
    return;
  }
  const last = touches[end]!;
  if (last.type === 'set') {
    mark(end, 'endsOnSet');
  } else if (last.result === 'point' && ['pass', 'dig'].includes(last.type)) {
    mark(end, 'pointOnTouch');
  }
}
