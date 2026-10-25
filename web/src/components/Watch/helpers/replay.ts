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

/** The placed floor touches of the ball from `time` back to `after` seconds earlier, with how far
 * along that window it is (0 to 1): where an impact ripples out. */
export function landingsAt(contacts: Contact[], time: number, after = 0.9): { x: number; y: number; f: number; i: number }[] {
  return contacts.filter((c) => c.type === 'floor' && c.x !== null && c.y !== null && time >= c.t && time <= c.t + after).map((c) => ({ x: c.x!, y: c.y!, f: (time - c.t) / after, i: c.i }));
}

// A player missing from a few samples, the tracker having lost them for a moment, stays where they
// were last seen for up to HOLD_S, rather than blinking out.
const HOLD_S = 0.5;

/** The players' feet at the sample nearest to `time`, and those of the HOLD_S before missing from
 * it at their last place; none past the samples. */
export function playersAt(players: Players, fps: number, time: number): { person: number; x: number; y: number }[] {
  const at = Math.round((time * fps) / players.step);
  const back = Math.round((HOLD_S * fps) / players.step);
  const seen = new Map<number, { person: number; x: number; y: number }>();
  for (let k = at; k >= Math.max(0, at - back); k--) {
    const flat = players.samples[k] ?? [];
    for (let i = 0; i < flat.length; i += 3) {
      if (!seen.has(flat[i])) {
        seen.set(flat[i], { person: flat[i], x: flat[i + 1], y: flat[i + 2] });
      }
    }
    // Past the samples, nobody.
    if (k === at && players.samples[k] === undefined) {
      return [];
    }
  }
  return [...seen.values()];
}

/** The rally whose ends the teams play on at `time`: the one being played, else the last one started
 * before, else the first. */
export function sidesAt<R extends { start: number }>(rallies: R[], time: number): R | undefined {
  return rallies.filter((r) => r.start - PAD <= time).pop() ?? rallies[0];
}
