import type { Contact } from '@/lib/match';
import type { Players } from '@/lib/players';
import { PAD } from '@/lib/playlist';

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

/** The players' feet at the sample nearest to `time`; none past the samples. */
export function playersAt(players: Players, fps: number, time: number): { track: number; x: number; y: number }[] {
  const flat = players.samples[Math.round((time * fps) / players.step)] ?? [];
  return Array.from({ length: flat.length / 3 }, (_, k) => ({ track: flat[3 * k], x: flat[3 * k + 1], y: flat[3 * k + 2] }));
}

/** The rally whose ends the teams play on at `time`: the one being played, else the last one started
 * before, else the first. */
export function sidesAt<R extends { start: number }>(rallies: R[], time: number): R | undefined {
  return rallies.filter((r) => r.start - PAD <= time).pop() ?? rallies[0];
}
