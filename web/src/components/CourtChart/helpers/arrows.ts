import type { ActionType, Contact, Placed, Result } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';

export const ARROWED: ActionType[] = ['serve', 'attack'];

/** A serve or an attack, from the player who played it to the next touch of its rally, `landing`
 * when that is the ball hitting the floor or the net. `shape` is the ball's flight, a curved arrow
 * widening from the player to its head, whose tip stops at the mark it ends on; `curve` its centre
 * line. */
export interface Arrow {
  from: Placed;
  to: Placed;
  result: Result;
  landing: boolean;
  shape: string;
  curve: string;
}

// The curve's control point, off the straight line by this share of its length.
const BEND = 0.12;
// Half widths in metres at the player, at the head's base and of the head; the head's length.
// Balls still in play are drawn thinner.
const START = 0.03;
const END = 0.13;
const BARB = 0.3;
const HEAD = 0.65;
const PLAY_WIDTH = 0.6;
// The flight stops short of the mark it ends on: a player's dot or the ball on the floor.
const STOP_TOUCH = 0.45;
const STOP_LANDING = 0.38;
const STEPS = 16;

export function arrows(shown: Contact[], all: Contact[]): Arrow[] {
  const out: Arrow[] = [];
  for (const c of shown) {
    const n = all[c.i + 1];
    if (!ARROWED.includes(c.type) || c.x === null || c.y === null || n?.rally !== c.rally || n.x === null || n.y === null) {
      continue;
    }
    const landing = !isTouch(n);
    const dx = n.x - c.x;
    const dy = n.y - c.y;
    const len = Math.hypot(dx, dy) || 1;
    const stop = Math.min(landing ? STOP_LANDING : STOP_TOUCH, len / 2);
    const ex = n.x - (dx / len) * stop;
    const ey = n.y - (dy / len) * stop;
    // Bent to the left of the flight, a share of its length.
    const bend = BEND * (len - stop);
    const qx = (c.x + ex) / 2 - (dy / len) * bend;
    const qy = (c.y + ey) / 2 + (dx / len) * bend;
    const scale = c.result === 'play' ? PLAY_WIDTH : 1;
    // The head takes HEAD metres of the curve, at most nearly half of a short one.
    const neck = 1 - Math.min(HEAD / Math.hypot(ex - c.x, ey - c.y), 0.45);
    const sx = c.x;
    const sy = c.y;
    // The points `w` metres left and right of the curve at `t`.
    const across = (t: number, w: number) => {
      const x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * qx + t ** 2 * ex;
      const y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * qy + t ** 2 * ey;
      const tx = 2 * (1 - t) * (qx - sx) + 2 * t * (ex - qx);
      const ty = 2 * (1 - t) * (qy - sy) + 2 * t * (ey - qy);
      const norm = Math.hypot(tx, ty) || 1;
      return [point(x - (ty / norm) * w, y + (tx / norm) * w), point(x + (ty / norm) * w, y - (tx / norm) * w)];
    };
    const left: string[] = [];
    const right: string[] = [];
    for (let k = 0; k <= STEPS; k++) {
      const [l, r] = across((neck * k) / STEPS, (START + ((END - START) * k) / STEPS) * scale);
      left.push(l);
      right.push(r);
    }
    const [barbLeft, barbRight] = across(neck, BARB * scale);
    out.push({
      from: c as Placed,
      to: n as Placed,
      result: c.result,
      landing,
      shape: `M${left.join('L')}L${barbLeft}L${point(ex, ey)}L${barbRight}L${right.reverse().join('L')}Z`,
      curve: `M${point(c.x, c.y)}Q${point(qx, qy)} ${point(ex, ey)}`,
    });
  }
  return out;
}

const round = (x: number) => Math.round(x * 1000) / 1000;
const point = (x: number, y: number) => `${round(x)},${round(y)}`;
