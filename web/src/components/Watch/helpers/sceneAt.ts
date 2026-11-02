import { match, playerMark, type Contact, type Rally } from '@/lib/match';
import type { SceneState } from '@/scene3d/scene';
import { ball3dAt, trail3dAt, type Places } from '@/components/Watch/helpers/flight';
import { ballBeforeServe, type Dot, type Pose } from '@/components/Watch/helpers/pose';
import { hasTapedFeet } from '@/components/Watch/helpers/replay';

/** What the 3D scene shows at `moment` of `rally`, `dots` the players then, `server` who holds the ball before the serve. */
export function sceneAt({
  dots,
  poses,
  rally,
  moment,
  touches,
  landings,
  server,
  places,
  board,
  camera,
  hidden,
  tipOf,
}: {
  dots: Dot[];
  poses: Map<number, Pose> | null;
  rally: Rally | undefined;
  moment: number;
  touches: { touch: Contact; f: number }[];
  landings: SceneState['landings'];
  server: Dot | undefined;
  places: Places;
  board: SceneState['board'];
  camera: SceneState['camera'];
  hidden: number | null;
  tipOf: (person: number) => string | undefined;
}): Omit<SceneState, 'colors'> {
  return {
    players: dots.map(({ person, x, y }) => {
      const pose = poses?.get(person);
      return {
        key: person,
        x: x + (pose?.shift.x ?? 0),
        y: y + (pose?.shift.y ?? 0),
        jump: pose?.jump ?? 0,
        pose,
        team: match.people[person]?.team ?? 1,
        label: playerMark(person) ?? '',
        tip: tipOf(person),
        taped: hasTapedFeet(match.people[person]?.name),
      };
    }),
    ball: rally ? ballBeforeServe(rally, moment, server, places, ball3dAt(rally.contacts, moment, places)) : null,
    trail: rally ? trail3dAt(rally.contacts, moment, places) : [],
    rings: touches.flatMap(({ touch, f }) => {
      const at = dots.find((d) => d.person === touch.person) ?? (touch.x !== null && touch.y !== null ? { x: touch.x, y: touch.y } : null);
      return at ? [{ x: at.x, y: at.y, f }] : [];
    }),
    landings,
    board,
    camera,
    hidden,
  };
}
