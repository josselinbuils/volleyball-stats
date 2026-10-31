import { afterEach, describe, expect, it, vi } from 'vitest';
import { allMarked, lookAlikes, marked, onServerBusy, post, serverBusy } from '@/lib/review';

// review.ts reads window.REVIEW on import.
vi.hoisted(() => {
  Object.assign(globalThis, { window: {} });
});

describe('allMarked', () => {
  const pieces = [
    { track: 1, frame: 10 },
    { track: 2, frame: 20 },
  ];

  afterEach(() => marked.clear());

  it('holds once every picture is marked as someone else', () => {
    marked.set('1:10', null);
    expect(allMarked({ pieces })).toBe(false);
    marked.set('2:20', '1:3');
    expect(allMarked({ pieces })).toBe(true);
  });

  it('never holds for a player without pictures', () => {
    expect(allMarked({ pieces: [] })).toBe(false);
  });
});

describe('serverBusy', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('tells what the server is doing while a request runs, saving first', async () => {
    const answers: (() => void)[] = [];
    vi.stubGlobal('fetch', () => new Promise((resolve) => answers.push(() => resolve({ ok: true, status: 200, json: async () => ({}) }))));
    const seen: (string | null)[] = [];
    const stop = onServerBusy(() => seen.push(serverBusy()));

    const loading = lookAlikes(1, 3);
    const saving = post('name', {});
    expect(serverBusy()).toBe('saving');
    answers[1]();
    await saving;
    expect(serverBusy()).toBe('loading');
    answers[0]();
    await loading;
    stop();

    expect(serverBusy()).toBeNull();
    expect(seen.at(-1)).toBeNull();
  });
});
