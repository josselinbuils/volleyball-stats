import type { Contact, Person, Rally } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { playerKey } from '@/helpers/players';
import { ball3dAt, type Places, type Point3 } from '@/components/Watch/helpers/flight';

/** An arm: `pitch` its angle up from hanging down, forward at a quarter turn, overhead at a half; `roll` towards the other
 * arm; `stretch` its length against its rest. */
export interface Arm {
  pitch: number;
  roll: number;
  stretch: number;
}

/** How a figure stands at a moment: all of it a function of the moment, so pausing, jumping and slowing down just work.
 * `shift` moves it towards the ball it reaches for, `arms` its right arm first, `stride` swings its legs. */
export interface Pose {
  jump: number;
  crouch: number;
  lean: number;
  stride: number;
  shift: { x: number; y: number };
  arms: [Arm, Arm];
}

/** A player on the court at a moment. */
export interface Dot {
  person: number;
  x: number;
  y: number;
}

// The figure: its shoulders' height and its arm's length, which stretches this much at most.
const SHOULDER_M = 1.08;
const ARM_M = 0.48;
const STRETCH = 1.7;
const TOP_M = SHOULDER_M + ARM_M * STRETCH;
// How high each action jumps at most, and half its time in the air: the ball decides within that.
const JUMPS: Partial<Record<Contact['type'], { most: number; half: number }>> = {
  attack: { most: 0.9, half: 0.4 },
  block: { most: 0.8, half: 0.4 },
  serve: { most: 0.6, half: 0.35 },
  set: { most: 0.25, half: 0.2 },
};
// Running: a steady cadence, its strength from the speed, measured this long each side of the moment.
const CADENCE_HZ = 2.4;
export const SPEED_S = 0.25;
const WALK = 0.5;
const SPRINT = 3.5;
const ARM_SWING = 0.7;
const STRIDE = 0.9;
// Set for the next ball while a rally plays, relaxed outside it, over this long.
const READY_S = 1;
const READY = { crouch: 0.15, pitch: 0.45 };
const EASE_S = 0.15;
// A body within this of the ball leans into it, up to REACH_M; further, the ball's place cannot be trusted to aim at.
const AIM_M = 2.5;
const REACH_M = 1.2;
const ARM_ROOM_M = 0.35;
// Another body takes a touch whose named player is not within SAME_M, the nearest of their team within NEAREST_M.
const SAME_M = 3;
const NEAREST_M = 2;
// A touch's window around its contact, in seconds.
const WINDOWS: Partial<Record<Contact['type'], [number, number]>> = {
  serve: [-1, 0.55],
  pass: [-0.6, 0.45],
  dig: [-0.45, 0.5],
  set: [-0.6, 0.5],
  relance: [-0.6, 0.5],
  attack: [-0.9, 0.8],
  block: [-0.6, 0.7],
};
// The serve: the ball rests in the server's hand, then flies to where it is hit from.
const TOSS_S = 0.7;
const HAND_M = 1.05;
const TOSS_M = 1.1;

const smooth = (a: number, b: number, x: number) => {
  const u = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return u * u * (3 - 2 * u);
};
const mix = (a: number, b: number, u: number) => a + (b - a) * u;

/** The value at `t` of `keys`, [time, value] in time order, eased between them and held outside. */
export function keyed(keys: [number, number][], t: number): number {
  if (t <= keys[0][0]) {
    return keys[0][1];
  }
  const k = keys.findIndex(([at]) => at > t);
  if (k === -1) {
    return keys[keys.length - 1][1];
  }
  return mix(keys[k - 1][1], keys[k][1], smooth(keys[k - 1][0], keys[k][0], t));
}

const hash = (n: number) => ((n * 2654435761) % 1000) / 1000;

/** The pose of a player with no touch going on: set or relaxed, running as fast as they go. */
export function restPose(person: number, time: number, speed: number, ready: number): Pose {
  const run = smooth(WALK, SPRINT, speed);
  const swing = Math.sin(2 * Math.PI * (CADENCE_HZ * time + hash(person)));
  const arm = (sign: number): Arm => ({ pitch: mix(0, READY.pitch, ready) + mix(0, 0.6 + sign * ARM_SWING * swing, run), roll: 0, stretch: 1 });
  return { jump: 0, crouch: Math.max(READY.crouch * ready, 0.1 * run), lean: 0.25 * run, stride: STRIDE * run * swing, shift: { x: 0, y: 0 }, arms: [arm(1), arm(-1)] };
}

