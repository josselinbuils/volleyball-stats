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

/** Where Chromium's `buffered` `ranges` of a video of `duration` s really are: it places each loaded byte at its share of
 * the file in the timeline, the index before the frames (`head`, a share of the file) included. The frames are taken as
 * evenly spread, within 10 s on the two matches; the few seconds it reports exactly, around the playhead, go behind it,
 * under the played part. */
export function unshifted(ranges: [number, number][], duration: number, head: number): [number, number][] {
  const at = (t: number) => Math.min(duration, Math.max(0, ((t / duration - head) / (1 - head)) * duration));
  return ranges.map(([a, b]) => [at(a), at(b)]);
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
