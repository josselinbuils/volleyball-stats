import type { CSSProperties } from 'react';

/** Height (px) of the seek bar's line, in the middle of its box. */
const LINE_PX = 4;

/** The seek bar's line over `start`..`end`: played up to `time` in `played`, the stretches of `held` (the video's loaded
 * parts) in `heldColor`, the rest in `rest`. */
export function seekLine(time: number, start: number, end: number, held: [number, number][], colors: { played: string; heldColor: string; rest: string }): CSSProperties {
  const share = (at: number) => `${(100 * (Math.min(end, Math.max(start, at)) - start)) / Math.max(1e-9, end - start)}%`;
  const solid = (color: string) => `linear-gradient(${color}, ${color})`;
  const parts = held.filter(([a, b]) => b > start && a < end).map(([a, b]) => `transparent ${share(a)}, ${colors.heldColor} ${share(a)} ${share(b)}, transparent ${share(b)}`);
  const layers = [solid(colors.played), ...(parts.length ? [`linear-gradient(to right, ${parts.join(', ')})`] : []), solid(colors.rest)];
  return {
    backgroundImage: layers.join(', '),
    backgroundSize: layers.map((_, k) => `${k ? '100%' : share(time)} ${LINE_PX}px`).join(', '),
    backgroundPosition: 'left center',
    backgroundRepeat: 'no-repeat',
  };
}

/** Chromium's place in the timeline of a video of `duration` s, read back to its real time: Chromium places each
 * loaded byte at its share of the file, which the file's `index` ([time, share of the file] in order, every 10 s) reads
 * back, within 2 s on the two matches. */
export function placer(duration: number, index: [number, number][]): (t: number) => number {
  return (t) => {
    const share = t / duration;
    const k = index.findLastIndex(([, s]) => s <= share);
    if (k < 0) {
      return 0;
    }
    const [t0, s0] = index[k];
    const [t1, s1] = index[k + 1] ?? [duration, 1];
    return Math.min(duration, t0 + ((share - s0) / Math.max(1e-12, s1 - s0)) * (t1 - t0));
  };
}

/** The playing copy's `ranges` (Chromium's `buffered`) read back, the copy standing at `at`. Around `at` Chromium joins
 * the few seconds it reads exactly, which need no reading back: that range's end is the lesser of both readings. */
export function unshifted(ranges: [number, number][], place: (t: number) => number, at: number): [number, number][] {
  return ranges.map(([a, b]) => (a <= at && at <= b ? [Math.min(a, place(a)), Math.max(at, Math.min(b, place(b)))] : [place(a), place(b)]));
}

/** Seconds before where a copy stands that its download may start: the keyframe before (one every 2 s). */
const KEYFRAME_S = 2.5;

/** Whether `range`, among a copy's ranges (Chromium's `buffered`), is that copy's own download where it stands, at `at`,
 * the copy not playing: it grew since the copy's `previous` ranges and, read back, starts at the keyframe before `at`.
 * Chromium also keeps an exact range at each place a copy stood, and its estimates of other downloads: only one copy's
 * own growing download starts there. */
export function isDownload([a, b]: [number, number], previous: [number, number][], place: (t: number) => number, at: number): boolean {
  const near = (x: number) => at - KEYFRAME_S <= x && x <= at + 0.5;
  const grew = !previous.some(([c, d]) => c <= a + 0.01 && d >= b - 0.01);
  const exact = near(a) && Math.abs(place(a) - a) > KEYFRAME_S;
  return grew && !exact && near(place(a)) && place(b) > place(a);
}

/** Seconds a loaded part may start after one of `points` and still count as loaded from there. */
const FROM_S = 2;

/** The `ranges` holding one of `points` (where the video stands, the next clips' starts), or starting just after it: what
 * the browser loads for them. The others are what it loaded once and may have dropped since. */
export function around(ranges: [number, number][], points: number[]): [number, number][] {
  return ranges.filter(([a, b]) => points.some((p) => a <= p + FROM_S && p <= b));
}

/** `ranges` in order, those overlapping or touching joined: a gradient's stops must not go back. */
export function merged(ranges: [number, number][]): [number, number][] {
  const out: [number, number][] = [];
  for (const [a, b] of [...ranges].sort((x, y) => x[0] - y[0])) {
    const last = out.at(-1);
    if (last && a <= last[1]) {
      last[1] = Math.max(last[1], b);
    } else {
      out.push([a, b]);
    }
  }
  return out;
}

/** The parts of `ranges` inside `windows`, both in order. */
export function within(ranges: [number, number][], windows: [number, number][]): [number, number][] {
  return merged(windows.flatMap(([c, d]) => ranges.filter(([a, b]) => b > c && a < d).map(([a, b]): [number, number] => [Math.max(a, c), Math.min(b, d)])));
}
