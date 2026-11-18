import { describe, expect, it } from 'vitest';
import { fingerprint, newPassword, open, seal, unlock } from './vault';

describe('vault', () => {
  it('opens what it sealed with the same master password only', async () => {
    const vault = (await unlock('a long master password', []))!;
    const sealed = await seal(vault, 'abc-def');
    expect(sealed.data).not.toContain('abc');
    expect(await open(vault, sealed)).toBe('abc-def');
    expect(await unlock('another master password', [sealed])).toBeNull();
    const again = (await unlock('a long master password', [sealed]))!;
    expect(await open(again, await seal(again, 'ghj'))).toBe('ghj');
    expect(await open(again, { ...sealed, data: sealed.data.replace(/^./, (c) => (c === 'A' ? 'B' : 'A')) })).toBeNull();
  }, 20_000);

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
});
