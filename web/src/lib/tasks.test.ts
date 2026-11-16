import { describe, expect, it } from 'vitest';
import { isHere, taskHref, type Task } from '@/lib/tasks';

const task = (kind: string): Task => ({ id: kind, kind, running: true });

describe('tasks', () => {
  it('leads each task to its own screen', () => {
    expect(taskHref(task('review'))).toBe('/review');
    expect(taskHref(task('hosting'))).toBe('/matches/#site');
    expect(taskHref(task('pipeline'))).toBe('/matches/');
  });

  it('knows the screen shown', () => {
    expect(isHere('/matches/#site', { pathname: '/matches/', hash: '#site' } as Location)).toBe(true);
    expect(isHere('/matches/', { pathname: '/matches/', hash: '#site' } as Location)).toBe(false);
    expect(isHere('/review', { pathname: '/review', hash: '#match' } as Location)).toBe(true);
    expect(isHere('/review', { pathname: '/page', hash: '' } as Location)).toBe(false);
  });
});
