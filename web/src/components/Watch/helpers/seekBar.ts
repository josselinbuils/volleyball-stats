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
