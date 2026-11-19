import { afterEach, describe, expect, it, vi } from 'vitest';
import { fingerprint, keyLink, linkedKey, newPassword } from './videoPassword';

describe('videoPassword', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('makes the fingerprint the server lists (matches.fingerprint)', async () => {
    // hashlib.sha256(b"volleyball:secret").hexdigest()
    expect(await fingerprint('secret')).toBe('f9f844ef5b0973286cd6bc0eaf78bd6469ddfc26ccf294de9ae6dcf1a8873a39');
  });

  it('makes new passwords of twelve readable letters', () => {
    const made = new Set(Array.from({ length: 50 }, newPassword));
    expect(made.size).toBe(50);
    for (const password of made) {
      expect(password).toMatch(/^[a-hjkmnp-z2-9]{3}(-[a-hjkmnp-z2-9]{3}){3}$/);
    }
  });

  it('takes the key a shared link brings out of the address', () => {
    const at = (url: string) => {
      const { pathname, search, hash } = new URL(url);
      const location = { pathname, search, hash };
      vi.stubGlobal('location', location);
      vi.stubGlobal('history', { state: null, replaceState: (_: unknown, __: string, to: string) => Object.assign(location, { hash: '', pathname: to.split('?')[0] }) });
      return location;
    };
    const key = 'a'.repeat(64);
    const link = keyLink('https://example.org/v/m/?x=1#saison', key);
    expect(link).toBe(`https://example.org/v/m/?x=1#key=${key}`);
    const location = at(link);
    expect(linkedKey()).toBe(key);
    expect(location.hash).toBe('');
    expect(linkedKey()).toBeNull();
    at('https://example.org/v/#key=not-a-key');
    expect(linkedKey()).toBeNull();
    expect(at('https://example.org/v/#saison') && linkedKey()).toBeNull();
  });
});
