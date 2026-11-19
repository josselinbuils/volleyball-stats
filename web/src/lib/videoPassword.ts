// The one password of every match's video. The app keeps it (matches.PASSWORD); the server and the viewer's cookie only
// its fingerprint, which a shared link carries too (`#key=`) to open the videos without the password.

export const VIDEO_MIN = 6;
// The video page's cookie holds the SHA-256 of this and the password, the server the same (matches.fingerprint).
const SALT = 'volleyball:';
const COOKIE = 'video_key';
const KEY = /^[0-9a-f]{64}$/;
// No 0/o, 1/l/i: a password read aloud or copied by hand.
const LETTERS = 'abcdefghjkmnpqrstuvwxyz23456789';

/** The fingerprint of `password` the server lists and the page's cookie holds. */
export async function fingerprint(password: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(SALT + password));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** `url` opening the videos without the password, for `key` (`fingerprint`). */
export function keyLink(url: string, key: string): string {
  return `${url.split('#')[0]}#key=${key}`;
}

/** The key a shared link (`keyLink`) brought, taken out of the address; null without one or for one malformed. */
export function linkedKey(): string | null {
  const found = new URLSearchParams(location.hash.slice(1)).get('key');
  if (found === null) {
    return null;
  }
  history.replaceState(history.state, '', location.pathname + location.search);
  return KEY.test(found) ? found : null;
}

/** Whether this browser holds a key to the videos. */
export function hasVideoKey(): boolean {
  return document.cookie.split('; ').some((c) => c.startsWith(`${COOKIE}=`));
}

/** The key kept a year for every match of the site at `path` (the list's folder), or removed. */
export function setVideoKey(key: string | null, path: string): void {
  document.cookie = `${COOKIE}=${key ?? ''}; Path=${path}; Max-Age=${key ? 31536000 : 0}; Secure; SameSite=Lax`;
}

/** A new password, 12 letters and digits in threes (~59 bits), easy to read out. */
export function newPassword(): string {
  const picked: string[] = [];
  // Only bytes under the largest multiple of the alphabet's size: every letter as likely.
  const limit = 256 - (256 % LETTERS.length);
  while (picked.length < 12) {
    for (const byte of crypto.getRandomValues(new Uint8Array(16))) {
      if (byte < limit && picked.length < 12) {
        picked.push(LETTERS[byte % LETTERS.length]);
      }
    }
  }
  return [0, 3, 6, 9].map((k) => picked.slice(k, k + 3).join('')).join('-');
}
