import { match } from '@/lib/match';

const storageKey = () => `volleyball-stats-me:${match.name}`;

/** The player the viewer said they are on this device, by `playerKey`. */
export function remembered(): string | null {
  try {
    return localStorage.getItem(storageKey());
  } catch {
    return null;
  }
}

export function remember(key: string) {
  try {
    localStorage.setItem(storageKey(), key);
  } catch {
    // Storage blocked: the choice lasts until the page closes.
  }
}
