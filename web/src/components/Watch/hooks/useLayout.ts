import { useCallback, useState } from 'react';
import { defaultLayout, parsed, type Layout, type View } from '@/components/Watch/helpers/layout';

const STORED = 'watch-layout';

interface Saved {
  page: Layout;
  full: Layout | null;
}

function read(available: readonly View[]): Saved {
  const page = defaultLayout(available.includes('video') ? ['video', '2d'] : ['2d']);
  try {
    const stored = JSON.parse(localStorage.getItem(STORED) ?? 'null') as { page?: unknown; full?: unknown } | null;
    return { page: parsed(stored?.page, available) ?? page, full: parsed(stored?.full, available) };
  } catch {
    return { page, full: null };
  }
}

/** The layout of the page or of full screen, each remembered by the browser when it can. Full screen
 * starts on the video alone, else on the page's first view. */
export function useLayout(full: boolean, available: readonly View[]): [Layout, (change: (layout: Layout) => Layout) => void] {
  const [saved, setSaved] = useState(() => read(available));
  const entering = (page: Layout): Layout => ({ ...page, order: [page.order.includes('video') ? 'video' : page.order[0]], before: null });
  const key = full ? 'full' : 'page';
  const update = useCallback(
    (change: (layout: Layout) => Layout) => {
      setSaved((now) => {
        const next = { ...now, [key]: change(now[key] ?? entering(now.page)) };
        try {
          localStorage.setItem(STORED, JSON.stringify(next));
        } catch {
          // Private browsing: the layout lasts for the page only.
        }
        return next;
      });
    },
    [key],
  );
  return [full ? (saved.full ?? entering(saved.page)) : saved.page, update];
}
