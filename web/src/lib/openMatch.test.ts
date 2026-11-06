import { afterEach, describe, expect, it, vi } from 'vitest';
import { reachedMatch } from '@/lib/openMatch';

describe('reachedMatch', () => {
  const at = (pathname: string, hash: string) => {
    const location = { pathname, hash, href: `${pathname}${hash}`, reload: vi.fn() };
    vi.stubGlobal('location', location);
    vi.stubGlobal('fetch', async () => ({ json: async () => ({ name: 'next' }) }));
    return location;
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reloads the review it is on, whose hash alone would not', async () => {
    const location = at('/review', '#match');
    await reachedMatch('next');
    expect(location.reload).toHaveBeenCalled();
    expect(location.href).toBe('/review#match');
  });

  it('goes to the review from the list, keeping the hash', async () => {
    const location = at('/matches/', '#season');
    await reachedMatch('next');
    expect(location.reload).not.toHaveBeenCalled();
    expect(location.href).toBe('/review#season');
  });
});
