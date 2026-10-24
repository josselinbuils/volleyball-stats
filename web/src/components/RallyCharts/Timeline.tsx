import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { clock, useFormat } from '@/lib/format';
import { match, sets } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { rallyAt, rallyClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { setBreaks, span, ticks } from '@/components/RallyCharts/helpers/timeline';

/** The rallies along the video, or along the picked set, as tall as they are long, with the playhead
 * and the set breaks. */
export function Timeline() {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const { set, rallies } = useSet();
  const [hover, setHover] = useState(-1);
  const current = useVideoTime((time) => rallyAt(rallies, time)?.i ?? -1);
  // ponytail: the playhead moves in quarter seconds, enough at this scale and 4 renders a second.
  const head = useVideoTime((time) => Math.round(time * 4) / 4);
  const [from, to] = set === null ? [0, match.duration] : span(rallies, match.duration);
  const top = Math.ceil(Math.max(1, ...rallies.map((r) => r.end - r.start)));
  const pct = (time: number) => `${(100 * (time - from)) / (to - from)}%`;
  const width = (seconds: number) => `${(100 * seconds) / (to - from)}%`;
  const breaks = set === null && sets.length > 1 ? setBreaks(rallies) : [];
  const playAt = (k: number) => play((tr) => (set === null ? tr('rallies') : tr('set', { n: set })), rallyClips(rallies, match.duration), k);

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-xs text-muted-foreground tabular-nums">
      <div aria-hidden className="relative h-40 w-9">
        {[top, top / 2, 0].map((s) => (
          <span key={s} className="absolute right-0 translate-y-1/2" style={{ bottom: `${(100 * s) / top}%` }}>
            {`${f.num(s)} s`}
          </span>
        ))}
      </div>
      <div className="relative h-40 border-b border-court-line">
        {[0.5, 1].map((k) => (
          <div key={k} aria-hidden className="absolute inset-x-0 border-t border-dashed border-border" style={{ bottom: `${100 * k}%` }} />
        ))}
        {breaks.map(({ time, set: n }) => (
          <div key={n} aria-hidden className="absolute inset-y-0 border-l-2 border-dashed border-foreground/40" style={{ left: pct(time) }}>
            <span className="absolute -top-0.5 left-1 font-semibold whitespace-nowrap text-foreground">{t('set', { n })}</span>
          </div>
        ))}
        {rallies.map((r, k) => {
          const label = `${t('rally', { n: r.i + 1 })} · ${clock(r.start)} · ${f.secs(r.end - r.start)} · ${t('touchesN', { count: r.contacts.length })}`;
          return (
            <Fragment key={r.i}>
              <div
                aria-hidden
                className={cn('pointer-events-none absolute bottom-0 min-w-1 rounded-t-[3px] bg-chart/75 transition-colors', r.i === hover || r.i === current ? 'bg-chart' : '')}
                style={{ left: pct(r.start), width: width(r.end - r.start), height: `${Math.max(4, (100 * (r.end - r.start)) / top)}%` }}
              />
              {/* A full-height hit area at least 12 px wide, a button for the keyboard too. */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label={`${label} · ${t('watchRally')}`}
                    onClick={() => playAt(k)}
                    onPointerEnter={() => setHover(r.i)}
                    onPointerLeave={() => setHover(-1)}
                    onFocus={() => setHover(r.i)}
                    onBlur={() => setHover(-1)}
                    className="absolute inset-y-0 -translate-x-1/2 cursor-pointer rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/60"
                    style={{ left: pct((r.start + r.end) / 2), width: `max(12px, ${width(r.end - r.start)})` }}
                  />
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            </Fragment>
          );
        })}
        {head >= from && head <= to && <div aria-hidden className="pointer-events-none absolute top-0 -bottom-1.5 w-px bg-foreground" style={{ left: pct(head) }} />}
      </div>
      <div />
      <div aria-hidden className="relative h-6">
        {ticks(from, to).map((s) => {
          const x = (s - from) / (to - from);
          return (
            <span key={s} className={cn('absolute top-1.5 whitespace-nowrap', x > 0 && '-translate-x-1/2', x > 0.95 && '-translate-x-full')} style={{ left: `${100 * x}%` }}>
              {clock(s)}
            </span>
          );
        })}
      </div>
    </div>
  );
}
