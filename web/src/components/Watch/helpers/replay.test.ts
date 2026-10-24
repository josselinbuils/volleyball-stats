import { describe, expect, it } from 'vitest';
import type { Contact } from '@/lib/match';
import { ballAt, playersAt } from '@/components/Watch/helpers/replay';

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
  const players = { step: 3, spans: [{ from: 10, samples: [[[1, 2], []], [[3, 4], [5, 6]]] }] };

  it('takes the nearest sample of the span holding the time', () => {
    // Sample 11 is frame 33, 1.1 s at 30 fps.
    expect(playersAt(players, 30, 1.12)).toEqual([[3, 4], [5, 6]]);
    expect(playersAt(players, 30, 1.0)).toEqual([[1, 2], []]);
  });

  it('has no players outside the spans', () => {
    expect(playersAt(players, 30, 0.5)).toEqual([[], []]);
    expect(playersAt(players, 30, 1.3)).toEqual([[], []]);
  });
});
