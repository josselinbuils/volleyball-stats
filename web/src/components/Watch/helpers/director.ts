import type { Contact, Rally } from '@/lib/match';
import type { Clip } from '@/lib/playlist';
import { isTouch } from '@/helpers/contacts';
import { scoringTouch } from '@/helpers/plays';
import { ball3dAt, jumpAt, type Places, type Point3 } from '@/components/Watch/helpers/flight';

/** What the TV director's camera does at a moment: court metres, the lens's vertical angle in degrees. */
export interface Camera3 {
  eye: Point3;
  target: Point3;
  fov: number;
}

/** A replay in the dead time after a rally: `time` the moment of the rally it shows, `f` how far it has gone (0 to 1). */
export interface ReplayMoment {
  rally: Rally;
  contact: Contact;
  time: number;
  f: number;
}

// A replay starts this long after its rally and shows the touch from BEFORE to AFTER, slowed down.
const REPLAY_AFTER_S = 1;
const BEFORE_S = 1.8;
const AFTER_S = 1;
const SLOW = 0.4;
export const REPLAY_S = (BEFORE_S + AFTER_S) / SLOW;
// Worth a replay at any time: from this many touches in the rally. Otherwise a winning attack, no more often than this.
const LONG_RALLY = 6;
const SPACING = 4;
// A clip of a rally ends this long after it without a replay.
const AFTER_RALLY_S = 2.5;
// The camera follows the ball averaged over this many seconds each side, in this many samples each side: it glides.
const SMOOTH_S = 0.5;
const SMOOTH_STEPS = 3;
// How long the serve's shot lasts after the serve, and the net-side shot around an attack without a set before it.
const SERVE_HOLD_S = 0.7;
const ATTACK_LEAD_S = 0.9;
// The net-side shot ends this long after the next touch, and at most this long after the attack.
const ATTACK_TAIL_S = 0.5;
const ATTACK_LONGEST_S = 2;
// The hall's inside: a camera stays within.
const WALL_X = 13.2;
const NET_X = 3.5;
const NET_Y = 8.5;
const NET_H = 3.4;
const NET_LOOK = 2;
const EYE_M = 1.6;
const LOOK_UNDER_M = 1.6;

/** The rallies given a replay, by index, with the touch it shows: a winning serve or block, a winning attack ending a
 * long rally or a set, and otherwise one winning attack every SPACING rallies; none without the dead time for it. */
export function replays(rallies: Rally[]): Map<number, Contact> {
  const out = new Map<number, Contact>();
  let last = -SPACING;
  rallies.forEach((r, k) => {
    const c = scoringTouch(r);
    const next = rallies[k + 1];
    if (!c || r.redo || r.wrongCall || r.winner !== c.g || !['serve', 'attack', 'block'].includes(c.type) || (next && next.start - r.end < REPLAY_AFTER_S + REPLAY_S + 1)) {
      return;
    }
    const touches = r.contacts.filter(isTouch).length;
    const setEnd = next?.set !== r.set;
    if (c.type !== 'attack' || touches >= LONG_RALLY || setEnd || k - last >= SPACING) {
      out.set(r.i, c);
      last = k;
    }
  });
  return out;
}

/** The replay showing at `time`, if any. */
export function replayAt(rallies: Rally[], chosen: Map<number, Contact>, time: number): ReplayMoment | null {
  for (const r of rallies) {
    const from = r.end + REPLAY_AFTER_S;
    const contact = chosen.get(r.i);
    if (contact && time >= from && time < from + REPLAY_S) {
      return { rally: r, contact, time: contact.t - BEFORE_S + (time - from) * SLOW, f: (time - from) / REPLAY_S };
    }
  }
  return null;
}

/** When a replay's rally starts it, for the commentary. */
export const replayStart = (rally: Rally) => rally.end + REPLAY_AFTER_S;

/** Each of `rallies` to watch one after another: from just before its serve to the end of its replay when it has one. */
export function broadcastClips(rallies: Rally[], chosen: Map<number, Contact>, duration: number): Clip[] {
  return rallies.map((r) => ({
    start: Math.max(0, r.start - 1),
    end: Math.min(duration, chosen.has(r.i) ? replayStart(r) + REPLAY_S : r.end + AFTER_RALLY_S),
    rally: r.i,
    time: r.start,
    length: r.end - r.start,
  }));
}

