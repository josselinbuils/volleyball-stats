import type { ReactNode } from 'react';

/** A dot's radius on the half courts, in metres. */
export const DOT = 0.45;
// An arrowhead's length and half width.
const HEAD = 0.35;
const WING = 0.2;

/** One half seen from behind its end line, the net at the top and 2 m of the other side beyond it, one unit a metre: x
 * toward the players' right, y away from the net. */
export function HalfCourt({ children }: { children: ReactNode }) {
  return (
    <svg aria-hidden viewBox="-5 -2.2 10 11.7" className="block h-auto max-h-72 w-full lg:max-h-60">
      <rect x={-4.5} y={-2} width={9} height={2} className="fill-court opacity-50" />
      <rect x={-4.5} y={0} width={9} height={9} className="fill-court" />
      <rect x={-4.5} y={0} width={9} height={9} className="court-line" />
      <line x1={-4.5} x2={4.5} y1={3} y2={3} className="court-line" />
      <line x1={-5} x2={5} y1={0} y2={0} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {children}
    </svg>
  );
}

/** A legend entry: a mark drawn in -1..1, then its label. */
export function Glyph({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg aria-hidden viewBox="-1 -1 2 2" className="size-3">
        {children}
      </svg>
      {label}
    </span>
  );
}

/** An arrow from the dot at [ux, uy] to the one at [sx, sy], where the two dots part: on each other the player is in place. */
export function Arrow({ from: [ux, uy], to: [sx, sy] }: { from: [number, number]; to: [number, number] }) {
  const far = Math.hypot(sx - ux, sy - uy);
  if (far < 2 * DOT + 0.05) {
    return null;
  }
  const [dx, dy] = [(sx - ux) / far, (sy - uy) / far];
  // The head on the target dot's edge with a line behind it where the gap holds both, else the head alone across the gap.
  const gap = far - 2 * DOT;
  const reach = gap >= HEAD ? far - DOT : DOT + (gap + HEAD) / 2;
  const [tx, ty] = [ux + dx * reach, uy + dy * reach];
  const [bx, by] = [tx - dx * HEAD, ty - dy * HEAD];
  return (
    <g>
      {gap > HEAD && <line x1={ux + dx * DOT} y1={uy + dy * DOT} x2={bx} y2={by} stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
      <polygon points={`${tx},${ty} ${bx - dy * WING},${by + dx * WING} ${bx + dy * WING},${by - dx * WING}`} fill="var(--foreground)" />
    </g>
  );
}
