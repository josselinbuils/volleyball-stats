import { describe, expect, it } from 'vitest';
import type { Contact, Group, Rally } from '@/lib/match';
import { commentary, lineAt, type Names } from '@/components/Watch/helpers/commentary';

describe('commentary', () => {
  const names: Names = { player: (p) => (p === null ? null : ({ 1: 'Anthony', 2: 'Manon', 3: 'Sam' } as Record<number, string>)[p]), team: (g: Group) => `T${g}` };

  function touch(t: number, type: Contact['type'], g: Group, person: number | null = 1, result: Contact['result'] = 'play'): Contact {
    return { i: t, t, type, g, team: g, side: g === 1 ? 'left' : 'right', rally: 0, set: 1, x: 0, y: 0, zone: null, result, person, player: null, name: null };
  }

  function rally(i: number, contacts: Contact[], winner: Group | null, score: [number, number] = [1, 0], extra: Partial<Rally> = {}): Rally {
    return { i, start: i * 30, end: i * 30 + 5, set: 1, left: 1, flipped: false, winner, score, contacts, ...extra };
  }

  // The set goes on after the rallies given, unless they say otherwise.
  const lines = (rallies: Rally[], i = 0, sets = 3) => commentary([...rallies, rally(99, [], null, [0, 0])], names, sets).get(i) ?? [];
  const last = (rallies: Rally[], i = 0) => lines(rallies, i).at(-1);

  it('tells each touch by name, in time', () => {
    const found = lines([rally(0, [touch(0, 'serve', 2, 3), touch(1, 'pass', 1, 2), touch(2, 'set', 1, 1), touch(3, 'attack', 1, 2, 'point')], 1)]);
    expect(found.map((l) => l.key.split('_')[0])).toEqual(['serve', 'pass', 'set', 'attackPoint']);
    expect(found[0].vars).toMatchObject({ name: 'Sam', ofName: 'de Sam' });
    expect(found.map((l) => l.t)).toEqual([...found.map((l) => l.t)].sort((a, b) => a - b));
  });

  it('names who scored', () => {
    expect(last([rally(0, [touch(0, 'serve', 1, 2, 'point')], 1)])).toMatchObject({ key: 'servePoint', vars: { name: 'Manon', team: 'T1', score: '1-0' } });
  });

  it('gives the score with the winner first', () => {
    expect(last([rally(0, [touch(0, 'serve', 2, 3, 'point')], 2, [1, 4])])?.vars.score).toBe('4-1');
  });

  it('names who gave the point away', () => {
    const fault = last([rally(0, [touch(0, 'serve', 2, 3), touch(1, 'attack', 1, 2, 'error')], 2, [0, 1])]);
    expect(fault?.key).toBe('attackFaultNamed');
    expect(fault?.vars).toMatchObject({ name: 'Manon', ofName: 'de Manon', team: 'T2', other: 'T1' });
  });

  it('says the team when no one is named on the fault', () => {
    expect(last([rally(0, [touch(1, 'attack', 1, null, 'error')], 2, [0, 1])])?.key).toBe('attackFault');
  });

  it('tells a touch losing the rally after a point once, on the point', () => {
    const found = lines([rally(0, [touch(0, 'attack', 2, 3, 'point'), touch(1, 'dig', 1, 2, 'error')], 2, [0, 1])]);
    expect(found.map((l) => l.key)).toEqual(['attackPoint']);
  });

  it('stays silent on a touch of no one named, and says the team on its point', () => {
    expect(lines([rally(0, [touch(0, 'set', 1, null), touch(1, 'attack', 1, null, 'point')], 1)]).map((l) => l.key)).toEqual(['attackPointTeam']);
  });

  it('marks the end of a set', () => {
    const rallies = [rally(0, [touch(0, 'serve', 1, 2, 'point')], 1, [25, 20]), rally(1, [touch(30, 'serve', 2, 3)], 2, [0, 1], { set: 2 })];
    expect(last(rallies)?.key).toBe('servePointSet');
  });

  it('calls a set point and a late tie before the serve', () => {
    const serve = (t: number) => [touch(t, 'serve', 1, 2)];
    const before = (a: number, b: number) => [rally(0, serve(0), 1, [a, b]), rally(1, serve(30), 1, [a + 1, b])];
    expect(lines(before(24, 22), 1)[0]).toMatchObject({ key: 'setPoint', vars: { team: 'T1' } });
    expect(lines(before(22, 24), 1)[0]).toMatchObject({ key: 'setPoint', vars: { team: 'T2' } });
    expect(lines(before(20, 20), 1)[0]).toMatchObject({ key: 'tie', vars: { n: 20 } });
    expect(lines(before(10, 10), 1)[0].key).not.toBe('tie');
  });

  it('notices a long rally', () => {
    const contacts = Array.from({ length: 9 }, (_, k) => touch(k, 'dig', 1, 2));
    expect(lines([rally(0, contacts, 1)]).map((l) => l.key)).toContain('longRally');
  });

  it('says a rally to replay', () => {
    expect(last([rally(0, [touch(0, 'serve', 1, 2)], null, [0, 0], { redo: true })])?.key).toBe('redo');
  });

  describe('lineAt', () => {
    const found = [
      { t: 1, key: 'a', vars: {}, strong: false },
      { t: 3, key: 'b', vars: {}, strong: false },
    ];

    it('holds the last line for a few seconds', () => {
      expect(lineAt(found, 0.5)).toBeNull();
      expect(lineAt(found, 2)?.key).toBe('a');
      expect(lineAt(found, 4)?.key).toBe('b');
      expect(lineAt(found, 8.1)).toBeNull();
      expect(lineAt(undefined, 1)).toBeNull();
    });
  });
});
