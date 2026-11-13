import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/** Seconds as the bars say them: under a minute, minutes, hours and minutes. */
export function useDuration() {
  const { t } = useTranslation();
  return (s: number) =>
    s < 60 ? t('review.lessThanMinute') : s < 3600 ? t('review.minutes', { count: Math.round(s / 60) }) : t('app.hours', { h: Math.floor(s / 3600), m: Math.round((s % 3600) / 60) });
}

/** A long run's bar and its share done, what it does (`children`) with the share done of its step (`part`), then the
 * time left and when it ends, the time spent with `elapsed`, or that it takes longer than expected when `late`. Without
 * a share told, the bar follows the time spent and left; without either, it slides. */
export function JobProgress({
  label,
  fraction,
  part,
  left,
  elapsed,
  late,
  className,
  children,
}: {
  label: string;
  fraction: number | null;
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
        aria-valuenow={share == null ? undefined : Math.round(share * 100)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={share == null ? 'progress-slide h-full w-1/3 rounded-full bg-primary/70' : 'h-full bg-primary transition-[width] duration-300'}
          style={share == null ? undefined : { width: `${share * 100}%` }}
        />
      </div>
      {children && (
        <p className="m-0 text-sm">
          {children}
          {part != null && <span className="text-muted-foreground tabular-nums"> · {percent(part)}</span>}
        </p>
      )}
      {(share != null || time) && <p className="m-0 text-xs text-muted-foreground tabular-nums">{[share != null && t('app.done', { percent: percent(share) }), time].filter(Boolean).join(' · ')}</p>}
    </div>
  );
}
