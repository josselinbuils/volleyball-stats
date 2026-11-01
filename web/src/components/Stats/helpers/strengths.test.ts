import { describe, expect, it } from 'vitest';
import type { Contact, Group, Person, Rally } from '@/lib/match';
import { lines } from '@/components/Stats/helpers/stats';
import { strengths } from '@/components/Stats/helpers/strengths';

describe('strengths', () => {
  const people: Record<string, Person> = {
    1: { team: 1, number: 1, jersey: null, name: 'Alex' },
    2: { team: 1, number: 2, jersey: null, name: 'Sam' },
    3: { team: 1, number: 3, jersey: null, name: 'Kim' },
    9: { team: 2, number: 9, jersey: null, name: 'Noa' },
  };

  function touch(rally: number, type: Contact['type'], person: number, result: Contact['result'] = 'play'): Contact {
    const g = people[person].team;
    return { i: 0, t: rally, type, g, team: g, side: 'left', rally, set: 1, x: 0, y: 0, zone: null, result, person, player: null, name: null };
  }

  const rallyOf = (i: number, contacts: Contact[], winner: Group = 1, score: [number, number] = [1, 0]): Rally => ({
    i,
    start: i,
    end: i + 1,
    set: 1,
    left: 1,
    flipped: false,
    winner,
    score,
    contacts,
  });

  /** The strengths of player 1 from `contacts`, each their own rally unless a rally is given. */
  function of(contacts: Contact[], seconds: Record<number, number> = {}, rallies?: Rally[]) {
    const found = lines(contacts, people, 1);
    const all =
      rallies ??
      [...new Set(contacts.map((c) => c.rally))].map((r) =>
        rallyOf(
          r,
          contacts.filter((c) => c.rally === r),
        ),
      );
    return strengths(found, (p) => seconds[p] ?? 0, contacts, all, people);
  }

  const times = (n: number, make: (k: number) => Contact, from = 0) => Array.from({ length: n }, (_, k) => make(from + k));
  const keys = (found: ReturnType<typeof of>, person = 1) => (found.get(person) ?? []).map((i) => i.key);

  it('sees who is on every ball for the time they played, not who played longest', () => {
    const contacts = [...times(30, (k) => touch(k, 'dig', 1)), ...times(30, (k) => touch(k, 'dig', 2), 100)];
    expect(keys(of(contacts, { 1: 300, 2: 600 }))).toContain('allBalls');
    expect(keys(of(contacts, { 1: 300, 2: 600 }), 2)).not.toContain('allBalls');
    expect(
      of(contacts, { 1: 300, 2: 600 })
        .get(1)
        ?.find((i) => i.key === 'allBalls')?.perMinute,
    ).toEqual([6, 3]);
  });

  it('says nothing on presence without playing times', () => {
    const contacts = [...times(30, (k) => touch(k, 'dig', 1)), ...times(5, (k) => touch(k, 'dig', 2), 100)];
    expect(keys(of(contacts))).not.toContain('allBalls');
  });

  it('calls a serve reliable against the rest of the team, from 5 tries each', () => {
    const contacts = [...times(6, (k) => touch(k, 'serve', 1)), ...times(4, (k) => touch(k, 'serve', 2), 100), ...times(2, (k) => touch(k, 'serve', 2, 'error'), 200)];
    expect(
      of(contacts)
        .get(1)
        ?.find((i) => i.key === 'safeServes'),
    ).toMatchObject({ n: 6, of: 6, restN: 4, restOf: 6 });
    expect(keys(of(contacts.slice(2)))).not.toContain('safeServes');
  });

  it('rewards sets followed by an attack against the rest of the team, not many sets', () => {
    const set = (r: number, setter: number, attacked: boolean) => [touch(r, 'set', setter), ...(attacked ? [touch(r, 'attack', 3)] : [])];
    const contacts = [...times(5, (k) => set(k, 1, true)).flat(), ...times(5, (k) => set(k + 100, 2, k < 2)).flat()];
    expect(
      of(contacts)
        .get(1)
        ?.find((i) => i.key === 'usedSets'),
    ).toMatchObject({ n: 5, of: 5, restN: 2, restOf: 5 });
    expect(keys(of(contacts), 2)).not.toContain('usedSets');
    const never = times(30, (k) => set(k, 1, false)).flat();
    expect(keys(of([...never, ...times(5, (k) => set(k + 100, 2, true)).flat()], { 1: 600, 2: 600 }))).not.toContain('usedSets');
  });

  it('counts the attacks won right after their sets, without their own', () => {
    const pair = (r: number, setter: number, attacker: number) => [touch(r, 'set', setter), touch(r, 'attack', attacker, 'point')];
    const contacts = [...pair(0, 1, 2), ...pair(1, 1, 2), ...pair(2, 1, 3), ...pair(3, 1, 1)];
    expect(
      of(contacts)
        .get(1)
        ?.find((i) => i.key === 'assists'),
    ).toMatchObject({ n: 3 });
    expect(keys(of(contacts.slice(2)))).not.toContain('assists');
  });

  it('counts points when the score is high and close, from the score before the rally', () => {
    const point = (r: number) => touch(r, 'attack', 1, 'point');
    const rallies = [rallyOf(0, [point(0)], 1, [20, 19]), rallyOf(1, [point(1)], 1, [21, 19]), rallyOf(2, [point(2)], 1, [22, 19])];
    expect(
      of(
        rallies.flatMap((r) => r.contacts),
        {},
        rallies,
      )
        .get(1)
        ?.find((i) => i.key === 'clutch'),
    ).toMatchObject({ n: 2 });
  });

  it('gives the most points to the top of the team, a tie to both', () => {
    const contacts = [...times(5, (k) => touch(k, 'attack', 1, 'point')), ...times(5, (k) => touch(k, 'attack', 2, 'point'), 100), ...times(4, (k) => touch(k, 'attack', 3, 'point'), 200)];
    expect(keys(of(contacts))).toContain('topScorer');
    expect(keys(of(contacts), 2)).toContain('topScorer');
    expect(keys(of(contacts), 3)).not.toContain('topScorer');
  });

  it('calls a player all-round from 5 kinds of touch, 3 times each', () => {
    const kinds: Contact['type'][] = ['pass', 'set', 'attack', 'dig', 'relance'];
    const contacts = kinds.flatMap((type, n) => times(3, (k) => touch(k + 10 * n, type, 1)));
    expect(
      of(contacts)
        .get(1)
        ?.find((i) => i.key === 'versatile'),
    ).toMatchObject({ n: 5 });
    expect(keys(of(contacts.slice(1)))).not.toContain('versatile');
  });

  it('shows the rarest in the team first, 3 at most', () => {
    const contacts = [
      ...times(6, (k) => touch(k, 'attack', 1, 'point')),
      ...times(2, (k) => touch(k, 'block', 1, 'point'), 50),
      ...times(3, (k) => touch(k, 'block', 2, 'point'), 60),
      ...times(5, (k) => touch(k, 'serve', 1), 70),
      ...times(5, (k) => touch(k, 'serve', 2, 'error'), 80),
    ];
    const found = keys(of(contacts));
    expect(found.indexOf('topScorer')).toBeLessThan(found.indexOf('blockPoints'));
    expect(found.length).toBeLessThanOrEqual(3);
  });

  it('gives no one a strength for nothing', () => {
    expect(keys(of(times(2, (k) => touch(k, 'serve', 1))))).toEqual([]);
  });
});
