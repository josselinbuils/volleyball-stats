import type { TFunction } from 'i18next';

/** A part of the page that changed since the last upload, with how many of its items (`review.page_changes`). */
export type PageChange = { part: string; count: number | null };

const NAMED = ['rallies', 'contacts', 'people', 'films', 'scores', 'teams', 'timeouts', 'voice', 'code'];

/** What changed since the last upload, for the tip on the late online page: the parts a viewer knows by name, with their
 * count, then one word for the rest. Undefined when nothing is known. */
export function changesLabel(changes: PageChange[] | null | undefined, t: TFunction): string | undefined {
  if (!changes?.length) {
    return undefined;
  }
  const named = changes.filter((c) => NAMED.includes(c.part));
  const parts = named.map((c) => t(`review.changed.${c.part}`) + (c.count ? ` (${c.count})` : ''));
  if (named.length < changes.length) {
    parts.push(t('review.changed.other'));
  }
  return parts.join(' · ');
}
