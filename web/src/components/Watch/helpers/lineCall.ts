import type { Rally } from '@/lib/match';

/** A ball landing near a line at a rally's end, in or out as the point went, and the referee's call when the review says
 * it was wrong (`web.line_calls`, in data.js: the camera zooms on their bounce, which the hosted video holds). `mark` when the measured landing agrees: where it was then, in metres, `line` the one it is told against. */
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
