import { afterEach, describe, expect, it, vi } from 'vitest';
import { marked, type Named } from '@/lib/review';
import { jerseyOf, matching, pictureOf, playerOptions, sameName, unnamedFirst } from '@/components/Review/helpers/players';

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
    read: null,
    suggestions: [],
  });
  const players = [player(3, 30), player(12, 120), player(5, 50)];
  const names: Record<number, string> = { 3: 'Paul', 12: ' paul ', 5: 'Léa' };
  const nameOf = (_: number, identity: number) => names[identity] ?? null;

  afterEach(() => marked.clear());

  it('gives a named player their first picture, and nothing to a player without a name', () => {
    const named = { ...players[0], crops: ['crop-a', 'crop-b'] };
    expect(pictureOf(named, nameOf, [])).toBe('crop-a');
    expect(pictureOf({ ...named, identity: 9 }, nameOf, [])).toBeUndefined();
  });

  it("prefers the match page's picture", () => {
    const named = { ...players[0], crops: ['crop-a'] };
    expect(pictureOf(named, nameOf, [{ team: 1, number: 3, photo: 'photo' }])).toBe('photo');
    expect(pictureOf(named, nameOf, [{ team: 2, number: 3, photo: 'photo' }])).toBe('crop-a');
  });

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

  it('puts the players without a name first, keeping their order', () => {
    const [a, b, c] = players;
    const sorted = unnamedFirst([{ ...a, name: 'Paul' }, b, { ...c, name: 'Léa' }, player(7, 70)]);

    expect(sorted.map((p) => p.identity)).toEqual([12, 7, 3, 5]);
  });

  it('lists first the player wearing a typed number', () => {
    const entries = [
      { key: '1:3', label: 'Joueur 3 · ASPOM 01', jersey: 38 },
      { key: '1:5', label: '#3 Léa (joueur 5) · ASPOM 01', jersey: 3 },
    ];

    expect(matching(entries, '3').map((e) => e.key)).toEqual(['1:5', '1:3']);
    expect(matching(entries, '38').map((e) => e.key)).toEqual([]);
  });

  it('takes the jersey number given, on the player or a namesake, before the one read', () => {
    const [paul, namesake, lea] = players;

    expect(jerseyOf({ ...lea, read: 8 }, players, nameOf)).toBe(8);
    expect(jerseyOf({ ...lea, jersey: 9, read: 8 }, players, nameOf)).toBe(9);
    expect(jerseyOf(paul, [paul, { ...namesake, jersey: 7 }, lea], nameOf)).toBe(7);
    expect(jerseyOf({ ...paul, read: 8 }, [paul, { ...namesake, jersey: 7 }, lea], nameOf)).toBe(7);
    expect(jerseyOf(paul, players, nameOf)).toBeNull();
  });
});
