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

/** Folds a text for matching: no accents, no case, no outer spaces. */
const plain = (text: string) =>
  text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .trim()
    .toLocaleLowerCase();

/** The key of the entry `text` designates: the one whose label it is, else the only one whose
 * label holds it; null for none or several. */
export function entryOf(entries: { key: string; label: string }[], text: string): string | null {
  const typed = plain(text);
  if (!typed) {
    return null;
  }
  const exact = entries.find((e) => plain(e.label) === typed);
  const holding = entries.filter((e) => plain(e.label).includes(typed));
  return exact?.key ?? (holding.length === 1 ? holding[0].key : null);
}
