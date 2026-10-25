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

/** The ball's path over the last `span` seconds, `steps` points from the oldest to `time`'s: a trail
 * as long as the ball is fast. */
export function trailAt(contacts: Contact[], time: number, span = 0.35, steps = 6): { x: number; y: number }[] {
  const out = [];
  for (let k = steps - 1; k >= 0; k--) {
    const at = ballAt(contacts, time - (span * k) / (steps - 1));
    if (at) {
      out.push(at);
    }
  }
  return out;
}

/** The touches of a known player around `time`, from `before` seconds before each to `after` seconds
 * after, with how far along that window it is (0 to 1). */
export function touchesAt(contacts: Contact[], time: number, before = 0.1, after = 0.6): { touch: Contact; f: number }[] {
  return contacts.filter((c) => c.person !== null && time >= c.t - before && time <= c.t + after).map((touch) => ({ touch, f: (time - touch.t + before) / (before + after) }));
}

/** The players' feet at the sample nearest to `time`; none past the samples. */
export function playersAt(players: Players, fps: number, time: number): { person: number; x: number; y: number }[] {
  const flat = players.samples[Math.round((time * fps) / players.step)] ?? [];
  return Array.from({ length: flat.length / 3 }, (_, k) => ({ person: flat[3 * k], x: flat[3 * k + 1], y: flat[3 * k + 2] }));
}

/** The rally whose ends the teams play on at `time`: the one being played, else the last one started
 * before, else the first. */
export function sidesAt<R extends { start: number }>(rallies: R[], time: number): R | undefined {
  return rallies.filter((r) => r.start - PAD <= time).pop() ?? rallies[0];
}
