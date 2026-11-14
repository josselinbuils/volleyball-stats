import { SLOW_BEFORE_S } from '@/helpers/slow';

/** A drag on the video's bar, near where it was pressed (or rested), moves a frame every FINE_PX. */
export const FINE_PX = 3;
/** Past this far from there, the bar follows the pointer again. */
export const FINE_SPAN_PX = 36;

/** The frames a drag of `dx` pixels moves frame by frame, null once it is past FINE_SPAN_PX. */
export function nudgeOf(dx: number): number | null {
  return Math.abs(dx) > FINE_SPAN_PX ? null : Math.round(dx / FINE_PX);
}

/** Whether the bar is coarser than the video: a pixel of it, `pxPerS` a second, spans more than a frame. */
export function coarse(pxPerS: number, fps: number): boolean {
  return pxPerS > 0 && pxPerS < fps;
}

/** The time that shows frame `frame` and reads back as it (frames rounded from time × fps): a third into it, clear of a
 * video's first frame starting a few milliseconds late. */
export function frameTime(frame: number, fps: number): number {
  return Math.max(0, (frame + 0.3) / fps);
}

/** Whether the slowed span of one of `touches` (times, sorted) starts between `from` and `to`, either way: the moment
 * the touch shown beside the video changes with the video slowing down. */
export function slowStarts(touches: readonly number[], from: number, to: number): boolean {
  const [lo, hi] = from < to ? [from, to] : [to, from];
  let a = 0;
  let b = touches.length;
  // The first touch whose span starts after lo.
  while (a < b) {
    const mid = (a + b) >> 1;
    if (touches[mid] - SLOW_BEFORE_S <= lo) {
      a = mid + 1;
    } else {
      b = mid;
    }
  }
  return a < touches.length && touches[a] - SLOW_BEFORE_S <= hi;
}

/** A drag on the bar from `x0` (pixels) at `t0` (seconds), the bar `sPerPx` seconds a pixel: a frame every FINE_PX
 * within FINE_SPAN_PX of `x0` (`nudge` the frames moved), past it the bar's own scale from there, so that leaving the
 * frames skips none. */
export function stretchedTime(dx: number, t0: number, sPerPx: number, fps: number): { time: number; nudge: number | null } {
  const n = nudgeOf(dx);
  if (n !== null) {
    return { time: frameTime(Math.round(t0 * fps) + n, fps), nudge: n };
  }
  const sign = Math.sign(dx);
  return { time: Math.max(0, t0 + sign * (FINE_SPAN_PX / FINE_PX / fps + (Math.abs(dx) - FINE_SPAN_PX) * sPerPx)), nudge: null };
}

/** Where `time` stands on the bar stretched so (`stretchedTime`), in pixels from `x0`: the thumb under the pointer. */
export function stretchedX(time: number, t0: number, sPerPx: number, fps: number): number {
  const fine = FINE_SPAN_PX / FINE_PX / fps;
  const dt = time - t0;
  return Math.abs(dt) <= fine ? dt * fps * FINE_PX : Math.sign(dt) * (FINE_SPAN_PX + (Math.abs(dt) - fine) / sPerPx);
}
