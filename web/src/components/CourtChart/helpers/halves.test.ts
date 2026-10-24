import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import { flips, onOwnHalf } from '@/components/CourtChart/helpers/halves';

describe('flips', () => {
  // Set 1, then set 2 on the other ends with the deciding set's swap at its third rally.
  const rallies = [
    { set: 1, left: 1 },
    { set: 1, left: 1 },
    { set: 2, left: 2 },
    { set: 2, left: 2 },
    { set: 2, left: 1 },
  ] as Rally[];

  it('flips the rallies played on the other ends than the match started on', () => {
    expect(flips(rallies, null)).toEqual([false, false, true, true, false]);
  });

  it('flips only the rallies after a swap within the picked set', () => {
    expect(flips(rallies, 1)).toEqual([false, false, true, true, false]);
    expect(flips(rallies, 2)).toEqual([true, true, false, false, true]);
  });
});

describe('onOwnHalf', () => {
  const touch = (rally: number, x: number | null, y: number | null) => ({ rally, x, y, zone: 1 }) as Contact;

  it('turns the touches of the flipped rallies half a turn, keeping the others', () => {
    const kept = touch(0, -6, 3);
    expect(onOwnHalf([kept, touch(1, 6, -3), touch(1, null, null)], [false, true])).toEqual([kept, touch(1, -6, 3), touch(1, null, null)]);
  });
});
