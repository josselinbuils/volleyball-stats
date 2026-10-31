import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useFormat } from '@/lib/format';
import { isTouch } from '@/helpers/contacts';
import { match } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { rallyClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';

const BINS = ['0', '1', '2', '3', '4', '5', '6', '7+'];

/** Rallies by number of touches. */
export function Histogram() {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const { rallies } = useSet();
  const binned = BINS.map((_, k) => rallies.filter((r) => Math.min(r.contacts.filter(isTouch).length, BINS.length - 1) === k));
  const most = Math.max(1, ...binned.map((rs) => rs.length));

  return (
    <div className="text-xs text-muted-foreground tabular-nums">
      <div className="flex h-40 items-end gap-1.5 border-b border-court-line">
        {binned.map((rs, k) => {
          const touches = t('touchesK', { count: parseInt(BINS[k], 10), k: BINS[k] });
          const label = `${t('ralliesN', { count: rs.length })} · ${touches}`;
          const bar = (
            <button
              type="button"
              aria-label={label}
              disabled={!rs.length}
              onClick={() => play((tr) => tr('ralliesWith', { touches: tr('touchesK', { count: parseInt(BINS[k], 10), k: BINS[k] }) }), rallyClips(rs, match.duration))}
              className="group flex h-full min-w-0 flex-1 cursor-pointer flex-col items-center justify-end rounded-t-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-default"
            >
              {rs.length > 0 && <span className="mb-1 font-semibold text-foreground">{f.num(rs.length)}</span>}
              {/* The tallest bar leaves room for its count. */}
              <span
                className="block w-full max-w-7 rounded-t-[4px] bg-chart/75 transition-colors group-hover:group-enabled:bg-chart"
                style={{ height: `calc(${rs.length / most} * (100% - 1.5rem))` }}
              />
            </button>
          );
          return rs.length ? (
            <Tooltip key={k}>
              <TooltipTrigger asChild>{bar}</TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
          ) : (
            <span key={k} className="contents">
              {bar}
            </span>
          );
        })}
      </div>
      <div aria-hidden className="mt-1.5 flex gap-1.5">
        {BINS.map((k) => (
          <span key={k} className="flex-1 text-center">
            {k}
          </span>
        ))}
      </div>
      <p className="mt-1 text-center">{t('touchesPerRally')}</p>
    </div>
  );
}
