import { describe, expect, it } from 'vitest';
import type { Contact, ZoneCell } from '@/lib/match';
import { cellContacts } from '@/components/CourtChart/helpers/zones';

describe('cellContacts', () => {
  const cells: ZoneCell[] = [
    { zone: 1, x: -9, y: 1.5, w: 6, h: 3 },
    { zone: 1, x: 3, y: -4.5, w: 6, h: 3 },
    { zone: 4, x: -3, y: -4.5, w: 3, h: 3 },
  ];
  const touch = (zone: number | null, x: number | null) => ({ zone, x }) as Contact;

  it('counts each touch in the cell of its zone on its own half', () => {
    const left1 = touch(1, -6);
    const right1 = touch(1, 7);
    const left4 = touch(4, -1);
    expect(cellContacts([left1, right1, left4, touch(1, -10.5)], cells)).toEqual([[left1, touch(1, -10.5)], [right1], [left4]]);
  });

  it('leaves out the touches without a position', () => {
    expect(cellContacts([touch(null, null)], cells)).toEqual([[], [], []]);
  });
});
