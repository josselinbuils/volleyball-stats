import { describe, expect, it } from 'vitest';
import type { Contact, Group, Rally } from '@/lib/match';
import { callAt, lineCalls, local, outside } from '@/components/Watch/helpers/lineCall';

const touch = (t: number, type: string, x: number, y: number, g: Group) => ({ t, type, x, y, g }) as Contact;
const rally = (i: number, winner: Group | null, contacts: Contact[], more: Partial<Rally> = {}) =>
  ({ i, start: contacts[0]?.t ?? 0, end: (contacts.at(-1)?.t ?? 0) + 1, winner, contacts, ...more }) as Rally;

describe('outside', () => {
  it('tells how far out, else in, and the line', () => {
    expect(outside(9.3, 1)).toEqual({ by: expect.closeTo(0.3, 5), line: 'end' });
    expect(outside(-2, -4.3)).toEqual({ by: expect.closeTo(-0.2, 5), line: 'side' });
    expect(outside(9.3, 4.9).line).toBe('side');
  });
});

describe('lineCalls', () => {
  // Team 1 attacks from the left (x < 0); the ball lands on the right, near its end line.
  const attack = (x: number, winner: Group, more: Partial<Rally> = {}) => rally(0, winner, [touch(10, 'attack', -2, 0, 1), touch(10.5, 'floor', x, 1, 2)], more);

  it('calls a close landing in or out as the point went, with its mark where the measure agrees', () => {
    expect(lineCalls([attack(8.8, 1)])).toEqual([{ rally: 0, t: 10.5, in: true, wrongCall: false, mark: { x: 8.8, y: 1, line: 'end' } }]);
    expect(lineCalls([attack(9.3, 2)])[0].in).toBe(false);
    // A ball touching the line is in.
    expect(lineCalls([attack(9.08, 1)])[0].in).toBe(true);
  });

  it('leaves out far landings, a measure saying otherwise, and a ball dropping on its own side', () => {
    expect(lineCalls([attack(5, 1)])).toEqual([]);
    expect(lineCalls([attack(9.3, 1)])).toEqual([]);
    expect(lineCalls([rally(0, 2, [touch(10, 'dig', 6, 0, 2), touch(10.5, 'floor', 9.2, 1, 2)])])).toEqual([]);
  });

  it('shows a wrong call whatever the distance, as the point really went', () => {
    const [call] = lineCalls([attack(9.92, 1, { wrongCall: true })]);
    expect([call.in, call.wrongCall, call.mark?.line]).toEqual([false, true, 'end']);
    expect(lineCalls([attack(7, 1, { wrongCall: true })])[0].mark).toBeNull();
  });
});

describe('callAt', () => {
  const rallies = [rally(0, 1, [touch(10, 'attack', -2, 0, 1), touch(10.5, 'floor', 8.8, 1, 2)]), rally(1, 1, [touch(13, 'serve', -9, 0, 1)])];
  const calls = lineCalls(rallies);

  it('holds the call from just after the bounce, until the next rally starts', () => {
    expect([10.5, 10.8, 12, 12.5].map((t) => callAt(calls, rallies, t, 0.2, 2.5)?.rally ?? null)).toEqual([null, 0, 0, 0]);
    expect(callAt(calls, rallies, 13.1, 0.2, 2.5)).toBeNull();
  });
});

describe('local', () => {
  it('turns the court so the mark is seen from outside its line', () => {
    expect(local({ x: 9.3, y: 2, line: 'end' })).toEqual({ u: 2, v: expect.closeTo(0.3, 5), corner: 4.5 });
    expect(local({ x: -9.3, y: 2, line: 'end' }).u).toBe(-2);
    expect(local({ x: 3, y: -4.2, line: 'side' })).toEqual({ u: 3, v: expect.closeTo(-0.3, 5), corner: 9 });
  });
});
