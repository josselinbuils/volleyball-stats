import { afterEach, describe, expect, it, vi } from 'vitest';
import { marked, type Named } from '@/lib/review';
import { matching, playerOptions, sameName } from '@/components/Review/helpers/players';

// review.ts reads window.REVIEW on import.
vi.hoisted(() => {
  Object.assign(globalThis, { window: {} });
});

describe('players', () => {
  const player = (identity: number, track: number): Named => ({
    team: 1,
    identity,
    seconds: 0,
    contacts: 0,
    crops: [],
    pieces: [{ track, frame: 0 }],
    name: null,
    jersey: null,
    suggestions: [],
  });
  const players = [player(3, 30), player(12, 120), player(5, 50)];
  const names: Record<number, string> = { 3: 'Paul', 12: ' paul ', 5: 'Léa' };
  const nameOf = (_: number, identity: number) => names[identity] ?? null;

  afterEach(() => marked.clear());

  it('tells namesakes apart from players without a name', () => {
    expect(sameName(players[0], players[1], nameOf)).toBe(true);
    expect(sameName(players[0], players[2], nameOf)).toBe(false);
    expect(sameName(players[0], { team: 1, identity: 9 }, nameOf)).toBe(false);
  });

  it('offers each name once and shows a namesake chosen as the entry standing for it', () => {
    const { options, value } = playerOptions(players, nameOf, undefined, '1:12');

    expect(options.map((p) => p.identity)).toEqual([3, 5]);
    expect(value).toBe('1:3');
  });

  it('leaves out the excluded player with their namesakes', () => {
    expect(playerOptions(players, nameOf, { team: 1, identity: 12 }, '').options.map((p) => p.identity)).toEqual([5]);
  });

  it('lets the next namesake stand for a player whose pictures are all marked', () => {
    marked.set('30:0', null);

    expect(playerOptions(players, nameOf, undefined, '').options.map((p) => p.identity)).toEqual([12, 5]);
  });

  it('lists the entries a typed text matches, the one it spells first', () => {
    const entries = [
      { key: '2:5', label: 'Joueur 5 · ASPOM 02' },
      { key: '1:3', label: 'Paul (joueur 3) · ASPOM 01' },
      { key: '1:5', label: 'Léa (joueur 5) · ASPOM 01' },
    ];

    expect(matching(entries, 'lea').map((e) => e.key)).toEqual(['1:5']);
    expect(matching(entries, ' 5').map((e) => e.key)).toEqual(['2:5', '1:5']);
    expect(matching(entries, 'joueur 5 · aspom 02').map((e) => e.key)).toEqual(['2:5']);
    expect(matching(entries, '')).toHaveLength(3);
  });
});
