import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import type { TFunction } from 'i18next';
import type { Format } from '@/lib/format';
import { clipLabel, contactClips, rallyAt, rallyClips, rallyNear } from '@/lib/playlist';

describe('contactClips', () => {
  // The player's key is their number here.
  const touch = (t: number, type: string, g: number, rally = 0, player: number | null = null) => ({ t, type, g, rally, player, person: player, name: null }) as Contact;

  it('plays from 2 s before each touch to 1.5 s after, within the video', () => {
    const clips = contactClips([touch(1, 'serve', 1), touch(50, 'serve', 1, 3), touch(59, 'serve', 1, 4)], 60);
    expect(clips.map((c) => [c.start, c.end, c.rally, c.time])).toEqual([
      [0, 2.5, 0, 1],
      [48, 51.5, 3, 50],
      [57, 60, 4, 59],
    ]);
  });

  it('names the action, the team and the player only when the playlist mixes them', () => {
    expect(contactClips([touch(5, 'serve', 1), touch(9, 'serve', 1)], 60)[0]).toMatchObject({ type: undefined, team: undefined, player: undefined });
    expect(contactClips([touch(5, 'serve', 1), touch(9, 'attack', 1)], 60)[1]).toMatchObject({ type: 'attack', team: undefined });
    expect(contactClips([touch(5, 'serve', 1), touch(9, 'serve', 2, 0, 3)], 60)[1]).toMatchObject({ type: undefined, team: 2, player: 3 });
  });

  it('names the player when the user named them', () => {
    const t = ((key: string, o?: { n: number }) => `${key}${o ? ` ${o.n}` : ''}`) as TFunction;
    const clip = contactClips([touch(1, 'serve', 1, 0, 3), { ...touch(5, 'serve', 1, 0, 4), name: 'Julie' }], 60)[1];
    expect(clipLabel(clip, t, {} as Format, (g) => `Team ${g}`)).toBe('Julie · rallyLower 1 · 0:05');
  });

  it('labels a touch with its action, team, player, rally and time', () => {
    const t = ((key: string, o?: { n: number }) => `${key}${o ? ` ${o.n}` : ''}`) as TFunction;
    const clip = contactClips([touch(5, 'serve', 1), touch(65, 'attack', 2, 3, 4)], 70)[1];
    expect(clipLabel(clip, t, {} as Format, (g) => `Team ${g}`)).toBe('types.attack · Team 2 · player 4 · rallyLower 4 · 1:05');
  });
});

describe('rallyClips', () => {
  const rallies = [
    { i: 0, start: 0.5, end: 4, contacts: [] },
    { i: 7, start: 20, end: 29.5, contacts: [] },
  ] as unknown as Rally[];

  it('plays each rally with a second around it, within the video, keeping its number', () => {
    expect(rallyClips(rallies, 30)).toEqual([
      { start: 0, end: 5, rally: 0, time: 0.5, length: 3.5 },
      { start: 19, end: 30, rally: 7, time: 20, length: 9.5 },
    ]);
  });

  it('finds the rally whose clip holds a time', () => {
    expect(rallyAt(rallies, 4.9)?.i).toBe(0);
    expect(rallyAt(rallies, 19.2)?.i).toBe(7);
    expect(rallyAt(rallies, 10)).toBeUndefined();
  });

  describe('rallyNear', () => {
    const rallies = [
      { i: 0, start: 10, end: 15 },
      { i: 1, start: 30, end: 40 },
    ];

    it('takes the rally being played, else the next one, else the last', () => {
      expect(rallyNear(rallies, 12)?.i).toBe(0);
      expect(rallyNear(rallies, 0)?.i).toBe(0);
      expect(rallyNear(rallies, 20)?.i).toBe(1);
      expect(rallyNear(rallies, 90)?.i).toBe(1);
      expect(rallyNear([], 5)).toBeUndefined();
    });
  });
});
