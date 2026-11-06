import type { Ball } from '@/lib/ball';
import type { MatchView } from '@/lib/match';

/** Seconds of the ball's path averaged into its place, against its jumps. */
export const SMOOTH_S = 0.5;
/** Share of the view, on each side, the ball is kept out of. */
const EDGE = 0.15;
/** The view without the review's: half the picture, in its middle. */
const NO_VIEW: MatchView = [0, 0.25, 0.25, 0.5];
/** The view's spring, in radians a second: it settles within about 5 / FOLLOW seconds. */
const FOLLOW = 5;

/** A view: its center (fractions of the picture) and how much it enlarges the picture. */
export type Camera = { x: number; y: number; zoom: number };

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

/** The automatic zoom at `time`: the review's view of the players then (`views`, framing.py's), moved
 * only as much as keeps `ball` EDGE inside it. */
export function frameAt(views: MatchView[], time: number, ball: { x: number; y: number } | null): Camera {
  const [, x, y, w] = views.findLast((v) => v[0] <= time) ?? views[0] ?? NO_VIEW;
  const keep = (from: number, at: number | undefined) => {
    const moved = at === undefined ? from : Math.min(at - EDGE * w, Math.max(at + EDGE * w - w, from));
    return Math.min(1 - w, Math.max(0, moved)) + w / 2;
  };
  return { x: keep(x, ball?.x), y: keep(y, ball?.y), zoom: 1 / w };
}

/** `now` and its `speed` moved `dt` seconds toward `target` by a critically damped spring: the view
 * sets off and stops gently, without bouncing. */
export function spring(now: Camera, speed: Camera, target: Camera, dt: number): void {
  for (const k of ['x', 'y', 'zoom'] as const) {
    speed[k] += (FOLLOW * FOLLOW * (target[k] - now[k]) - 2 * FOLLOW * speed[k]) * dt;
    now[k] += speed[k] * dt;
  }
}

/** The view zooming `zoom` times on `at` (fractions of the picture) in an element `width` × `height`
 * showing a `videoWidth` × `videoHeight` picture letterboxed: a scale and the translation (px) that
 * put `at` in the middle, the picture still filling its place. */
export function zoomOn(at: { x: number; y: number }, width: number, height: number, videoWidth: number, videoHeight: number, zoom: number): { scale: number; x: number; y: number } {
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
