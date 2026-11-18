import { noBall } from '@/helpers/contacts';
import type { Contact } from '@/lib/match';

/** A point of the 3D scene: court metres, `h` the height above the floor. */
export interface Point3 {
  x: number;
  y: number;
  h: number;
}

const G = 9.81;
// The ball's height at each touch, in metres: a guess from the action, the camera giving none.
const HEIGHTS: Record<string, number> = { serve: 2.7, pass: 0.9, dig: 0.7, set: 2.4, attack: 2.9, relance: 1.6, block: 2.6, net: 2.2, floor: 0.11 };
// A flight longer than this hides a touch the pipeline missed: its arc stays this flight's.
const LONGEST_S = 2.2;
// A ball crossing the net clears it: its centre above the scene's net top (2.35 m) by the drawn ball's radius.
const OVER_NET = 2.6;

// The floor under the drawn ball's centre.
const FLOOR = HEIGHTS.floor;
// After a rally's last touch in the air, its fall's length in seconds and where it lands, in metres from the net on the
// other side (`over`) or past the touch on its own (`on`): a point or a serve lands in the other court, a fault long out, else near.
const POINT: Record<string, { s: number; over: number }> = { attack: { s: 0.5, over: 5 }, block: { s: 0.7, over: 1.5 }, serve: { s: 1, over: 6 } };
const FAULT: Record<string, { s: number; over: number }> = { attack: { s: 0.7, over: 10.5 }, serve: { s: 1, over: 10.5 } };
const NEAR = { s: 0.8, on: 1.5 };

const height = (c: Contact) => HEIGHTS[c.type] ?? 1.5;
type Placed3 = Point3 & { type: string; t: number; result?: Contact['result'] };

/** Where the ball falls after the rally's last touch `a` (`p` the one before): a fall of `s` seconds to `to` on the floor. */
function fallAfter(a: Placed3, p: Placed3 | undefined): { s: number; to: Point3 } {
  const side = Math.sign(a.x) || 1;
  if (a.type === 'net') {
    // Straight down along the net, on the side it came from.
    return { s: Math.sqrt((2 * Math.max(0, a.h - FLOOR)) / G), to: { x: a.x, y: a.y, h: FLOOR } };
  }
  // A serve with nothing after it still crosses.
  const over = a.result === 'error' ? FAULT[a.type] : a.result === 'point' || a.type === 'serve' ? (POINT[a.type] ?? { s: 1.2, over: 5 }) : undefined;
  if (over) {
    return { s: over.s, to: { x: -side * over.over, y: Math.max(-3.5, Math.min(3.5, a.y)), h: FLOOR } };
  }
  // On, in the way the ball came, else toward its own back line.
  const dx = p ? a.x - p.x : side;
  const dy = p ? a.y - p.y : 0;
  const len = Math.hypot(dx, dy) || 1;
  return { s: NEAR.s, to: { x: a.x + (NEAR.on * dx) / len, y: a.y + (NEAR.on * dy) / len, h: FLOOR } };
}

/** The touches' 3D places by index in the contacts. */
export type Places = Map<number, Point3> | null;

/** A touch's place: found from the ball's flights (`places`), else on the floor under it at its action's typical height. */
function placeOf(c: Contact, places: Places): Placed3 | null {
  const found = places?.get(c.i) ?? (c.x !== null && c.y !== null ? { x: c.x, y: c.y, h: height(c) } : null);
  return found && { ...found, type: c.type, t: c.t, result: c.result };
}

/** The ball at `time` in 3D: straight between the touches of a rally seen from above, and up the arc gravity gives a
 * flight of that duration (g T² / 8 at its middle), raised to clear the net when it crosses it, unless it ends or
 * starts in the net; at the first touch before it; after the last one, falling to the floor unless it is there. */
export function ball3dAt(contacts: Contact[], time: number, places: Places = null): Point3 | null {
  // A playing fault is no touch of the ball.
  const pts = contacts.flatMap((c) => {
    const at = noBall(c) ? null : placeOf(c, places);
    return at ? [at] : [];
  });
  if (!pts.length) {
    return null;
  }
  const k = pts.findIndex((c) => c.t > time);
  if (k === 0) {
    const { x, y, h } = pts[0];
    return { x, y, h };
  }
  const last = pts[pts.length - 1];
  if (k === -1 && last.type === 'floor') {
    return { x: last.x, y: last.y, h: last.h };
  }
  // Past the last touch in the air, the ball falls to the floor.
  const fall = k === -1 ? fallAfter(last, pts[pts.length - 2]) : null;
  const a = k === -1 ? last : pts[k - 1];
  const b = fall ? { ...fall.to, type: 'floor', t: last.t + fall.s } : pts[k];
  const span = b.t - a.t;
  if (time >= b.t || span <= 0) {
    return { x: b.x, y: b.y, h: b.h };
  }
  const f = (time - a.t) / span;
  const flight = Math.min(span, LONGEST_S);
  const arc = (u: number) => a.h + u * (b.h - a.h) + (G * flight * flight * u * (1 - u)) / 2;
  let h = arc(f);
  if (a.x * b.x < 0 && a.type !== 'net' && b.type !== 'net') {
    // A bump of 1 where the ball crosses the net, 0 at the touches.
    const over = a.x / (a.x - b.x);
    const u = f ** (Math.log(0.5) / Math.log(over));
    h += Math.max(0, OVER_NET - arc(over)) * 4 * u * (1 - u);
  }
  return { x: a.x + f * (b.x - a.x), y: a.y + f * (b.y - a.y), h };
}

/** The ball's path over the last `span` seconds, `steps` points from the oldest to `time`'s. */
export function trail3dAt(contacts: Contact[], time: number, places: Places = null, span = 0.35, steps = 8): Point3[] {
  const out: Point3[] = [];
  for (let k = steps - 1; k >= 0; k--) {
    const at = ball3dAt(contacts, time - (span * k) / (steps - 1), places);
    if (at) {
      out.push(at);
    }
  }
  return out;
}
