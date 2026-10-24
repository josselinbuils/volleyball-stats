/** Seconds shown around a set's rallies on its timeline. */
const MARGIN = 10;

/** The stretch of video a set's timeline shows: its rallies with a margin, within the video. */
export function span(rallies: { start: number; end: number }[], duration: number): [number, number] {
  if (!rallies.length) {
    return [0, duration];
  }
  return [Math.max(0, rallies[0].start - MARGIN), Math.min(duration, rallies[rallies.length - 1].end + MARGIN)];
}

/** Where each set after the first begins: halfway between the last rally of the previous set and its
 * first rally. */
export function setBreaks(rallies: { start: number; end: number; set: number }[]): { time: number; set: number }[] {
  return rallies.slice(1).flatMap((r, k) => (r.set !== rallies[k].set ? [{ time: (rallies[k].end + r.start) / 2, set: r.set }] : []));
}

/** Round clock times from `from` to `to`, about six of them. */
export function ticks(from: number, to: number): number[] {
  const minutes = (to - from) / 60;
  const step = 60 * ([1, 2, 5, 10, 15, 30, 60].find((s) => minutes / s <= 6) ?? 120);
  const out = [];
  for (let s = Math.ceil(from / step) * step; s <= to; s += step) {
    out.push(s);
  }
  return out;
}
