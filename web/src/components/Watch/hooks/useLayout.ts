import { useCallback, useState } from 'react';
import { defaultLayout, parsed, type Layout, type View } from '@/components/Watch/helpers/layout';

const STORED = 'watch-layout';

function read(available: readonly View[]): Layout {
  const first = defaultLayout(available.includes('video') ? ['video', '2d'] : ['2d']);
  try {
    return parsed(JSON.parse(localStorage.getItem(STORED) ?? 'null'), available) ?? first;
  } catch {
    return first;
  }
}

/** The views' layout, the same on the page and in full screen, remembered by the browser when it can. */
export function useLayout(available: readonly View[]): [Layout, (change: (layout: Layout) => Layout) => void] {
  const [layout, setLayout] = useState(() => read(available));
  const update = useCallback((change: (layout: Layout) => Layout) => {
    setLayout((now) => {
      const next = change(now);
      try {
        localStorage.setItem(STORED, JSON.stringify(next));
      } catch {
        // Private browsing: the layout lasts for the page only.
      }
      return next;
    });
  }, []);
  return [layout, update];
}
