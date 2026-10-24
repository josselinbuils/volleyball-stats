import type { ActionType, Contact, Placed, Result } from '@/lib/match';

export const ARROWED: ActionType[] = ['serve', 'attack'];

/** A serve or an attack, drawn from where it was played to the next touch of its rally, `landing`
 * when that is the ball hitting the floor. `line` stops short of the head, whose tip stops short of the target. */
export interface Arrow {
  from: Placed;
  to: Placed;
  result: Result;
  landing: boolean;
  line: [number, number, number, number];
  head: string;
}

export function arrows(shown: Contact[], all: Contact[]): Arrow[] {
  const out: Arrow[] = [];
  for (const c of shown) {
    const n = all[c.i + 1];
    if (!ARROWED.includes(c.type) || c.x === null || c.y === null || n?.rally !== c.rally || n.x === null || n.y === null) {
      continue;
    }
    const dx = n.x - c.x;
    const dy = n.y - c.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const landing = n.type === 'floor';
    const tip = landing ? 0.75 : 0.4;
    const ex = n.x - ux * tip;
    const ey = n.y - uy * tip;
    const point = (x: number, y: number) => `${round(x)},${round(y)}`;
    out.push({
      from: c as Placed,
      to: n as Placed,
      result: c.result,
      landing,
      line: [c.x, c.y, round(ex - ux * 0.3), round(ey - uy * 0.3)],
      head: [point(ex, ey), point(ex - ux * 0.6 - uy * 0.3, ey - uy * 0.6 + ux * 0.3), point(ex - ux * 0.6 + uy * 0.3, ey - uy * 0.6 - ux * 0.3)].join(' '),
    });
  }
  return out;
}

const round = (x: number) => Math.round(x * 1000) / 1000;
