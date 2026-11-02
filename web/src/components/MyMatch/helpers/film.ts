import type { Contact, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { smoothBall, type Camera3 } from '@/components/Watch/helpers/director';
import type { Places, Point3 } from '@/components/Watch/helpers/flight';
import { highlights } from '@/components/MyMatch/helpers/myMatch';

const MOMENTS = 4;
export const FILM_LEAST_MOMENTS = 2;
const INTRO_S = 2.6;
const OUTRO_S = 4.5;
// A moment plays from this long before the touch, and after it for this long.
const LEAD_S = 3.5;
const AFTER_S = 1;
const AFTER_POINT_S = 1.6;
const AFTER_FLIGHT_S = 0.5;
// Its replay, slowed down.
const REPLAY_BEFORE_S = 1;
const REPLAY_AFTER_S = 0.8;
const REPLAY_SPEED = 0.5;
// The live shot looks from behind the player's end of the court, up its length: the court fills a tall picture.
const EYE_X = 15.5;
const EYE_H = 7.5;
const LIVE_FOV = 50;
// It looks this far nearer than the ball, leaving what is near the camera clear of the caption.
const LIVE_LOOK_NEAR = 2;
// The replay circles the player at this distance, over this many radians, as the ball arrives.
const ORBIT_M = 5.2;
const ORBIT_H = 3.6;
const ORBIT_SWEEP = 0.9;
const ORBIT_FOV = 44;
// Where it looks: under the player's middle, so they stand clear of the caption with the ball over them.
const ORBIT_LOOK_H = 1.05;

export interface Shot {
  kind: 'intro' | 'live' | 'replay' | 'outro';
  /** When it starts in the film, how long it lasts. */
  start: number;
  length: number;
  /** The match time it shows from, and how fast. */
  from: number;
  speed: number;
  contact: Contact;
  rally: Rally;
}

/** A player's moments for their film, in the order it shows them: their fastest serve first, then their points, building up
 * to the best; at most one a rally, nothing they got wrong. */
export function filmMoments(rallies: Rally[], key: string, people: Record<string, Person>, mine: Contact[]): Contact[] {
  const played = mine.filter((c) => isTouch(c) && c.result !== 'error');
  const speeds = played.filter((c) => c.speed !== undefined);
  const fastest = speeds.length ? speeds.reduce((a, b) => ((b.speed as number) > (a.speed as number) ? b : a)) : null;
  const touchesIn = (c: Contact) => rallies[c.rally]?.contacts.filter(isTouch).length ?? 0;
  const candidates = [
    ...highlights(rallies, key, people, MOMENTS).map((h) => h.contact),
    ...played.filter((c) => c.result === 'point').sort((a, b) => b.t - a.t),
    ...played.filter((c) => c.result !== 'point').sort((a, b) => touchesIn(b) - touchesIn(a)),
  ];
  const seen = new Set(fastest ? [fastest.rally] : []);
  const best: Contact[] = [];
  for (const c of candidates) {
    if (seen.size < MOMENTS && !seen.has(c.rally)) {
      seen.add(c.rally);
      best.push(c);
    }
  }
  return [...(fastest ? [fastest] : []), ...best.reverse()];
}

/** The film's shots: a title, each moment played then replayed slowly, an end. */
export function filmShots(moments: Contact[], rallies: Rally[]): { shots: Shot[]; length: number } {
  const shots: Shot[] = [];
  let at = 0;
  const add = (kind: Shot['kind'], length: number, from: number, speed: number, contact: Contact, rally: Rally) => {
    shots.push({ kind, start: at, length, from, speed, contact, rally });
    at += length;
  };
  add('intro', INTRO_S, moments[0].t - LEAD_S, 1, moments[0], rallies[moments[0].rally]);
  for (const c of moments) {
    const rally = rallies[c.rally];
    const touches = rally.contacts.filter(isTouch);
    const next = touches[touches.indexOf(c) + 1];
    const from = Math.max(rally.start, c.t - LEAD_S);
    const to = c.type === 'serve' && next ? next.t + AFTER_FLIGHT_S : c.t + (c.result === 'point' ? AFTER_POINT_S : AFTER_S);
    add('live', to - from, from, 1, c, rally);
    add('replay', (REPLAY_BEFORE_S + REPLAY_AFTER_S) / REPLAY_SPEED, c.t - REPLAY_BEFORE_S, REPLAY_SPEED, c, rally);
  }
  const last = moments[moments.length - 1];
  add('outro', OUTRO_S, last.t, 1, last, rallies[last.rally]);
  return { shots, length: at };
}

/** The shot at `time` of the film, the last one past its end. */
export function shotAt(shots: Shot[], time: number): Shot {
  return shots.findLast((s) => s.start <= time) ?? shots[0];
}

/** The match time a shot shows at `time` of the film. */
export function momentOf(shot: Shot, time: number): number {
  return shot.from + (time - shot.start) * shot.speed;
}

/** Which end of the court a touch was played at, 1 or -1. */
const endOf = (c: Contact, places: Places) => Math.sign(places?.get(c.i)?.x ?? c.x ?? 0) || 1;

/** The live shot: from behind the player's end, following the ball. */
export function liveCamera(shot: Shot, moment: number, places: Places): Camera3 {
  const side = endOf(shot.contact, places);
  const ball = smoothBall(shot.rally.contacts, moment, places) ?? { x: 0, y: 0, h: 1 };
  return { eye: { x: side * EYE_X, y: ball.y * 0.4, h: EYE_H }, target: { x: ball.x + side * LIVE_LOOK_NEAR, y: ball.y, h: 0.2 + 0.3 * ball.h }, fov: LIVE_FOV };
}

/** The replay: circling the player where they play the touch, `at` their place, from their end of the court. */
export function orbitCamera(shot: Shot, moment: number, at: Pick<Point3, 'x' | 'y'>, places: Places): Camera3 {
  const side = endOf(shot.contact, places);
  const f = Math.min(1, Math.max(0, (moment - shot.from) / (shot.length * shot.speed)));
  const start = side > 0 ? 0.35 : Math.PI - 0.35;
  const angle = start - (side > 0 ? 1 : -1) * ORBIT_SWEEP * (f - 0.5);
  return { eye: { x: at.x + ORBIT_M * Math.cos(angle), y: at.y + ORBIT_M * Math.sin(angle), h: ORBIT_H }, target: { x: at.x, y: at.y, h: ORBIT_LOOK_H }, fov: ORBIT_FOV };
}

/** The idle shot under the title and the end: high over the court, turning slowly. */
export function titleCamera(time: number): Camera3 {
  const angle = 0.5 + time / 14;
  return { eye: { x: 14 * Math.cos(angle), y: 11 * Math.sin(angle), h: 5.5 }, target: { x: 0, y: 0, h: 0.5 }, fov: 58 };
}
