import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import { drops } from '@/components/Stats/helpers/between';

describe('drops', () => {
  const people: Record<string, Person> = {
    0: { team: 1, number: 1, jersey: null },
    1: { team: 1, number: 2, jersey: null },
    2: { team: 1, number: 3, jersey: null },
    3: { team: 2, number: 1, jersey: null },
  };
  const touch = (type: string, g: number, t: number, x: number | null, y: number | null, result = 'play') => ({ type, g, t, x, y, result, rally: 0 }) as Contact;
  // One sample every frame at 10 fps; the ball lands at 1 s, sample 10.
  const at = (flat: number[]) => ({ step: 1, samples: [...Array.from({ length: 10 }, () => []), flat] });
  const rally = [touch('attack', 2, 0.5, 3, 0, 'point'), touch('floor', 1, 1, -5, 0)];

  it('takes an untouched ball landing in about as near two teammates, both within reach', () => {
    expect(drops(rally, at([0, -5, 1, 1, -5, -1.5, 2, -8, 0]), 10, people)).toEqual([{ landing: rally[1], pair: [0, 1] }]);
  });

  it('leaves a ball one teammate was clearly the nearest to, or out of everyone’s reach', () => {
    expect(drops(rally, at([0, -5, 0.5, 1, -5, -1.5]), 10, people)).toEqual([]);
    expect(drops(rally, at([0, -5, 2.4, 1, -5, -2.8]), 10, people)).toEqual([]);
  });

  it('counts only the landing team’s players on its half', () => {
    expect(drops(rally, at([0, -5, 1, 3, -5, -1]), 10, people)).toEqual([]);
    expect(drops(rally, at([0, -5, 1, 1, 1, 0]), 10, people)).toEqual([]);
  });

  it('leaves a ball touched before it landed, or out', () => {
    const touched = [touch('attack', 2, 0.5, 3, 0, 'play'), touch('dig', 1, 0.8, -5, 1, 'error'), touch('floor', 1, 1, -5, 0)];
    expect(drops(touched, at([0, -5, 1, 1, -5, -1]), 10, people)).toEqual([]);
    const out = [touch('attack', 2, 0.5, 3, 0, 'error'), touch('floor', 1, 1, -10, 0)];
    expect(drops(out, at([0, -10, 1, 1, -10, -1]), 10, people)).toEqual([]);
  });
});
