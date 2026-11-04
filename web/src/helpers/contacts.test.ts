import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { isTouch, labelled } from '@/helpers/contacts';

describe('isTouch', () => {
  it("counts the players' touches, not the ball hitting the floor or the net", () => {
    const types = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'floor', 'net'];
    expect(types.filter((type) => isTouch({ type } as Contact))).toEqual(['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig']);
  });
});

describe('labelled', () => {
  it('gives what happened where the statistics read it otherwise', () => {
    expect(labelled({ result: 'point', label: 'play' } as Contact)).toBe('play');
    expect(labelled({ result: 'error' } as Contact)).toBe('error');
  });
});