/** The action's pose `t` after its contact, `up` the arm's angle to the ball at the contact, `long` its stretch to it. */
function gesture(type: Contact['type'], t: number, jump: number, up: number, long: number, high: boolean): Pick<Pose, 'crouch' | 'lean' | 'arms'> {
  const both = (pitch: number, roll: number, stretch: number): [Arm, Arm] => [
    { pitch, roll, stretch },
    { pitch, roll, stretch },
  ];
  // A free ball over the head is played as a set, under it as a pass.
  const kind = type === 'relance' ? (high ? 'set' : 'pass') : type;
  if (kind === 'attack') {
    return {
      crouch: keyed(
        [
          [-0.9, 0],
          [-0.45, 0.6],
          [-0.3, 0.1],
          [0.35, 0],
          [0.5, 0.35],
          [0.8, 0],
        ],
        t,
      ),
      lean: keyed(
        [
          [-0.9, 0],
          [-0.45, 0.35],
          [0, 0.1],
          [0.25, 0.35],
          [0.6, 0],
        ],
        t,
      ),
      arms: [
        {
          pitch: keyed(
            [
              [-0.9, 0.2],
              [-0.45, -0.7],
              [-0.25, 2.4],
              [-0.06, 2.8],
              [0, Math.max(up, 2.2)],
              [0.15, 1.6],
              [0.45, 0.3],
            ],
            t,
          ),
          roll: 0,
          stretch: keyed(
            [
              [-0.06, 1],
              [0, long],
              [0.15, 1],
            ],
            t,
          ),
        },
        {
          pitch: keyed(
            [
              [-0.9, 0.2],
              [-0.45, -0.7],
              [-0.2, 2.6],
              [0, 2],
              [0.3, 0.4],
            ],
            t,
          ),
          roll: 0,
          stretch: 1,
        },
      ],
    };
  }
  if (kind === 'block') {
    const pitch = keyed(
      [
        [-0.6, 0.6],
        [-0.25, 2.9],
        [0.25, 2.9],
        [0.6, 0.4],
      ],
      t,
    );
    return {
      crouch: keyed(
        [
          [-0.6, 0],
          [-0.4, 0.5],
          [-0.25, 0],
          [0.35, 0],
          [0.5, 0.3],
          [0.7, 0],
        ],
        t,
      ),
      lean: 0.08,
      arms: both(
        pitch,
        -0.12,
        keyed(
          [
            [-0.25, 1],
            [0, Math.max(long, 1.4)],
            [0.25, 1],
          ],
          t,
        ),
      ),
    };
  }
  if (kind === 'set') {
    const pitch = keyed(
      [
        [-0.6, 0.6],
        [-0.3, 2.45],
        [-0.03, 2.55],
        [0, Math.max(up, 2.2)],
        [0.22, 2.85],
        [0.5, 0.45],
      ],
      t,
    );
    return {
      crouch: keyed(
        [
          [-0.5, 0.25],
          [-0.08, 0.25],
          [0.02, 0.05],
          [0.3, 0],
        ],
        t,
      ),
      lean: 0,
      arms: both(
        pitch,
        -0.12,
        keyed(
          [
            [-0.05, 1],
            [0, Math.min(long, 1.25)],
            [0.2, 1],
          ],
          t,
        ),
      ),
    };
  }
  if (kind === 'serve') {
    return {
      crouch: keyed(
        [
          [-1, 0],
          [-0.4, 0.3],
          [-jump * 0.4 - 0.1, 0],
        ],
        t,
      ),
      lean: keyed(
        [
          [-0.6, -0.1],
          [0, 0.2],
          [0.4, 0.15],
        ],
        t,
      ),
      arms: [
        {
          pitch: keyed(
            [
              [-1, 0.3],
              [-0.45, 0.6],
              [-0.2, 2.6],
              [0, 2.9],
              [0.2, 1.4],
              [0.55, 0.4],
            ],
            t,
          ),
          roll: 0,
          stretch: keyed(
            [
              [-0.1, 1],
              [0, 1.4],
              [0.15, 1],
            ],
            t,
          ),
        },
        {
          pitch: keyed(
            [
              [-1, 0.9],
              [-0.55, 2.6],
              [-0.2, 2.4],
              [0, 1],
              [0.3, 0.3],
            ],
            t,
          ),
          roll: 0,
          stretch: 1,
        },
      ],
    };
  }
  // A reception or a dig: low, forearms together towards the ball.
  const low = kind === 'dig';
  const crouch = low ? 0.85 : 0.55;
  return {
    crouch: keyed(
      [
        [-0.5, crouch],
        [0, crouch],
        [0.3, crouch * 0.4],
      ],
      t,
    ),
    lean: low ? 0.55 : 0.3,
    arms: both(
      keyed(
        [
          [-0.45, 0.95],
          [0, Math.min(1.35, Math.max(0.7, up))],
          [0.3, 0.7],
        ],
        t,
      ),
      0.35,
      1,
    ),
  };
}

/** The body playing a touch: its named player if near it, else the nearest of its team. */
export function bodyOf(c: Contact, place: Point3 | null, dots: Dot[], people: Record<string, Person>): Dot | undefined {
  const key = playerKey(c.person, people);
  const distance = (d: Dot) => (place ? Math.hypot(d.x - place.x, d.y - place.y) : 0);
  const named = key === null ? undefined : dots.find((d) => playerKey(d.person, people) === key);
  if (named && distance(named) <= SAME_M) {
    return named;
  }
  const team = dots.filter((d) => people[d.person]?.team === c.g).sort((a, b) => distance(a) - distance(b));
  return place && team[0] && distance(team[0]) <= NEAREST_M ? team[0] : named;
}

