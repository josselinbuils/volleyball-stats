/** Playing with "slow at touches" on, the video slows down to SLOW_RATE from SLOW_BEFORE_S before each touch to
 * SLOW_AFTER_S after it, in the review's video and on the match page. */
export const SLOW_BEFORE_S = 0.3;
export const SLOW_AFTER_S = 0.15;
/** Half speed (the owner's choice: the match page's since 15 Nov, the review's since 19 Nov). */
export const SLOW_RATE = 0.5;
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
