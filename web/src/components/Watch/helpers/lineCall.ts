import type { Contact, Group, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';

/** Half the court's length and width, in metres to the lines' outer edges (the lines are in). */
export const HALF_X = 9;
export const HALF_Y = 4.5;
/** The ball's radius: a ball touching the line is in. */
export const BALL_R = 0.105;
/** A landing this near a line is a close call. */
export const NEAR_M = 0.4;

/** A ball landing near a line at a rally's end, in or out as the point went, and the referee's call when the review says
 * it was wrong. `mark` when the measured landing agrees: where it was then, in metres, `line` the one it is told against. */
export interface LineCall {
  rally: number;
  /** The bounce, in seconds of the video. */
  t: number;
  in: boolean;
  wrongCall: boolean;
  mark: { x: number; y: number; line: 'end' | 'side' } | null;
}

/** How far a ball centred on (x, y) lands outside the court (negative inside), and the line it is told against: the one
 * it is past, else the nearest. */
export function outside(x: number, y: number): { by: number; line: 'end' | 'side' } {
  const [dx, dy] = [Math.abs(x) - HALF_X, Math.abs(y) - HALF_Y];
  if (dx > 0 || dy > 0) {
    return { by: Math.hypot(Math.max(0, dx), Math.max(0, dy)), line: dx >= dy ? 'end' : 'side' };
  }
  return dx >= dy ? { by: dx, line: 'end' } : { by: dy, line: 'side' };
}

/** The rallies ending on a ball landing near a line on the other side from its last touch, by time; with a wrong call, any
 * such landing. In or out from who won the point (the other team on a wrong call), the measured mark kept where it says the
 * same; a close landing where it does not is left out. */
export function lineCalls(rallies: Rally[]): LineCall[] {
  const out: LineCall[] = [];
  for (const r of rallies) {
    if (r.winner === null || r.redo) {
      continue;
    }
    const played = r.contacts.filter((c) => c.type !== 'fault');
    const land = played.at(-1);
    const hit = played.findLast(isTouch);
    if (!land || land.type !== 'floor' || !hit || land.x === null || land.y === null || hit.x === null || Math.sign(land.x) === Math.sign(hit.x)) {
      continue;
    }
    const won: Group = r.wrongCall ? (r.winner === 1 ? 2 : 1) : r.winner;
    const isIn = won === (hit as Contact).g;
    const { by, line } = outside(land.x, land.y);
    const agrees = by <= BALL_R === isIn;
    if (r.wrongCall || (agrees && Math.abs(by) <= NEAR_M)) {
      out.push({ rally: r.i, t: land.t, in: isIn, wrongCall: !!r.wrongCall, mark: agrees ? { x: land.x, y: land.y, line } : null });
    }
  }
  return out.sort((a, b) => a.t - b.t);
}

/** The call shown at `time`: from just after its bounce for `hold` seconds, until the next rally starts. */
export function callAt(calls: LineCall[], rallies: Rally[], time: number, after: number, hold: number): LineCall | null {
  const call = calls.findLast((c) => c.t + after <= time);
  if (!call || time > call.t + after + hold) {
    return null;
  }
  const next = rallies[call.rally + 1];
  return next && time >= next.start ? null : call;
}

/** The mark seen from outside the court, its line across: `u` along the line, `v` outward from its outer edge (positive
 * out), and the court's corner along it at `corner` (u), all in metres. */
export function local(mark: NonNullable<LineCall['mark']>): { u: number; v: number; corner: number } {
  return mark.line === 'end' ? { u: mark.y * Math.sign(mark.x), v: Math.abs(mark.x) - HALF_X, corner: HALF_Y } : { u: -mark.x * Math.sign(mark.y), v: Math.abs(mark.y) - HALF_Y, corner: HALF_X };
}