/** The pose of each of `dots` at `time`, a rally shown or none: its touch going on, else its rest. `before` and `after` are
 * the players' places SPEED_S either side, for their speed. */
export function posesAt(rally: Rally | undefined, time: number, dots: Dot[], before: Dot[], after: Dot[], places: Places, people: Record<string, Person>): Map<number, Pose> {
  const ready = rally ? smooth(rally.start - READY_S, rally.start, time) * (1 - smooth(rally.end, rally.end + READY_S, time)) : 0;
  const out = new Map<number, Pose>();
  for (const d of dots) {
    const [a, b] = [before.find((o) => o.person === d.person) ?? d, after.find((o) => o.person === d.person) ?? d];
    out.set(d.person, restPose(d.person, time, Math.hypot(b.x - a.x, b.y - a.y) / (2 * SPEED_S), ready));
  }
  // The touch nearest in time takes a body, so a later one does not cut one short.
  const going = (rally?.contacts ?? [])
    .filter((c) => {
      const window = isTouch(c) ? WINDOWS[c.type] : undefined;
      return window && time - c.t >= window[0] && time - c.t <= window[1];
    })
    .sort((p, q) => Math.abs(time - q.t) - Math.abs(time - p.t));
  for (const c of going) {
    const place = places?.get(c.i) ?? (c.x !== null && c.y !== null ? { x: c.x, y: c.y, h: 1.5 } : null);
    const body = bodyOf(c, place, dots, people);
    const rest = body && out.get(body.person);
    if (!body || !rest) {
      continue;
    }
    const window = WINDOWS[c.type] as [number, number];
    const t = time - c.t;
    const away = place ? Math.hypot(place.x - body.x, place.y - body.y) : Infinity;
    const aimed = away <= AIM_M && c.type !== 'serve';
    const moved = aimed ? Math.max(0, Math.min(REACH_M, away - ARM_ROOM_M)) : 0;
    const height = place?.h ?? 1.5;
    const shape = JUMPS[c.type];
    const peak = shape ? Math.max(0, Math.min(shape.most, height - TOP_M)) : 0;
    const left = aimed ? away - moved : 0.3;
    const rise = height - SHOULDER_M - peak;
    const up = Math.PI / 2 + Math.atan2(rise, left);
    const long = Math.max(1, Math.min(STRETCH, Math.hypot(rise, left) / ARM_M));
    const ease = smooth(window[0], window[0] + EASE_S, t) * (1 - smooth(window[1] - EASE_S, window[1], t));
    const pose = gesture(c.type, t, peak, up, long, height > SHOULDER_M + ARM_M);
    const lunge = moved * smooth(-0.35, -0.05, t) * (1 - smooth(0.1, 0.5, t));
    const toward = aimed && away > 0 ? { x: (((place as Point3).x - body.x) / away) * lunge, y: (((place as Point3).y - body.y) / away) * lunge } : { x: 0, y: 0 };
    out.set(body.person, {
      jump: shape && Math.abs(t) < shape.half ? peak * (1 - (t / shape.half) ** 2) : 0,
      crouch: mix(rest.crouch, pose.crouch, ease),
      lean: mix(rest.lean, pose.lean, ease),
      stride: rest.stride * (1 - ease),
      shift: toward,
      arms: [0, 1].map((k) => ({
        pitch: mix(rest.arms[k].pitch, pose.arms[k].pitch, ease),
        roll: mix(rest.arms[k].roll, pose.arms[k].roll, ease),
        stretch: mix(rest.arms[k].stretch, pose.arms[k].stretch, ease),
      })) as [Arm, Arm],
    });
  }
  return out;
}

/** The ball before the serve: in the hand of the server `at`, then tossed up and on to where the serve is hit from; `flown`
 * after it. Rallies not starting on a serve, or with no server seen, keep `flown`. */
export function ballBeforeServe(rally: Rally, time: number, at: Dot | undefined, places: Places, flown: Point3 | null): Point3 | null {
  const first = rally.contacts.find(isTouch);
  if (first?.type !== 'serve' || time >= first.t || !at) {
    return flown;
  }
  const hit = ball3dAt(rally.contacts, first.t, places);
  if (!hit) {
    return flown;
  }
  const hand = { x: at.x - Math.sign(at.x) * 0.3, y: at.y, h: HAND_M };
  const u = smooth(first.t - TOSS_S, first.t, time);
  return { x: mix(hand.x, hit.x, u), y: mix(hand.y, hit.y, u), h: mix(HAND_M, hit.h, u) + TOSS_M * Math.sin(Math.PI * u) };
}
