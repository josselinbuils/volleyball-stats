import { describe, expect, it } from 'vitest';
import { LANDMARKS, importError, nextLandmark, parseTime, teamNames, validName } from './setup';

describe('setup', () => {
  it('reads times as m:ss or h:mm:ss', () => {
    expect(parseTime('1:30')).toBe(90);
    expect(parseTime('1:02:03')).toBe(3723);
    expect(parseTime('45')).toBe(45);
    expect(parseTime('')).toBeNull();
    expect(parseTime('1:x')).toBeNull();
  });

  it('refuses the names the command line cannot carry', () => {
    expect(validName('ASPOM 1')).toBe(true);
    expect(validName(' ')).toBe(false);
    expect(validName('A,B')).toBe(false);
    expect(validName('A:B')).toBe(false);
  });

  it('goes through the landmarks in order', () => {
    expect(nextLandmark(0)).toBe('corner_left_far');
    expect(nextLandmark(LANDMARKS.length - 1)).toBe('post_near');
    expect(nextLandmark(LANDMARKS.length)).toBeNull();
  });

  it('says why an import was refused', () => {
    expect(importError('unreadable:DJI_0003.MP4')).toEqual(['app.import.unreadable', { name: 'DJI_0003.MP4' }]);
    expect(importError('disk:120')).toEqual(['app.import.disk', { gb: '120' }]);
    expect(importError('running')).toEqual(['app.import.running', {}]);
    expect(importError('boom')).toEqual(['app.import.failed', { error: 'boom' }]);
  });

  it('names the teams only when both have a name', () => {
    expect(teamNames({ name: 'm', teams: [{ name: 'A' }, { name: 'B' }] as never })).toEqual(['A', 'B']);
    expect(teamNames({ name: 'm', teams: null })).toBeNull();
  });
});