function smoothBall(contacts: Contact[], time: number, places: Places): Point3 | null {
  const sum = { x: 0, y: 0, h: 0 };
  let n = 0;
  for (let k = -SMOOTH_STEPS; k <= SMOOTH_STEPS; k++) {
    const at = ball3dAt(contacts, time + (SMOOTH_S * k) / SMOOTH_STEPS, places);
    if (at) {
      sum.x += at.x;
      sum.y += at.y;
      sum.h += at.h;
      n += 1;
    }
  }
  return n ? { x: sum.x / n, y: sum.y / n, h: sum.h / n } : null;
}

/** The wide shot from the near stand, moving along the court with the ball. */
function wide(ball: Point3): Camera3 {
  return { eye: { x: ball.x * 0.55, y: 13.5, h: 6.2 }, target: { x: ball.x * 0.8, y: ball.y * 0.25, h: 1.2 + 0.25 * ball.h }, fov: 38 };
}

/** The net-side shot: from the defenders' side beyond the sideline, past the post, on the attacker and the ball, no higher
 * than the block: the players stay in the picture. */
function netSide(attack: Contact, ball: Point3): Camera3 {
  const side = attack.side === 'left' ? 1 : -1;
  const attacker = attack.x ?? ball.x;
  return { eye: { x: side * NET_X, y: NET_Y, h: NET_H }, target: { x: (attacker + ball.x) / 2, y: ball.y * 0.5, h: Math.min(ball.h, NET_LOOK) }, fov: 46 };
}

/** The attack around `time` in a rally, with the moment the shot on it starts: at the set before it, else just before. */
function attackShot(touches: Contact[], time: number): Contact | undefined {
  return touches.find((c, k) => {
    if (c.type !== 'attack') {
      return false;
    }
    const before = touches[k - 1];
    const next = touches[k + 1];
    const from = before?.type === 'set' && before.g === c.g ? before.t : c.t - ATTACK_LEAD_S;
    const to = Math.min(next ? next.t + ATTACK_TAIL_S : Infinity, c.t + ATTACK_LONGEST_S);
    return time >= from && time < to;
  });
}

/** The camera while a rally plays: behind the server, then the wide shot, cutting to the net's side on each attack. */
export function rallyCamera(rally: Rally, time: number, places: Places): Camera3 {
  const touches = rally.contacts.filter(isTouch);
  const ball = smoothBall(rally.contacts, time, places) ?? { x: 0, y: 0, h: 1 };
  const serve = touches[0]?.type === 'serve' ? touches[0] : undefined;
  if (serve && time < serve.t + SERVE_HOLD_S) {
    const place = places?.get(serve.i) ?? { x: serve.x ?? 9, y: serve.y ?? 0, h: 2.4 };
    const side = Math.sign(place.x) || 1;
    return { eye: { x: side * Math.min(WALL_X, Math.abs(place.x) + 4), y: place.y * 0.7, h: 2.7 }, target: { x: -side * 2, y: place.y * 0.2, h: 1.7 }, fov: 42 };
  }
  const attack = attackShot(touches, time);
  if (attack) {
    return netSide(attack, ball);
  }
  return wide(ball);
}

/** Between rallies: the hall seen from the near stand, drifting slowly. */
export function idleCamera(time: number): Camera3 {
  return { eye: { x: 6 * Math.sin(time / 9), y: 14, h: 7 }, target: { x: 0, y: -1, h: 1 }, fov: 42 };
}

/** The camera of a replay: out of the eyes of the player `at` (their feet then), looking at the ball; without them from
 * the net's side. The ball is looked at no higher than a player sees it ahead of them. */
export function replayCamera(moment: ReplayMoment, at: { person: number; x: number; y: number } | undefined, places: Places): Camera3 {
  const { rally, time, contact } = moment;
  const ball = ball3dAt(rally.contacts, time, places) ?? { x: 0, y: 0, h: 1 };
  if (!at) {
    return netSide(contact, ball);
  }
  const away = Math.hypot(ball.x - at.x, ball.y - at.y);
  // At the player's hands the ball is overhead: they look past it, over the net.
  const target = away < 1 ? { x: -Math.sign(at.x) * 3, y: at.y * 0.5, h: LOOK_UNDER_M } : { x: ball.x, y: ball.y, h: Math.min(ball.h, LOOK_UNDER_M) };
  return { eye: { x: at.x, y: at.y, h: EYE_M + jumpAt(rally.contacts, at.person, time) }, target, fov: 62 };
}
