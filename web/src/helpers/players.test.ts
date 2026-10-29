import { describe, expect, it } from 'vitest';
import { playersAt } from '@/helpers/players';

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

  it('keeps a player missing from the last samples at their last place for half a second', () => {
    // At 30 fps every 3 frames, half a second is 5 samples.
    const gappy = { step: 3, samples: [[4, 1, 2], [], [9, 5, 6], [9, 5, 6], [9, 5, 6], [9, 5, 6], [9, 5, 6]] };
    expect(playersAt(gappy, 30, 0.2)).toEqual([
      { person: 9, x: 5, y: 6 },
      { person: 4, x: 1, y: 2 },
    ]);
    expect(playersAt(gappy, 30, 0.6)).toEqual([{ person: 9, x: 5, y: 6 }]);
  });

  it('has no players past the samples', () => {
    expect(playersAt(players, 30, 0)).toEqual([]);
    expect(playersAt(players, 30, 5)).toEqual([]);
  });
});
