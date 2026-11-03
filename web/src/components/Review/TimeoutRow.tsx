import { useTranslation } from 'react-i18next';
import { Play, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, match, teamColor, teamRing } from '@/lib/match';
import type { Timeout, TimeoutChange } from '@/lib/review';

/** A timeout among the rallies: its team to pick, removed if it is none. */
export function TimeoutRow({
  timeout,
  current,
  onPlay,
  onChange,
}: {
  timeout: Timeout;
  /** The video is in it. */
  current: boolean;
  onPlay: (time: number) => void;
  onChange: (change: TimeoutChange) => void;
}) {
  const { t } = useTranslation();
  const { start, end, team } = timeout;
  const time = start / match.fps;
  return (
    <li data-key={`o${start}`} className={cn('grid grid-cols-[minmax(0,1fr)] gap-1.5 rounded-md border border-dashed bg-card p-1.5 transition-colors', current && 'border-muted-foreground bg-muted')}>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          title={t('review.reportPlay')}
          aria-label={`${t('review.reportPlay')} ${clock(time)}`}
          onClick={() => onPlay(time)}
          className="flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-sm tabular-nums outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <Play aria-hidden className="size-3.5 fill-current" />
          {clock(time)}
        </button>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{t('review.timeout')}</span>
        <Button variant="ghost" size="icon-sm" title={t('review.timeoutRemove')} aria-label={t('review.timeoutRemove')} onClick={() => onChange({ start, end, removed: true })}>
          <X aria-hidden />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {GROUPS.map((g) => (
          <Button
            key={g}
            variant={team === g ? 'secondary' : 'outline'}
            size="sm"
            className={cn('flex-1', team === g ? 'border-muted-foreground' : 'bg-card')}
            aria-pressed={team === g}
            onClick={() => onChange({ start, end, team: team === g ? null : g })}
          >
            <Swatch color={teamColor(g)} ring={teamRing(g)} />
            {groupName(t, g)}
          </Button>
        ))}
      </div>
    </li>
  );
}
