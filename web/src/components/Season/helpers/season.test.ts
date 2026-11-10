import { describe, expect, it } from 'vitest';
import type { ListedMatch } from '@/components/Matches';
import { buildSeason, matchesOf, seasonTeams } from '@/components/Season/helpers/season';
import type { Data, Person } from '@/lib/match';

describe('season', () => {
  const team = (name: string) => ({ name, colour: '#000000' });
  const listed = (path: string, date: string, one: string, two: string, rallies = 10): ListedMatch => ({
    path,
    name: path,
    date,
    title: null,
    teams: [team(one), team(two)],
    scores: null,
    sets: 1,
    rallies,
  });
  const person = (name: string | null, jersey: number | null, number: number | null, g: 1 | 2): Person => ({ team: g, name, jersey, number });
  const touch = (rally: number, person: number, type: 'serve' | 'attack' | 'pass', result: 'point' | 'play' | 'error', g: 1 | 2, set = 1) => ({
    t: rally * 10,
    type,
    side: g === 1 ? ('left' as const) : ('right' as const),
    team: g,
    rally,
    set,
    x: null,
    y: null,
    zone: null,
    person,
    result,
  });
  const data = (teams: [string, string], people: Record<string, Person>, contacts: Data['contacts'], scores: string[] | null = null): Data =>
    ({
      teams: [team(teams[0]), team(teams[1])],
      people,
      contacts,
      scores,
      rallies: contacts.map((c) => ({ start: 0, end: 1, set: c.set, left: 1, score: [1, 0] as [number, number] })),
    }) as unknown as Data;

  describe('seasonTeams', () => {
    it('holds the named teams of two matches or more, most matches first', () => {
      const matches = [listed('a', '2026-01-01', 'B', 'A'), listed('b', '2026-01-02', 'A', 'C'), listed('c', '2026-01-03', 'B', 'A'), listed('d', '2026-01-04', 'B', 'E', 0)];
      expect(seasonTeams(matches)).toEqual(['A', 'B']);
    });

    it("holds the club's teams only, once picked", () => {
      const matches = [listed('a', '2026-01-01', 'B', 'A'), listed('b', '2026-01-02', 'A', 'B')];
      expect(seasonTeams(matches, ['A'])).toEqual(['A']);
      expect(seasonTeams(matches, [])).toEqual(['A', 'B']);
    });

    it('counts a match once for a team on both sides', () => {
      expect(seasonTeams([listed('a', '2026-01-01', 'A', 'A')])).toEqual([]);
    });
  });

  it("puts a team's matches oldest first", () => {
    const matches = [listed('new', '2026-02-01', 'A', 'B'), listed('old', '2026-01-01', 'C', 'A')];
    expect(matchesOf(matches, 'A').map((m) => m.path)).toEqual(['old', 'new']);
  });

  describe('buildSeason', () => {
    const first = data(
      ['A', 'B'],
      { 1: person('Léa', null, 1, 1), 2: person('Zoé', 7, 2, 2) },
      [0, 1, 2, 3, 4, 5].map((r) => touch(r, 1, 'attack', r < 3 ? 'point' : 'play', 1)),
      ['25-20', '20-25', '25-10'],
    );
    const second = data(
      ['C', 'A'],
      { 3: person('Léa', 4, 1, 2) },
      [0, 1, 2, 3, 4, 5].map((r) => touch(r, 3, 'attack', 'point', 2, r < 3 ? 1 : 2)),
      ['20-25', '15-25'],
    );
    const season = buildSeason('A', [
      { match: listed('one', '2026-01-01', 'A', 'B'), data: first },
      { match: listed('two', '2026-01-08', 'C', 'A'), data: second },
    ]);

    it("gives results from the team's side", () => {
      expect(season.played[0]).toMatchObject({
        opponent: 'B',
        scores: [
          [25, 20],
          [20, 25],
          [25, 10],
        ],
        won: 2,
        lost: 1,
      });
      expect(season.played[1]).toMatchObject({
        opponent: 'C',
        scores: [
          [25, 20],
          [25, 15],
        ],
        won: 2,
        lost: 0,
      });
    });

    it('follows a player by name across matches, per set played', () => {
      expect(season.players.map((p) => p.key)).toEqual(['name Léa']);
      expect(season.players[0].values.points).toEqual([3, 3]);
    });

    it('leaves out a measure with too few touches', () => {
      expect(season.players[0].values.serve).toEqual([null, null]);
    });

    it('adds up the strengths of the match pages over the matches they showed in', () => {
      expect(season.players[0]).toMatchObject({ matches: 2, strengths: [{ key: 'topScorer', n: 6, of: 6, matches: 1 }], work: null });
    });

    it('shows what went up, never what went down', () => {
      const better = data(
        ['A', 'B'],
        { 1: person('Léa', null, 1, 1) },
        [0, 1, 2, 3, 4, 5].map((r) => touch(r, 1, 'attack', 'point', 1)),
      );
      const rose = buildSeason('A', [
        { match: listed('one', '2026-01-01', 'A', 'B'), data: first },
        { match: listed('two', '2026-01-08', 'A', 'B'), data: better },
      ]);
      const fell = buildSeason('A', [
        { match: listed('one', '2026-01-01', 'A', 'B'), data: better },
        { match: listed('two', '2026-01-08', 'A', 'B'), data: first },
      ]);
      expect(rose.players[0].rising).toEqual([{ measure: 'points', from: 3, to: 6 }]);
      expect(fell.players[0].rising).toEqual([]);
    });

    it('does not carry an unnamed player without a jersey across matches', () => {
      const unnamed = buildSeason('A', [{ match: listed('one', '2026-01-01', 'A', 'B'), data: data(['A', 'B'], { 1: person(null, null, 1, 1) }, [touch(0, 1, 'serve', 'play', 1)]) }]);
      expect(unnamed.players).toEqual([]);
    });
  });
});
