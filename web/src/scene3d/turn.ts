// How long a body takes to turn most of the way, in seconds.
const TURN_S = 0.12;

/** The angle of a body at `from` after `seconds` turning towards `to` the short way round; at once after a long time, a jump in the video. */
export function turnedTo(from: number, to: number, seconds: number): number {
  const gap = Math.atan2(Math.sin(to - from), Math.cos(to - from));
  return from + gap * (1 - Math.exp(-seconds / TURN_S));
}
