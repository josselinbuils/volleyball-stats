import type { Contact, Players } from '@/lib/match';

/** The ball between the placed touches of a rally, straight from one to the next; at the first
 * touch before it, at the last one after. */
export function ballAt(contacts: Contact[], time: number): { x: number; y: number } | null {
  const pts = contacts.filter((c): c is Contact & { x: number; y: number } => c.x !== null && c.y !== null);
  if (!pts.length) {
    return null;
  }
  const k = pts.findIndex((c) => c.t > time);
  if (k === 0 || k === -1) {
    const c = k === 0 ? pts[0] : pts[pts.length - 1];
    return { x: c.x, y: c.y };
  }
  const a = pts[k - 1];
  const b = pts[k];
  const f = (time - a.t) / (b.t - a.t);
  return { x: a.x + f * (b.x - a.x), y: a.y + f * (b.y - a.y) };
}

/** The players' feet at the sample nearest to `time`: flat [x, y, ...] lists of the left team,
 * then of the right team; none outside the sampled spans. */
export function playersAt(players: Players, fps: number, time: number): number[][] {
  const k = Math.round((time * fps) / players.step);
  const span = players.spans.find((s) => k >= s.from && k < s.from + s.samples.length);
  return span ? span.samples[k - span.from] : [[], []];
}
