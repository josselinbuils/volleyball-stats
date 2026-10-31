import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';

describe('isTouch', () => {
  it("counts the players' touches, not the ball hitting the floor or the net", () => {
    const types = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'floor', 'net'];
    expect(types.filter((type) => isTouch({ type } as Contact))).toEqual(['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig']);
  });
});
