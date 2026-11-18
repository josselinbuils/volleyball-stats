import type { Contact } from '@/lib/match';

const TOUCHES = new Set(['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig']);

/** Whether a player touched the ball: floor and net contacts are the ball's, not a player's. */
export const isTouch = (c: Contact) => TOUCHES.has(c.type);

/** What the review adds without a touch of the ball, a fault of its player each (`web.NO_BALL`): a playing fault and a
 * ball let fall. */
export const NO_BALL: readonly string[] = ['fault', 'missed'];
export const noBall = (c: { type: string }) => NO_BALL.includes(c.type);

/** What a touch holds for the review, before the statistics' reading. */
export const labelled = (c: Contact) => c.label ?? c.result;
