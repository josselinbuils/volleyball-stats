import type { TFunction } from 'i18next';
import type { Format } from '@/lib/format';
import { groupName, match, teams } from '@/lib/match';

/** The match's title: the one the user typed, else "Match <team 1> vs <team 2>" with the names the
 * rest of the page shows; null without teams. */
export function matchTitle(t: TFunction): string | null {
  if (match.title) {
    return match.title;
  }
  if (!teams) {
    return null;
  }
  return t('matchTitle', { one: groupName(t, 1), two: groupName(t, 2) });
}

/** The browser tab's title: the match's with its date, the file name's without teams. */
export function tabTitle(t: TFunction, f: Format): string {
  const title = matchTitle(t);
  if (!title) {
    return `${match.name} · ${t('report')}`;
  }
  return match.date ? `${title} · ${f.date(match.date)}` : title;
}
