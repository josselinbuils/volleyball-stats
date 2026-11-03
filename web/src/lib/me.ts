import { match } from '@/lib/match';

const storageKey = (name: string = match.name) => `volleyball-stats-me:${name}`;

/** The player the viewer said they are on this device, by `playerKey`. */
export function remembered(): string | null {
  try {
    // Chosen under a name the match had before, the choice stays.
    return [match.name, ...(match.aliases ?? [])].map((name) => localStorage.getItem(storageKey(name))).find(Boolean) ?? null;
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
