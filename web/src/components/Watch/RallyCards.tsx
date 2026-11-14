import { useEffect, useRef } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Legend } from '@/components/Court';
import { clock, useFormat } from '@/lib/format';
import { color, groupName, sets, TYPES } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { Tip } from '@/components/Tip';
import { entryDetail, entryTime, useWatchList } from '@/components/Watch/useWatchList';

// A card shows this many letters at most, the rest counted: one long rally would make every card in the row as tall.
const LETTERS = 10;

/** One card per rally with the letters of its touches, in one row scrolling sideways; while a playlist of other moments
 * plays, one card per moment instead, its touch lit among its rally's letters. The current one stands out. */
export function RallyCards() {
  const { t } = useTranslation();
  const f = useFormat();
  const { set } = useSet();
  const { title, playing, whole, entries, at, pick } = useWatchList();
  const list = useRef<HTMLOListElement>(null);
  const present = TYPES.filter((type) => entries.some((e) => e.rally.contacts.some((c) => c.type === type)));

  // Brings the current card to the start of the list when it is not wholly in view, without scrolling the page.
  // On the first render the list stands at its start: measuring it would only slow the first paint.
  const shown = useRef(false);
  useEffect(() => {
    if (!shown.current) {
      shown.current = true;
      return;
    }
    const box = list.current;
    const item = box?.children[at] as HTMLElement | undefined;
    if (box && item && (item.offsetLeft < box.scrollLeft || item.offsetLeft + item.offsetWidth > box.scrollLeft + box.clientWidth)) {
      const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
      box.scrollTo({ left: item.offsetLeft - (box.children[0] as HTMLElement).offsetLeft, behavior: smooth ? 'smooth' : 'auto' });
    }
  }, [at, entries.length, whole]);

  return (
    <div className="min-w-0">
      <h3 className="font-semibold">
        {whole ? t('rallies') : title(t)}
        {playing && <span className="ml-2 font-normal text-muted-foreground tabular-nums">{t('iOfN', { i: f.num(at + 1), n: f.num(entries.length) })}</span>}
      </h3>
      {entries.length ? (
        <ol ref={list} className="relative mt-3 grid auto-cols-[9.5rem] grid-flow-col items-start gap-2 overflow-x-auto p-0.5 pb-2 sm:auto-cols-[12rem]">
          {entries.map((e, k) => {
            const r = e.rally;
            const current = k === at;
            const letters = r.contacts.slice(0, r.contacts.length > LETTERS ? LETTERS - 1 : LETTERS);
            // A touch beyond the letters shown takes the last place.
            if (e.contact && !letters.includes(e.contact)) {
              letters[letters.length - 1] = e.contact;
            }
            return (
              <li key={e.clip ? `${k}-${e.clip.start}` : r.i}>
                <Tip label={t(e.contact ? 'watchClip' : 'watchRally')}>
                  <button
                    type="button"
                    aria-current={current || undefined}
                    onClick={() => pick(k)}
                    className={cn(
                      'grid h-full w-full content-start gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
                      current && 'border-primary bg-primary/8 hover:bg-primary/12',
                    )}
                  >
                    <span className="flex flex-wrap gap-x-2.5 text-[13px] text-muted-foreground tabular-nums">
                      <b className="font-semibold text-foreground">{t('rally', { n: r.i + 1 })}</b>
                      <span>{e.contact ? entryTime(e) : clock(r.start)}</span>
                      {!e.contact && <span>{f.secs(r.end - r.start)}</span>}
                      {set === null && sets.length > 1 && <span>{t('set', { n: r.set })}</span>}
                    </span>
                    {e.contact
                      ? entryDetail(e, t, f) && <span className="truncate text-xs text-foreground">{entryDetail(e, t, f)}</span>
                      : r.flipped && (
                          <Tip label={t('onTheLeft', { team: groupName(t, r.left) })}>
                            <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                              <ArrowLeftRight aria-hidden className="size-3.5 shrink-0" />
                              <span className="truncate">{t('onTheLeft', { team: groupName(t, r.left) })}</span>
                            </span>
                          </Tip>
                        )}
                    {r.contacts.length > 0 && (
                      <span className="flex flex-wrap gap-1">
                        {letters.map((c) => (
                          <Tip key={c.i} label={t(`types.${c.type}`)}>
                            <span
                              aria-hidden
                              className={cn('rounded-[5px] px-1.5 text-[11px] leading-[18px] font-semibold', e.contact && c !== e.contact && 'opacity-35')}
                              style={{ background: `color-mix(in srgb, ${color(c.type)} 22%, transparent)`, boxShadow: `inset 2px 0 0 ${color(c.type)}` }}
                            >
                              {t(`short.${c.type}`)}
                            </span>
                          </Tip>
                        ))}
                        {r.contacts.length > LETTERS && (
                          <span aria-hidden className="rounded-[5px] bg-muted px-1.5 text-[11px] leading-[18px] font-semibold text-muted-foreground tabular-nums">
                            +{r.contacts.length - LETTERS + 1}
                          </span>
                        )}
                        {!e.contact && <span className="sr-only">{r.contacts.map((c) => t(`types.${c.type}`)).join(', ')}</span>}
                      </span>
                    )}
                  </button>
                </Tip>
              </li>
            );
          })}
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
