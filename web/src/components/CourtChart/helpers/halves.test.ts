import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import { onOwnHalf } from '@/components/CourtChart/helpers/halves';

describe('onOwnHalf', () => {
  const rallies = [{ flipped: false }, { flipped: true }] as Rally[];
  const touch = (rally: number, x: number | null, y: number | null) => ({ rally, x, y, zone: 1 }) as Contact;

  it('turns the touches of rallies played on the other ends half a turn, keeping the others', () => {
    const kept = touch(0, -6, 3);
    expect(onOwnHalf([kept, touch(1, 6, -3), touch(1, null, null)], rallies)).toEqual([kept, touch(1, -6, 3), touch(1, null, null)]);
  });
});
