import { describe, expect, it } from 'vitest';
import { playerKey, playersAt } from '@/helpers/players';

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

describe('playerKey', () => {
  const people = {
    1: { team: 1 as const, number: 1, jersey: 9, name: 'Lou' },
    2: { team: 1 as const, number: 2, jersey: null, name: 'Lou' },
    3: { team: 1 as const, number: 3, jersey: 11 },
    4: { team: 1 as const, number: 4, jersey: 11 },
    5: { team: 1 as const, number: 11, jersey: null },
    6: { team: 2 as const, number: 1, jersey: 11 },
    7: { team: 1 as const, number: null, jersey: null },
  };

  it('gives one key to the identities of a team sharing a name or a jersey number', () => {
    expect(playerKey(1, people)).toBe(playerKey(2, people));
    expect(playerKey(3, people)).toBe(playerKey(4, people));
  });

  it('never matches a jersey number with a number for the match or another team', () => {
    expect(playerKey(5, people)).not.toBe(playerKey(3, people));
    expect(playerKey(6, people)).not.toBe(playerKey(3, people));
  });

  it('has none for a track without identity', () => {
    expect([playerKey(7, people), playerKey(null, people), playerKey(99, people)]).toEqual([null, null, null]);
  });
});
