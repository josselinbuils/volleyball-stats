import type { Ball } from '@/lib/ball';

/** Seconds of the ball's path averaged into the zoom's center, against its jumps. */
export const SMOOTH_S = 0.5;
/** How much the picture is enlarged on the ball. */
export const ZOOM = 2;

/** The ball's place at `time` (fractions of the picture), its samples within SMOOTH_S averaged;
 * null without any: between rallies, or the ball out of sight. */
export function ballAt(ball: Ball, time: number): { x: number; y: number } | null {
  const { fps, samples } = ball;
  // The first sample at or after the window's start, by bisection over the frames.
  let lo = 0;
  let hi = samples.length / 3;
  const from = (time - SMOOTH_S) * fps;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (samples[3 * mid] < from) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  let x = 0;
  let y = 0;
  let n = 0;
  for (let k = lo; k < samples.length / 3 && samples[3 * k] <= (time + SMOOTH_S) * fps; k += 1) {
    x += samples[3 * k + 1];
    y += samples[3 * k + 2];
    n += 1;
  }
  return n ? { x: x / n, y: y / n } : null;
}

/** The view zooming `zoom` times on `at` (fractions of the picture) in an element `width` × `height`
 * showing a `videoWidth` × `videoHeight` picture letterboxed: a scale and the translation (px) that
 * put `at` in the middle, the picture still filling its place. */
export function zoomOn(at: { x: number; y: number }, width: number, height: number, videoWidth: number, videoHeight: number, zoom = ZOOM): { scale: number; x: number; y: number } {
  const s = Math.min(width / videoWidth, height / videoHeight);
  const [w, h] = [videoWidth * s, videoHeight * s];
  const [left, top] = [(width - w) / 2, (height - h) / 2];
  const clamp = (v: number, low: number, high: number) => Math.min(high, Math.max(low, v));
  return {
    scale: zoom,
    x: clamp(width / 2 - zoom * (left + at.x * w), left + w - zoom * (left + w), left * (1 - zoom)),
    y: clamp(height / 2 - zoom * (top + at.y * h), top + h - zoom * (top + h), top * (1 - zoom)),
  };
}
