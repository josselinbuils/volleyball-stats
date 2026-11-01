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
  // The ball lands with the players at `around`.
  const landed = (around: number[], x = -5) => [touch('attack', 2, 0.5, 3, 0, 'point'), { ...touch('floor', 1, 1, x, 0), around }];

  it('takes an untouched ball landing in about as near two teammates, both within reach', () => {
    const rally = landed([0, -5, 1, 1, -5, -1.5, 2, -8, 0]);
    expect(drops(rally, people)).toEqual([{ landing: rally[1], pair: [0, 1] }]);
  });

  it('leaves a ball one teammate was clearly the nearest to, or out of everyone’s reach', () => {
    expect(drops(landed([0, -5, 0.5, 1, -5, -1.5]), people)).toEqual([]);
    expect(drops(landed([0, -5, 2.4, 1, -5, -2.8]), people)).toEqual([]);
  });

  it('counts only the landing team’s players on its half', () => {
    expect(drops(landed([0, -5, 1, 3, -5, -1]), people)).toEqual([]);
    expect(drops(landed([0, -5, 1, 1, 1, 0]), people)).toEqual([]);
  });

  it('leaves a ball touched before it landed, or out', () => {
    const around = [0, -5, 1, 1, -5, -1];
    const touched = [touch('attack', 2, 0.5, 3, 0, 'play'), touch('dig', 1, 0.8, -5, 1, 'error'), { ...touch('floor', 1, 1, -5, 0), around }];
    expect(drops(touched, people)).toEqual([]);
    const out = [touch('attack', 2, 0.5, 3, 0, 'error'), { ...touch('floor', 1, 1, -10, 0), around: [0, -10, 1, 1, -10, -1] }];
    expect(drops(out, people)).toEqual([]);
  });
});
