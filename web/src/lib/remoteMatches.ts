import type { ListedMatch } from '@/components/Matches';

/** `here` and the server's `remote` matches, newest first as the review server sorts them. */
export function withRemote(here: ListedMatch[], remote: ListedMatch[]): ListedMatch[] {
  const key = (m: ListedMatch) => `${m.date ?? ''}\u0000${m.path}`;
  return [...here, ...remote.filter((m) => !here.some((h) => h.path === m.path))].sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
}
