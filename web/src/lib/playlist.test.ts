import { describe, expect, it } from 'vitest';
import type { Contact, Rally } from '@/lib/match';
import { contactClips, rallyAt, rallyClips } from '@/lib/playlist';

describe('contactClips', () => {
  const touch = (t: number, type: string, side: string, rally = 0) => ({ t, type, side, rally }) as Contact;

  it('plays from 2 s before each touch to 1.5 s after, within the video', () => {
    const clips = contactClips([touch(1, 'serve', 'left'), touch(50, 'serve', 'left', 3), touch(59, 'serve', 'left', 4)], 60);
    expect(clips.map((c) => [c.start, c.end, c.rally, c.time])).toEqual([
      [0, 2.5, 0, 1],
      [48, 51.5, 3, 50],
      [57, 60, 4, 59],
    ]);
  });

  it('names the action and the side only when the playlist mixes them', () => {
    expect(contactClips([touch(5, 'serve', 'left'), touch(9, 'serve', 'left')], 60)[0]).toMatchObject({ type: undefined, side: undefined });
    expect(contactClips([touch(5, 'serve', 'left'), touch(9, 'attack', 'left')], 60)[1]).toMatchObject({ type: 'attack', side: undefined });
    expect(contactClips([touch(5, 'serve', 'left'), touch(9, 'serve', 'right')], 60)[1]).toMatchObject({ type: undefined, side: 'right' });
  });
});

describe('rallyClips', () => {
  const rallies = [
    { i: 0, start: 0.5, end: 4, contacts: [] },
    { i: 7, start: 20, end: 29.5, contacts: [] },
  ] as Rally[];

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
});
