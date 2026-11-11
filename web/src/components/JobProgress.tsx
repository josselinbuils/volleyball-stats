import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/** Seconds as the bars say them: under a minute, minutes, hours and minutes. */
export function useDuration() {
  const { t } = useTranslation();
  return (s: number) =>
    s < 60 ? t('review.lessThanMinute') : s < 3600 ? t('review.minutes', { count: Math.round(s / 60) }) : t('app.hours', { h: Math.floor(s / 3600), m: Math.round((s % 3600) / 60) });
}

/** A long run's bar (pulsing while its share is unknown), what it does (`children`), then the time left and when it
 * ends, the time spent with `elapsed`, or that it takes longer than expected when `late`. */
export function JobProgress({
  label,
  fraction,
  left,
  elapsed,
  late,
  className,
  children,
}: {
  label: string;
  fraction: number | null;
  left?: number | null;
  elapsed?: number;
  late?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const duration = useDuration();
  const end = left != null && new Date(Date.now() + left * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' });
  // Under a minute left, said as such, not "about".
  const soon = left != null && left < 60 ? 'soon' : undefined;
  const time =
    late && elapsed != null
      ? t('review.progressLate', { elapsed: duration(elapsed) })
      : left != null
        ? elapsed != null
          ? t('review.progressLeft', { left: duration(left), end, elapsed: duration(elapsed), context: soon })
          : t('app.left', { left: duration(left), end, context: soon })
        : null;
  return (
    <div className={cn('grid gap-1', className)}>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={fraction == null ? undefined : Math.round(fraction * 100)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={fraction == null ? 'h-full w-1/3 animate-pulse bg-primary/60' : 'h-full bg-primary transition-[width] duration-300'}
          style={fraction == null ? undefined : { width: `${fraction * 100}%` }}
        />
      </div>
      {children && <p className="m-0 text-sm">{children}</p>}
      {time && <p className="m-0 text-xs text-muted-foreground tabular-nums">{time}</p>}
    </div>
  );
}
