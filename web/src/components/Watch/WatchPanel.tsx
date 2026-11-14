import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { VideoButton } from '@/components/VideoButton';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import { entryDetail, entryTime, useWatchList } from '@/components/Watch/useWatchList';

/** In full screen, over the player's right above its control bar: what plays (`useWatchList`), the current one lit and
 * kept in view, each line playing from it. `light` beside the court's replay, else over the video. */
export function WatchPanel({ light, onClose }: { light: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { title, playing, whole, entries, at, pick } = useWatchList();
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    // Only the list scrolls: scrollIntoView would also move the page under the full screen.
    const box = list.current;
    const item = box?.children[at] as HTMLElement | undefined;
    if (box && item && (item.offsetTop < box.scrollTop || item.offsetTop + item.offsetHeight > box.scrollTop + box.clientHeight)) {
      box.scrollTop = item.offsetTop - (box.clientHeight - item.offsetHeight) / 2;
    }
  }, [at, entries.length]);

  return (
    <div
      className={cn(
        'absolute right-2 bottom-full z-20 mb-2 flex max-h-[calc(100dvh-7rem)] w-80 max-w-[calc(100%-1rem)] flex-col overflow-hidden rounded-lg text-sm',
        light ? 'border bg-popover text-popover-foreground shadow-md' : 'bg-black/75 text-white backdrop-blur-sm',
      )}
    >
      <div className="flex items-center gap-2 py-1 pr-1 pl-3">
        <p className="min-w-0 flex-1 truncate font-semibold">
          {whole ? t('rallies') : title(t)}
          {playing && <span className={cn('ml-2 font-normal tabular-nums', light ? 'text-muted-foreground' : 'text-white/75')}>{t('iOfN', { i: f.num(at + 1), n: f.num(entries.length) })}</span>}
        </p>
        <VideoButton light={light} label={t('sheetClose')} onClick={onClose}>
          <X aria-hidden />
        </VideoButton>
      </div>
      <ol ref={list} className="relative min-h-0 overflow-y-auto overscroll-contain pb-1">
        {entries.map((e, k) => (
          <li key={e.clip ? `${k}-${e.clip.start}` : e.rally.i}>
            <button
              type="button"
              aria-current={k === at || undefined}
              onClick={() => pick(k)}
              className={cn(
                'grid w-full border-l-3 border-transparent px-3 py-1.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-inset',
                light ? 'hover:bg-foreground/10 focus-visible:ring-ring/50' : 'hover:bg-white/15 focus-visible:ring-white/70',
                k === at && (light ? 'border-primary bg-primary/8' : 'border-primary bg-white/20'),
              )}
            >
              <span className="tabular-nums">
                <b className="font-semibold">{t('rally', { n: e.rally.i + 1 })}</b>
                {` · ${entryTime(e)}`}
              </span>
              {entryDetail(e, t, f) && <span className={cn('truncate text-xs', light ? 'text-muted-foreground' : 'text-white/75')}>{entryDetail(e, t, f)}</span>}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
