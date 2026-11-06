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
 * places each loaded byte at its share of the file in the timeline, the index before the frames (`head`, a share of the
 * file) included; the frames are taken as evenly spread, within 10 s on the two matches. The few seconds around `at` it
 * reads exactly: that range stays. */
export function unshifted(ranges: [number, number][], duration: number, head: number, at: number): [number, number][] {
  const place = (t: number) => Math.min(duration, Math.max(0, ((t / duration - head) / (1 - head)) * duration));
  return ranges.map(([a, b]) => (a <= at && at <= b ? [a, b] : [place(a), place(b)]));
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
