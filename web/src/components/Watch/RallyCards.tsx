import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Legend } from '@/components/Court';
import { clock, useFormat } from '@/lib/format';
import { color, match, present, rallies } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { rallyAt, rallyClips } from '@/lib/playlist';

/** One card per rally with the letters of its touches; the current rally stands out. */
export function RallyCards() {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const current = useVideoTime((time) => rallyAt(rallies, time)?.i ?? -1);
  const list = useRef<HTMLOListElement>(null);

  // Keeps the current rally's card in view inside the list, without scrolling the page.
  useEffect(() => {
    const box = list.current;
    const item = box?.children[current] as HTMLElement | undefined;
    if (box && item && (item.offsetTop < box.scrollTop || item.offsetTop + item.offsetHeight > box.scrollTop + box.clientHeight)) {
      box.scrollTop = item.offsetTop - 8;
    }
  }, [current]);

  return (
    <div>
      <h3 className="font-semibold">{t('rallies')}</h3>
      {rallies.length ? (
        <ol ref={list} className="relative mt-3 grid max-h-80 grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] sm:grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-2 overflow-y-auto p-0.5">
          {rallies.map((r) => (
            <li key={r.i}>
              <button
                type="button"
                title={t('watchRally')}
                aria-current={r.i === current || undefined}
                onClick={() => play((tr) => tr('rallies'), rallyClips(rallies, match.duration), r.i)}
                className={cn(
                  'grid h-full w-full content-start gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
                  r.i === current && 'border-primary bg-primary/8 hover:bg-primary/12',
                )}
              >
                <span className="flex flex-wrap gap-x-2.5 text-[13px] text-muted-foreground tabular-nums">
                  <b className="font-semibold text-foreground">{t('rally', { n: r.i + 1 })}</b>
                  <span>{clock(r.start)}</span>
                  <span>{f.secs(r.end - r.start)}</span>
                </span>
                {r.contacts.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {r.contacts.map((c) => (
                      <span
                        key={c.i}
                        aria-hidden
                        title={t(`types.${c.type}`)}
                        className="rounded-[5px] px-1.5 text-[11px] leading-[18px] font-semibold"
                        style={{ background: `color-mix(in srgb, ${color(c.type)} 22%, transparent)`, boxShadow: `inset 2px 0 0 ${color(c.type)}` }}
                      >
                        {t(`short.${c.type}`)}
                      </span>
                    ))}
                    <span className="sr-only">{r.contacts.map((c) => t(`types.${c.type}`)).join(', ')}</span>
                  </span>
                )}
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-2 text-muted-foreground">{t('noRallies')}</p>
      )}
      {present.length > 0 && (
        <Legend className="mt-3">
          <span>{t('letters')}</span>
          {present.map((type) => (
            <span key={type}>
              <b className="mr-1 font-semibold text-foreground">{t(`short.${type}`)}</b>
              {t(`types.${type}`)}
            </span>
          ))}
        </Legend>
      )}
    </div>
  );
}
