import { describe, expect, it } from 'vitest';
import type { Contact, Group, Rally } from '@/lib/match';
import { story } from '@/components/Story/helpers/story';

describe('story', () => {
  /** A set's rallies from who won each, a serve by `server` of the winner opening each. */
  function played(winners: Group[], server = 7, set = 1): Rally[] {
    const score: [number, number] = [0, 0];
    return winners.map((won, i) => {
      score[won - 1]++;
      const serve = { i, t: i, type: 'serve', g: won, team: won, side: 'left', rally: i, set, x: null, y: null, zone: null, result: 'play', person: server, player: null, name: null } as Contact;
      return { i, start: i * 10, end: i * 10 + 5, set, left: 1, flipped: false, winner: won, score: [...score], contacts: [serve] } as Rally;
    });
  }
  const key = (person: number) => `p${person}`;
  const finals = (rallies: Rally[]) => [{ set: 1, score: rallies[rallies.length - 1].score as [number, number] }];
  const repeat = (...parts: [Group, number][]) => parts.flatMap(([g, n]) => Array<Group>(n).fill(g));

  it('finds a run of 5 points with its server, not one of 4', () => {
    const rallies = played(repeat([1, 5], [2, 4], [1, 1]));
    const [chapter] = story(rallies, finals(rallies), key);
    expect(chapter.moments.filter((m) => m.kind === 'run')).toEqual([expect.objectContaining({ team: 1, n: 5, from: [0, 0], to: [5, 0], person: 7, rallies: [0, 1, 2, 3, 4] })]);
  });

  it('tells the scores of a run from the running team', () => {
    const rallies = played(repeat([1, 2], [2, 5]));
    const [chapter] = story(rallies, finals(rallies), key);
    expect(chapter.moments.find((m) => m.kind === 'run')).toMatchObject({ team: 2, from: [0, 2], to: [5, 2] });
  });

  it('finds a deficit of 4 caught up, and a comeback set when its winner came from behind', () => {
    const rallies = played(repeat([2, 4], [1, 2], [2, 1], [1, 5]));
    const [chapter] = story(rallies, finals(rallies), key);
    expect(chapter.moments.find((m) => m.kind === 'comeback')).toMatchObject({ team: 1, n: 4, from: [0, 4], to: [5, 5], rallies: [4, 5, 6, 7, 8, 9] });
    expect(chapter).toMatchObject({ shape: 'comeback', winner: 1, deficit: 4, score: [7, 5] });
  });

  it('leaves a comeback made within one run to the run', () => {
    const rallies = played(repeat([2, 4], [1, 5]));
    const kinds = story(rallies, finals(rallies), key)[0].moments.map((m) => m.kind);
    expect(kinds).toContain('run');
    expect(kinds).not.toContain('comeback');
  });

  it('does not tell a deficit never caught up', () => {
    const rallies = played(repeat([2, 4], [1, 2], [2, 2]));
    expect(story(rallies, finals(rallies), key)[0].moments.some((m) => m.kind === 'comeback')).toBe(false);
  });

  it('joins set points saved in a row', () => {
    const level = Array.from({ length: 44 }, (_, k): Group => (k % 2 ? 2 : 1));
    const rallies = played([...level, ...repeat([1, 2], [2, 2], [1, 2])]);
    const saved = story(rallies, finals(rallies), key)[0].moments.filter((m) => m.kind === 'setPoints');
    expect(saved).toEqual([expect.objectContaining({ team: 2, n: 2, from: [22, 24], to: [24, 24] })]);
  });

  it('tells the shape of a set from its final gap, the given score first', () => {
    const rallies = played(repeat([1, 1], [2, 1], [1, 1]));
    expect(story(rallies, [{ set: 1, score: [25, 23] }], key)[0]).toMatchObject({ shape: 'tight', score: [25, 23] });
    expect(story(rallies, [{ set: 1, score: [12, 25] }], key)[0]).toMatchObject({ shape: 'oneSided', winner: 2, score: [25, 12] });
    expect(story(rallies, [{ set: 1, score: [25, 20] }], key)[0].shape).toBe('steady');
  });

  it('counts a point once for the player with the most, 3 or more', () => {
    const rallies = played(repeat([1, 4]));
    rallies.slice(0, 3).forEach((r) => (r.contacts[0].result = 'point'));
    expect(story(rallies, finals(rallies), key)[0].top).toEqual({ person: 7, points: 3 });
    rallies[0].contacts[0].result = 'play';
    expect(story(rallies, finals(rallies), key)[0].top).toBeNull();
  });

  it('skips a rally to replay: the score did not move', () => {
    const rallies = played(repeat([1, 2]));
    rallies.splice(1, 0, { ...rallies[0], i: 9, winner: null, redo: true });
    expect(story(rallies, finals(rallies), key)[0].points.map((p) => p.rally)).toEqual([0, 1]);
  });

  it('tells the longest rally once, in its set', () => {
    const rallies = [...played(repeat([1, 2])), ...played(repeat([2, 1]), 7, 2).map((r, k) => ({ ...r, i: 2 + k }))];
    rallies[2].contacts = [...rallies[2].contacts, { ...rallies[2].contacts[0], type: 'attack', result: 'point', person: 3 }];
    const chapters = story(
      rallies,
      [
        { set: 1, score: [2, 0] },
        { set: 2, score: [0, 1] },
      ],
      key,
    );
    expect(chapters[0].moments.some((m) => m.kind === 'longest')).toBe(false);
    expect(chapters[1].moments.find((m) => m.kind === 'longest')).toMatchObject({ n: 2, person: 3 });
  });
});
