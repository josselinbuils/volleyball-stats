import type { ActionType, Contact, Placed, Result } from '@/lib/match';

export const ARROWED: ActionType[] = ['serve', 'attack'];

/** A serve or an attack, from the player who played it to the next touch of its rally, `landing`
 * when that is the ball hitting the floor. `shape` is the ball's flight, a curve widening from the
 * player to where the ball went and stopping at the mark it ends on; `curve` its centre line. */
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
// Half widths in metres at the player and at the end; balls still in play are drawn thinner.
const START = 0.03;
const END = 0.19;
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
    const landing = n.type === 'floor';
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
    const left: string[] = [];
    const right: string[] = [];
    for (let k = 0; k <= STEPS; k++) {
      const t = k / STEPS;
      const x = (1 - t) ** 2 * c.x + 2 * (1 - t) * t * qx + t ** 2 * ex;
      const y = (1 - t) ** 2 * c.y + 2 * (1 - t) * t * qy + t ** 2 * ey;
      const tx = 2 * (1 - t) * (qx - c.x) + 2 * t * (ex - qx);
      const ty = 2 * (1 - t) * (qy - c.y) + 2 * t * (ey - qy);
      const norm = Math.hypot(tx, ty) || 1;
      const w = (START + (END - START) * t) * scale;
      left.push(point(x - (ty / norm) * w, y + (tx / norm) * w));
      right.push(point(x + (ty / norm) * w, y - (tx / norm) * w));
    }
    out.push({
      from: c as Placed,
      to: n as Placed,
      result: c.result,
      landing,
      shape: `M${left.join('L')}L${right.reverse().join('L')}Z`,
      curve: `M${point(c.x, c.y)}Q${point(qx, qy)} ${point(ex, ey)}`,
    });
  }
  return out;
}

const round = (x: number) => Math.round(x * 1000) / 1000;
const point = (x: number, y: number) => `${round(x)},${round(y)}`;
