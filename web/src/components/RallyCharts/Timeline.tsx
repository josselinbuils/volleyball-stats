import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { clock, useFormat } from '@/lib/format';
import { match, rallies } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { rallyAt, rallyClips } from '@/lib/playlist';

const longest = Math.max(1, ...rallies.map((r) => r.end - r.start));
const top = Math.ceil(longest);
const minutes = match.duration / 60;
const step = [1, 2, 5, 10, 15, 30, 60].find((s) => minutes / s <= 6) ?? 120;
const ticks = Array.from({ length: Math.floor(minutes / step) + 1 }, (_, k) => k * step * 60);

/** The rallies along the video, as tall as they are long, with the playhead. */
export function Timeline() {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const [hover, setHover] = useState(-1);
  const current = useVideoTime((time) => rallyAt(rallies, time)?.i ?? -1);
  // ponytail: the playhead moves in quarter seconds, enough at this scale and 4 renders a second.
  const head = useVideoTime((time) => Math.round(time * 4) / 4);
  const pct = (time: number) => `${(100 * time) / match.duration}%`;

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-xs text-muted-foreground tabular-nums">
      <div aria-hidden className="relative h-40 w-9">
        {[top, top / 2, 0].map((s) => (
          <span key={s} className="absolute right-0 translate-y-1/2" style={{ bottom: `${(100 * s) / top}%` }}>
            {`${f.num(s)}\u00a0s`}
          </span>
        ))}
      </div>
      <div className="relative h-40 border-b border-court-line">
        {[0.5, 1].map((k) => (
          <div key={k} aria-hidden className="absolute inset-x-0 border-t border-dashed border-border" style={{ bottom: `${100 * k}%` }} />
        ))}
        {rallies.map((r) => {
          const label = `${t('rally', { n: r.i + 1 })} · ${clock(r.start)} · ${f.secs(r.end - r.start)} · ${t('touchesN', { count: r.contacts.length })}`;
          return (
            <Fragment key={r.i}>
              <div
                aria-hidden
                className={cn('pointer-events-none absolute bottom-0 min-w-1 rounded-t-[3px] bg-chart/75 transition-colors', r.i === hover || r.i === current ? 'bg-chart' : '')}
                style={{ left: pct(r.start), width: pct(r.end - r.start), height: `${Math.max(4, (100 * (r.end - r.start)) / top)}%` }}
              />
              {/* A full-height hit area at least 12 px wide. Pointer only: the rally cards are the
                  keyboard path to the same clips. */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    aria-hidden
                    onClick={() => play((tr) => tr('rallies'), rallyClips(rallies, match.duration), r.i)}
                    onPointerEnter={() => setHover(r.i)}
                    onPointerLeave={() => setHover(-1)}
                    className="absolute inset-y-0 -translate-x-1/2 cursor-pointer"
                    style={{ left: pct((r.start + r.end) / 2), width: `max(12px, ${pct(r.end - r.start)})` }}
                  />
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            </Fragment>
          );
        })}
        <div aria-hidden className="pointer-events-none absolute top-0 -bottom-1.5 w-px bg-foreground" style={{ left: pct(head) }} />
      </div>
      <div />
      <div aria-hidden className="relative h-6">
        {ticks.map((s) => {
          const x = s / match.duration;
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
