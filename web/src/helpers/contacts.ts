import type { Contact } from '@/lib/match';

const TOUCHES = new Set(['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig']);

/** Whether a player touched the ball: floor and net contacts are the ball's, not a player's. */
export const isTouch = (c: Contact) => TOUCHES.has(c.type);
