import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { ballAt, playersAt, sidesAt } from '@/components/Watch/helpers/replay';

describe('ballAt', () => {
  const touch = (t: number, x: number | null, y: number | null) => ({ t, x, y }) as Contact;
  const rally = [touch(1, -8, 0), touch(2, null, null), touch(3, 4, 2)];

  it('moves straight between two placed touches, skipping unplaced ones', () => {
    expect(ballAt(rally, 2)).toEqual({ x: -2, y: 1 });
  });

  it('waits at the first touch before it and stays at the last one after', () => {
    expect(ballAt(rally, 0)).toEqual({ x: -8, y: 0 });
    expect(ballAt(rally, 9)).toEqual({ x: 4, y: 2 });
  });

  it('has no ball without a placed touch', () => {
    expect(ballAt([touch(1, null, null)], 1)).toBeNull();
  });
});

describe('playersAt', () => {
  const players = { step: 3, samples: [[], [4, 1, 2], [4, 3, 4, 9, 5, 6]] };

  it('takes the nearest sample as player and court feet', () => {
    // Sample 2 is frame 6, 0.2 s at 30 fps.
    expect(playersAt(players, 30, 0.19)).toEqual([
      { person: 4, x: 3, y: 4 },
      { person: 9, x: 5, y: 6 },
    ]);
    expect(playersAt(players, 30, 0.1)).toEqual([{ person: 4, x: 1, y: 2 }]);
  });

  it('has no players past the samples', () => {
    expect(playersAt(players, 30, 0)).toEqual([]);
    expect(playersAt(players, 30, 5)).toEqual([]);
  });
});

describe('sidesAt', () => {
  const rallies = [{ start: 10 }, { start: 30 }];

  it('takes the rally being played, else the last one before, else the first', () => {
    expect(sidesAt(rallies, 29.5)).toBe(rallies[1]);
    expect(sidesAt(rallies, 20)).toBe(rallies[0]);
    expect(sidesAt(rallies, 2)).toBe(rallies[0]);
    expect(sidesAt([], 2)).toBeUndefined();
  });
});
