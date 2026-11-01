/** What looks wrong in a rally, as the review's automatic reports find it (review.unusual). */
export type Problem = 'empty' | 'noServe' | 'twoServes' | 'passWithoutServe' | 'serveNotReceived' | 'fourTouches' | 'samePlayer' | 'afterFault' | 'afterPoint' | 'server' | 'noWinner';

/** A touch as the editor lists it: its player "TEAM:IDENTITY", '' when unknown. */
export interface Checked {
  type: string;
  team: number;
  player: string;
  result: string;
}

/** The problems of a rally's touches (in order, the removed ones left out; a playing fault is no touch
 * of the ball in their order, and ends the rally as a fault does): those of the rally, and
 * those of each touch by its index, on the touch that shows them. `winner` is the rally's,
 * `previous` the winner of the rally before in the same set (null: none, or unknown), `teams`
 * whether the match has teams (no winner then is a problem). */
export function problems(touches: Checked[], winner: number | null, previous: number | null, teams: boolean): { rally: Problem[]; touch: Map<number, Problem[]> } {
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
  });
  touches.forEach((c, k) => {
    const before = touches[k - 1];
    // An attack blocked for a point is the attacker's fault, the block after it.
    if (before?.result === 'error' && c.type !== 'block') {
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
  });
  if (serves.length && previous !== null && touches[serves[0]].team !== previous) {
    mark(serves[0], 'server');
  }
  if (teams && winner === null) {
    rally.push('noWinner');
  }
  return { rally, touch };
}
