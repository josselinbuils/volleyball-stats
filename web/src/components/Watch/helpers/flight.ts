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
// Players jump to attack and block: up to JUMP_M, over JUMP_S before and after the touch.
const JUMP_M = 0.55;
const JUMP_S = 0.4;

type Placed = Contact & { x: number; y: number };

const height = (c: Contact) => HEIGHTS[c.type] ?? 1.5;

/** The ball at `time` in 3D: straight between the placed touches of a rally seen from above, and
 * up the arc gravity gives a flight of that duration (g T² / 8 at its middle); at the first touch
 * before it, at the last one after. */
export function ball3dAt(contacts: Contact[], time: number): Point3 | null {
  const pts = contacts.filter((c): c is Placed => c.x !== null && c.y !== null);
  if (!pts.length) {
    return null;
  }
  const k = pts.findIndex((c) => c.t > time);
  if (k === 0 || k === -1) {
    const c = k === 0 ? pts[0] : pts[pts.length - 1];
    return { x: c.x, y: c.y, h: height(c) };
  }
  const a = pts[k - 1];
  const b = pts[k];
  const span = b.t - a.t;
  const f = (time - a.t) / span;
  const flight = Math.min(span, LONGEST_S);
  return { x: a.x + f * (b.x - a.x), y: a.y + f * (b.y - a.y), h: height(a) + f * (height(b) - height(a)) + (G * flight * flight * f * (1 - f)) / 2 };
}

/** The ball's path over the last `span` seconds, `steps` points from the oldest to `time`'s. */
export function trail3dAt(contacts: Contact[], time: number, span = 0.35, steps = 8): Point3[] {
  const out: Point3[] = [];
  for (let k = steps - 1; k >= 0; k--) {
    const at = ball3dAt(contacts, time - (span * k) / (steps - 1));
    if (at) {
      out.push(at);
    }
  }
  return out;
}

/** How high `person` jumps at `time`: up to JUMP_M around each of their attacks and blocks. */
export function jumpAt(contacts: Contact[], person: number, time: number): number {
  let jump = 0;
  for (const c of contacts) {
    const dt = Math.abs(time - c.t);
    if (c.person === person && (c.type === 'attack' || c.type === 'block') && dt < JUMP_S) {
      jump = Math.max(jump, JUMP_M * (1 - (dt / JUMP_S) ** 2));
    }
  }
  return jump;
}
