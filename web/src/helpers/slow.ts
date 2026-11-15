/** Playing with "slow at touches" on, the video slows down from SLOW_BEFORE_S before each touch to SLOW_AFTER_S after
 * it: to SLOW_RATE in the review's video, PAGE_SLOW_RATE on the match page. */
export const SLOW_BEFORE_S = 0.3;
export const SLOW_AFTER_S = 0.15;
export const SLOW_RATE = 0.25;
/** On the match page, to watch rather than to answer: half speed (the owner's choice, 15 Nov). */
export const PAGE_SLOW_RATE = 0.5;
/** Seconds the sound takes to fade out as the video slows, and back: slowed, it only warbles. */
export const SOUND_FADE_S = 0.15;

/** The volume one frame `dt` seconds on from `volume`, toward silence while `slowed`, else toward full. */
export function fadedVolume(volume: number, slowed: boolean, dt: number): number {
  const step = Math.max(0, dt) / SOUND_FADE_S;
  return slowed ? Math.max(0, volume - step) : Math.min(1, volume + step);
}

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
