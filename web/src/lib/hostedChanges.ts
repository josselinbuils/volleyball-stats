import type { TFunction } from 'i18next';

/** A part of the page that changed since the last upload, with how many of its items and, for some, which (`review.page_changes`);
 * for the code, the commits that changed it when git tells them. */
export type PageChange = { part: string; count: number | null; keys?: string[]; commits?: string[] };

/** A cause of the late online page, with its details below it (the code's commits). */
export type ChangeLine = { text: string; details?: string[] };

/** What changed since the last upload, one cause a line for the tip on the late online page: each part by its name (its key
 * when it has none), with which of its items changed, else how many. Undefined when nothing is known. */
export function changesLines(changes: PageChange[] | null | undefined, t: TFunction): ChangeLine[] | undefined {
  if (!changes?.length) {
    return undefined;
  }
  return changes.map((c) => {
    const part = t(`review.changed.${c.part}`, { defaultValue: c.part });
    const details = c.commits?.length ? { details: c.commits } : {};
    if (c.keys?.length) {
      const keys = c.keys.map((k) => (c.part === 'people' ? k : t(`review.changedKeys.${c.part}.${k}`, { defaultValue: k })));
      return { text: t('review.changedWhich', { part, keys: keys.join(', ') }), ...details };
    }
    return { text: c.count ? `${part} (${c.count})` : part, ...details };
  });
}
