import type { CSSProperties } from 'react';

/** Height (px) of the seek bar's line, in the middle of its box. */
const LINE_PX = 4;
/** Loaded parts narrower than this share of the bar, and gaps as narrow between two, are only noise: a few pixels. */
const MIN_SHARE = 0.004;

/** The seek bar's line over `start`..`end`: played up to `time` in `played`, the stretches of `held` (the video's loaded
 * parts, in order) in `heldColor` past MIN_SHARE, the rest in `rest`. */
export function seekLine(time: number, start: number, end: number, held: [number, number][], colors: { played: string; heldColor: string; rest: string }): CSSProperties {
  const share = (at: number) => `${(100 * (Math.min(end, Math.max(start, at)) - start)) / Math.max(1e-9, end - start)}%`;
  const solid = (color: string) => `linear-gradient(${color}, ${color})`;
  const min = MIN_SHARE * (end - start);
  const shown: [number, number][] = [];
  for (const [a, b] of held) {
    const last = shown.at(-1);
    if (last && a - last[1] < min) {
      last[1] = Math.max(last[1], b);
    } else {
      shown.push([a, b]);
    }
  }
  const parts = shown.filter(([a, b]) => Math.min(b, end) - Math.max(a, start) >= min).map(([a, b]) => `transparent ${share(a)}, ${colors.heldColor} ${share(a)} ${share(b)}, transparent ${share(b)}`);
  const layers = [solid(colors.played), ...(parts.length ? [`linear-gradient(to right, ${parts.join(', ')})`] : []), solid(colors.rest)];
  return {
    backgroundImage: layers.join(', '),
    backgroundSize: layers.map((_, k) => `${k ? '100%' : share(time)} ${LINE_PX}px`).join(', '),
    backgroundPosition: 'left center',
    backgroundRepeat: 'no-repeat',
  };
}

/** Where Chromium's `buffered` `ranges` of a video of `duration` s really are, for a copy of it standing at `at`: it
 * places each loaded byte at its share of the file in the timeline, which the file's `index` ([time, share of the file]
 * in order, every 10 s) reads back, within 2 s on the two matches. Around `at` it joins the few seconds it reads exactly,
 * which need no reading back: that range's end is the lesser of both readings, never past what is loaded. */
export function unshifted(ranges: [number, number][], duration: number, index: [number, number][], at: number): [number, number][] {
  const place = (t: number) => {
    const share = t / duration;
    const k = index.findLastIndex(([, s]) => s <= share);
    if (k < 0) {
      return 0;
    }
    const [t0, s0] = index[k];
    const [t1, s1] = index[k + 1] ?? [duration, 1];
    return Math.min(duration, t0 + ((share - s0) / Math.max(1e-12, s1 - s0)) * (t1 - t0));
  };
  return ranges.map(([a, b]) => (a <= at && at <= b ? [Math.min(a, place(a)), Math.max(at, Math.min(b, place(b)))] : [place(a), place(b)]));
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
