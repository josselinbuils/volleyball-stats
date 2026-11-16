import { describe, expect, it } from 'vitest';
import type { Contact, Group, Rally } from '@/lib/match';
import { callAt, type LineCall } from '@/components/Watch/helpers/lineCall';

const touch = (t: number, type: string, x: number, y: number, g: Group) => ({ t, type, x, y, g }) as Contact;
const rally = (i: number, winner: Group | null, contacts: Contact[], more: Partial<Rally> = {}) =>
  ({ i, start: contacts[0]?.t ?? 0, end: (contacts.at(-1)?.t ?? 0) + 1, winner, contacts, ...more }) as Rally;

describe('callAt', () => {
  const rallies = [rally(0, 1, [touch(10, 'attack', -2, 0, 1), touch(10.5, 'floor', 8.8, 1, 2)]), rally(1, 1, [touch(13, 'serve', -9, 0, 1)])];
  const calls: LineCall[] = [{ rally: 0, t: 10.5, in: true, wrongCall: false, mark: { x: 8.8, y: 1, line: 'end' } }];

  it('holds the call from just after the bounce, until the next rally starts', () => {
    expect([10.5, 10.8, 12, 12.5].map((t) => callAt(calls, rallies, t, 0.2, 2.5)?.rally ?? null)).toEqual([null, 0, 0, 0]);
    expect(callAt(calls, rallies, 13.1, 0.2, 2.5)).toBeNull();
  });
});
