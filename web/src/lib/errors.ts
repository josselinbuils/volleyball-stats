import type { TFunction } from 'i18next';

/** A failure in words: `text`, the server's own words as `detail` (often technical, shown small below it), `log` when the
 * app's log may tell more. */
export type Explained = { text: string; detail: string | null; log: boolean };

// The codes a server's refusal names, said the same way everywhere.
const KNOWN: Record<string, string> = { network: 'error.noAnswer', busy: 'error.busy' };

/** A server's refusal `error` in words: its code's sentence when known, else `fallback`'s with the server's words as the detail. */
export function explain(t: TFunction, error: string | null | undefined, fallback = 'error.failed'): Explained {
  if (error && KNOWN[error]) {
    return { text: t(KNOWN[error]), detail: null, log: false };
  }
  return { text: t(fallback), detail: error || null, log: true };
}
