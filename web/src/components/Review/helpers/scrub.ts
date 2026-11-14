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

/** Playing with "slow at touches" on, the video slows down from SLOW_BEFORE_S before each touch to SLOW_AFTER_S after it. */
export const SLOW_BEFORE_S = 0.5;
export const SLOW_AFTER_S = 0.3;

/** Whether `time` is in the slowed span of one of `touches` (times, sorted). */
export function nearTouch(touches: readonly number[], time: number): boolean {
  let lo = 0;
  let hi = touches.length;
  // The first touch not more than SLOW_AFTER_S behind.
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (touches[mid] < time - SLOW_AFTER_S) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo < touches.length && touches[lo] <= time + SLOW_BEFORE_S;
}
