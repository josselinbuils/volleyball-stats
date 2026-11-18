// The videos' passwords, sealed by the owner's master password in this browser: PBKDF2-SHA256 (ROUNDS) makes an AES-256-GCM
// key from it and the salt every sealed password shares, so one unlock opens them all. The app's server keeps only what this
// seals and each password's fingerprint (matches.py's PASSWORD), never a password nor the master one.

/** What the app's server keeps of a video's password (matches.SEALED). */
export type Sealed = { v: number; iter: number; salt: string; iv: string; data: string };

/** The master password's key, its salt and rounds: in memory only, while unlocked. */
export type Vault = { key: CryptoKey; salt: string; iter: number };

// OWASP's count for PBKDF2-SHA256 (2023); matches.SEALED_ROUNDS refuses fewer.
const ROUNDS = 600_000;
export const VIDEO_MIN = 8;
export const MASTER_MIN = 12;
// The video page's cookie holds the SHA-256 of this and the password (VideoChoice.tsx), the server the same.
const SALT = 'volleyball:';
// No 0/o, 1/l/i: a password read aloud or copied by hand.
const LETTERS = 'abcdefghjkmnpqrstuvwxyz23456789';

const encode = (text: string) => new TextEncoder().encode(text);
const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes));
const unb64 = (text: string) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

/** The fingerprint of `password` the server lists and the page's cookie holds. */
export async function fingerprint(password: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', encode(SALT + password));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function derive(master: string, salt: string, iter: number): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey('raw', encode(master), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: unb64(salt), iterations: iter }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}

/** The vault `master` opens, checked on the first of `sealed` (those kept); with none, a new one with a new salt. Null for a
 * wrong master password. */
export async function unlock(master: string, sealed: Sealed[]): Promise<Vault | null> {
  const first = sealed[0];
  const salt = first?.salt ?? b64(crypto.getRandomValues(new Uint8Array(16)));
  const iter = first?.iter ?? ROUNDS;
  const vault = { key: await derive(master, salt, iter), salt, iter };
  return !first || (await open(vault, first)) !== null ? vault : null;
}

/** `password` sealed for the server to keep. */
export async function seal(vault: Vault, password: string): Promise<Sealed> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, vault.key, encode(password));
  return { v: 1, iter: vault.iter, salt: vault.salt, iv: b64(iv), data: b64(new Uint8Array(data)) };
}

/** The password in `sealed`, null if this vault cannot open it (another master password, altered). */
export async function open(vault: Vault, sealed: Sealed): Promise<string | null> {
  if (sealed.salt !== vault.salt || sealed.iter !== vault.iter) {
    return null;
  }
  try {
    return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(sealed.iv) }, vault.key, unb64(sealed.data)));
  } catch {
    return null;
  }
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
