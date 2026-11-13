import { describe, expect, it } from 'vitest';
import { LANDMARKS, chapterAt, importError, nextLandmark, parseTime, sourceQuery, teamNames, validName } from './setup';

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

describe('chapterAt', () => {
  it('finds the chapter and the time in it', () => {
    expect(chapterAt([600, 600, 300], 0)).toEqual([0, 0]);
    expect(chapterAt([600, 600, 300], 650)).toEqual([1, 50]);
    expect(chapterAt([600, 600, 300], 1200)).toEqual([2, 0]);
    expect(chapterAt([600, 600, 300], 9999)).toEqual([2, 300]);
  });
});

describe('sourceQuery', () => {
  it('names one source or several videos picked together', () => {
    expect(sourceQuery('/mnt/e', { recording: '1' })).toBe('source=%2Fmnt%2Fe&recording=1');
    expect(sourceQuery(['/a.mp4', '/b.mp4'], { at: '3' })).toBe('source=%2Fa.mp4&source=%2Fb.mp4&at=3');
  });
});
