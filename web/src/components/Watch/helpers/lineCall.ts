import type { Rally } from '@/lib/match';

/** Half the court's length and width, in metres to the lines' outer edges (the lines are in). */
export const HALF_X = 9;
export const HALF_Y = 4.5;
/** The ball's radius: a ball touching the line is in. */
export const BALL_R = 0.105;

/** A ball landing near a line at a rally's end, in or out as the point went, and the referee's call when the review says
 * it was wrong (`web.line_calls`, in data.js: the video's camera zooms on their bounce). `mark` when the measured landing agrees: where it was then, in metres, `line` the one it is told against. */
export interface LineCall {
  rally: number;
  /** The bounce, in seconds of the video. */
  t: number;
  in: boolean;
  wrongCall: boolean;
  mark: { x: number; y: number; line: 'end' | 'side' } | null;
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
