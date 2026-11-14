import type { Ball } from '@/lib/ball';
import type { Contact } from '@/lib/match';

/** Seconds of the ball's path its trail shows: as long as the ball is fast. */
export const TRAIL_S = 0.5;
/** Two samples further apart than this are not joined: the ball was out of sight between them. */
export const GAP_S = 0.25;
/** A serve's speed shows from this long after its hit, the ball clear of the server, */
const SPEED_FROM_S = 0.15;
/** until the next touch, or this long after the hit. */
const SPEED_FOR_S = 2;

/** A place in the picture (fractions of it), or on the screen (px). */
export type Point = { x: number; y: number };
/** A point of the trail, `age` the seconds since the ball was there. */
export type Aged = Point & { age: number };
/** A view of the picture as the zoom sets it: enlarged `scale` times, then moved by `x`, `y` px. */
export type View = { scale: number; x: number; y: number };

/** The first sample of `samples` (flat [seconds, x, y, ...]) at or after `time`, by bisection. */
function firstFrom(samples: number[], time: number): number {
  let lo = 0;
  let hi = samples.length / 3;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (samples[3 * mid] < time) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

/** The ball's place at `time`, between the samples around it; null where they are over GAP_S apart or one is missing. */
export function placeAt(ball: Ball, time: number): Point | null {
  const { samples } = ball;
  const after = firstFrom(samples, time);
  if (after >= samples.length / 3) {
    return null;
  }
  const [t1, x1, y1] = samples.slice(3 * after, 3 * after + 3);
  if (t1 === time) {
    return { x: x1, y: y1 };
  }
  if (after === 0 || t1 - samples[3 * after - 3] > GAP_S) {
    return null;
  }
  const [t0, x0, y0] = samples.slice(3 * after - 3, 3 * after);
  const share = (time - t0) / (t1 - t0);
  return { x: x0 + (x1 - x0) * share, y: y0 + (y1 - y0) * share };
}

/** The ball's path over the TRAIL_S before `time`, from the oldest place to the newest: the samples seen without a gap
 * back from `time`, then its place at `time` where it is seen. The ball out of sight, its last places stay, ageing. */
export function trailAt(ball: Ball, time: number): Aged[] {
  const { samples } = ball;
  const trail: Aged[] = [];
  let next: number | null = null;
  for (let k = firstFrom(samples, time) - 1; k >= 0; k -= 1) {
    const t = samples[3 * k];
    if (time - t >= TRAIL_S || (next !== null && next - t > GAP_S)) {
      break;
    }
    trail.unshift({ x: samples[3 * k + 1], y: samples[3 * k + 2], age: time - t });
    next = t;
  }
  const head = placeAt(ball, time);
  if (head && (trail.length === 0 || trail[trail.length - 1].age > 0)) {
    trail.push({ ...head, age: 0 });
  }
  return trail;
}

/** `points` joined by a smooth curve (through the middle of each segment, bending at each point, so never past them),
 * as marks every `spacing` along it, each with its age. Under two points, nothing to join. */
export function stamps(points: Aged[], spacing: number): Aged[] {
  if (points.length < 2) {
    return [];
  }
  const mid = (a: Aged, b: Aged): Aged => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, age: (a.age + b.age) / 2 });
  const out: Aged[] = [];
  // Each piece: from `a` to `b`, bending toward `bend`.
  const piece = (a: Aged, bend: Aged, b: Aged) => {
    const length = Math.hypot(bend.x - a.x, bend.y - a.y) + Math.hypot(b.x - bend.x, b.y - bend.y);
    const n = Math.max(1, Math.ceil(length / spacing));
    for (let k = out.length ? 1 : 0; k <= n; k += 1) {
      const s = k / n;
      const [wa, wc, wb] = [(1 - s) * (1 - s), 2 * s * (1 - s), s * s];
      out.push({ x: wa * a.x + wc * bend.x + wb * b.x, y: wa * a.y + wc * bend.y + wb * b.y, age: wa * a.age + wc * bend.age + wb * b.age });
    }
  };
  let from = points[0];
  for (let k = 1; k < points.length - 1; k += 1) {
    const to = mid(points[k], points[k + 1]);
    piece(from, points[k], to);
    from = to;
  }
  const last = points[points.length - 1];
  piece(from, mid(from, last), last);
  return out;
}

/** Where a place of the picture (fractions of it) stands, in px, in an element `width` × `height` showing a
 * `videoWidth` × `videoHeight` picture letterboxed and zoomed by `view` (zoom.zoomOn's); `unit` the picture's width there. */
export function onScreen(width: number, height: number, videoWidth: number, videoHeight: number, view: View): { at: (p: Point) => Point; unit: number } {
  const s = Math.min(width / videoWidth, height / videoHeight);
  const [w, h] = [videoWidth * s, videoHeight * s];
  const [left, top] = [(width - w) / 2, (height - h) / 2];
  return { at: (p) => ({ x: view.x + view.scale * (left + p.x * w), y: view.y + view.scale * (top + p.y * h) }), unit: w * view.scale };
}

/** A serve's speed (km/h) and the seconds it shows between. */
export type Shown = { from: number; until: number; speed: number };

/** When each measured serve's speed shows: from just after its hit to the rally's next touch, SPEED_FOR_S at most. */
export function serveSpeeds(contacts: Contact[]): Shown[] {
  return contacts.flatMap((c, k) => {
    if (c.type !== 'serve' || c.speed === undefined) {
      return [];
    }
    const next = contacts[k + 1];
    const until = Math.min(c.t + SPEED_FOR_S, next && next.rally === c.rally ? next.t : Infinity);
    return until > c.t + SPEED_FROM_S ? [{ from: c.t + SPEED_FROM_S, until, speed: c.speed }] : [];
  });
}

/** The speed showing at `time`, `shown` by time. */
export function speedAt(shown: Shown[], time: number): Shown | null {
  const last = shown.findLast((s) => s.from <= time);
  return last && time < last.until ? last : null;
}
