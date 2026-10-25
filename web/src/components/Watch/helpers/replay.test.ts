import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { ballAt, landingsAt, playersAt, sidesAt, touchesAt, trailAt } from '@/components/Watch/helpers/replay';

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

describe('trailAt', () => {
  const touch = (t: number, x: number, y: number) => ({ t, x, y }) as Contact;

  it('follows the ball back in time, longer for a faster ball', () => {
    expect(trailAt([touch(0, 0, 0), touch(1, 10, 0)], 0.5, 0.2, 3)).toEqual([
      { x: 3, y: 0 },
      { x: 4, y: 0 },
      { x: 5, y: 0 },
    ]);
    expect(trailAt([touch(0, 0, 0), touch(2, 10, 0)], 1, 0.2, 2)).toEqual([
      { x: 4, y: 0 },
      { x: 5, y: 0 },
    ]);
  });

  it('stands still where the ball waits', () => {
    expect(new Set(trailAt([touch(5, 1, 2), touch(6, 3, 2)], 1).map((p) => `${p.x},${p.y}`))).toEqual(new Set(['1,2']));
  });
});

describe('touchesAt', () => {
  const touch = (t: number, person: number | null) => ({ t, person }) as Contact;

  it('keeps the touches of a known player from just before them to half a second after', () => {
    const found = touchesAt([touch(1, 3), touch(1.2, null), touch(2, 5)], 1.25);
    expect(found.map(({ touch: c, f }) => [c.person, Math.round(f * 100) / 100])).toEqual([[3, 0.5]]);
    expect(touchesAt([touch(1, 3)], 0.85)).toEqual([]);
  });
});

describe('landingsAt', () => {
  const touch = (i: number, t: number, type: string, x: number | null) => ({ i, t, type, x, y: x === null ? null : 1 }) as Contact;

  it('ripples from a placed floor touch for under a second after it', () => {
    const rally = [touch(0, 1, 'serve', -8), touch(1, 2, 'floor', 5), touch(2, 2.1, 'floor', null)];
    expect(landingsAt(rally, 2.45).map(({ f, ...at }) => ({ ...at, f: Math.round(f * 100) / 100 }))).toEqual([{ x: 5, y: 1, f: 0.5, i: 1 }]);
    expect(landingsAt(rally, 1.9)).toEqual([]);
    expect(landingsAt(rally, 3)).toEqual([]);
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

describe('sidesAt', () => {
  const rallies = [{ start: 10 }, { start: 30 }];

  it('takes the rally being played, else the last one before, else the first', () => {
    expect(sidesAt(rallies, 29.5)).toBe(rallies[1]);
    expect(sidesAt(rallies, 20)).toBe(rallies[0]);
    expect(sidesAt(rallies, 2)).toBe(rallies[0]);
    expect(sidesAt([], 2)).toBeUndefined();
  });
});
