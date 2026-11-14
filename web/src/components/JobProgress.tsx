import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/** Seconds as the bars say them: under a minute, minutes, hours and minutes. */
export function useDuration() {
  const { t } = useTranslation();
  return (s: number) =>
    s < 60 ? t('review.lessThanMinute') : s < 3600 ? t('review.minutes', { count: Math.round(s / 60) }) : t('app.hours', { h: Math.floor(s / 3600), m: Math.round((s % 3600) / 60) });
}

/** Under this many seconds in all, a run says only the time left: no end time, no time spent. */
const SHORT = 600;

/** A long run's bar: what it does (`children`) with its share done beside, then below its step (`step`, "this step"
 * when only its share `part` is told) and the time left, when it ends and the time spent with `elapsed` (only the time
 * left for a short run), or that it takes longer than expected when `late`. Without a share told, the bar follows the
 * time spent and left; without either, it slides. */
export function JobProgress({
  label,
  fraction,
  step,
  part,
  left,
  elapsed,
  late,
  className,
  children,
}: {
  label: string;
  fraction: number | null;
  step?: string;
  part?: number | null;
  left?: number | null;
  elapsed?: number;
  late?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const duration = useDuration();
  const percent = (x: number) => new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 0 }).format(Math.min(0.99, Math.max(0, x)));
  const share = fraction ?? (left != null && elapsed != null ? Math.min(0.99, elapsed / Math.max(1, elapsed + left)) : null);
  const end = left != null && new Date(Date.now() + left * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' });
  const short = (elapsed ?? 0) + (left ?? 0) < SHORT;
  // Under a minute left, said as such, not "about".
  const soon = left != null && left < 60 ? 'soon' : undefined;
  const time =
    late && elapsed != null
      ? t('review.progressLate', { elapsed: duration(elapsed), context: short ? 'short' : undefined })
      : left != null
        ? short
          ? t('app.leftOnly', { left: duration(left), context: soon })
          : elapsed != null
            ? t('review.progressLeft', { left: duration(left), end, elapsed: duration(elapsed), context: soon })
            : t('app.left', { left: duration(left), end, context: soon })
        : null;
  const where = part != null ? t('app.stepDone', { step: step ?? t('app.thisStep'), percent: percent(part) }) : step;
  const below = [where, time].filter(Boolean).join(' · ');
  return (
    <div className={cn('grid gap-1', className)}>
      {(children || share != null) && (
        <div className="flex items-baseline justify-between gap-3 text-sm">
          <p className="m-0">{children}</p>
          {share != null && <span className="shrink-0 font-medium tabular-nums">{percent(share)}</span>}
        </div>
      )}
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={share == null ? undefined : Math.round(share * 100)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={share == null ? 'progress-slide h-full w-1/3 rounded-full bg-primary/70' : 'h-full bg-primary transition-[width] duration-300'}
          style={share == null ? undefined : { width: `${share * 100}%` }}
        />
      </div>
      {below && <p className="m-0 text-xs text-muted-foreground tabular-nums">{below}</p>}
    </div>
  );
}
