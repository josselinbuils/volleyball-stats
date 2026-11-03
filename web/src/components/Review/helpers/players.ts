import type { Group } from '@/lib/match';
import { allMarked, type Named } from '@/lib/review';

type Who = { team: Group; identity: number };
export type NameOf = (team: Group, identity: number) => string | null;

const fold = (name: string) => name.trim().toLocaleLowerCase();
const keyOf = (p: Who) => `${p.team}:${p.identity}`;

/** Whether two players of a team carry the same name: one player once applied. */
export function sameName(a: Who, b: Who, nameOf: NameOf): boolean {
  const x = nameOf(a.team, a.identity);
  const y = nameOf(b.team, b.identity);
  return a.team === b.team && !!x && !!y && fold(x) === fold(y);
}

/** The players a list offers: one per name, the first in `players`' order (longest on court first)
 * with pictures left; none for `exclude` and its namesakes, nor those whose every picture is marked
 * as someone else, unless chosen. `value` comes back as the entry standing for it. */
export function playerOptions(players: Named[], nameOf: NameOf, exclude: Who | undefined, value: string): { options: Named[]; value: string } {
  const options: Named[] = [];
  let shown = value;
  for (const p of players) {
    if (exclude && (keyOf(p) === keyOf(exclude) || sameName(p, exclude, nameOf))) {
      continue;
    }
    const twin = options.find((o) => sameName(o, p, nameOf));
    if (twin) {
      if (keyOf(p) === value) {
        shown = keyOf(twin);
      }
      continue;
    }
    if (!allMarked(p) || keyOf(p) === value) {
      options.push(p);
    }
  }
  return { options, value: shown };
}

/** A named player's picture: the match page's one (`people`), else the first of their card. */
export function pictureOf(p: Named, nameOf: NameOf, people: { team: number | null; number: number | null; photo?: string }[]): string | undefined {
  if (!nameOf(p.team, p.identity)) {
    return undefined;
  }
  return people.find((x) => x.team === p.team && x.number === p.identity)?.photo ?? p.crops[0];
}

/** A player's jersey number: the one given, on them or a namesake, else the one read. */
export function jerseyOf(p: Named, players: Named[], nameOf: NameOf): number | null {
  const same = players.filter((o) => o === p || sameName(o, p, nameOf));
  return p.jersey ?? same.find((o) => o.jersey !== null)?.jersey ?? p.read ?? same.find((o) => o.read !== null)?.read ?? null;
}

/** Folds a text for matching: no accents, no case, no outer spaces. */
const plain = (text: string) =>
  text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .trim()
    .toLocaleLowerCase();

/** The entries whose label holds `text` (no accents, no case), the one it spells first, then those
 * wearing it; all of them for no text. */
export function matching<T extends { label: string; jersey?: number | null }>(entries: T[], text: string): T[] {
  const typed = plain(text);
  const rank = (e: T) => (plain(e.label) === typed ? 0 : e.jersey != null && String(e.jersey) === typed ? 1 : 2);
  return entries.filter((e) => plain(e.label).includes(typed)).sort((a, b) => rank(a) - rank(b));
}
