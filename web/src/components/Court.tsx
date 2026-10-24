import { useSyncExternalStore, type ComponentProps, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

// Phones: the court takes most of the width, the players standing far behind an end line spill
// over the edge.
const SMALL = '(max-width: 639px)';

function useSmall(): boolean {
  return useSyncExternalStore(
    (listener) => {
      const query = matchMedia(SMALL);
      query.addEventListener('change', listener);
      return () => query.removeEventListener('change', listener);
    },
    () => matchMedia(SMALL).matches,
  );
}

/** A top view of the court in court metres: x along the length, net at 0, y toward the camera,
 * which films from beyond the near sideline (bottom). `ends` names the halves (default: none),
 * `camera` marks the camera's side. */
export function Court({
  zones = false,
  ends,
  camera = true,
  className,
  children,
  ...props
}: { zones?: boolean; ends?: [ReactNode, ReactNode]; camera?: boolean } & ComponentProps<'svg'>) {
  const { t } = useTranslation();
  const small = useSmall();
  return (
    <div className={className}>
      <svg viewBox={small ? '-10.2 -6 20.4 12' : '-12.5 -6.5 25 13'} className="block h-auto w-full overflow-visible" {...props}>
        <rect x={-9} y={-4.5} width={18} height={9} className="fill-court" />
        {zones && [-1.5, 1.5].map((y) => <line key={y} x1={-9} x2={9} y1={y} y2={y} className="court-line opacity-50" strokeWidth={1} />)}
        <rect x={-9} y={-4.5} width={18} height={9} className="court-line" />
        {[-3, 3, 0].map((x) => (
          <line key={x} x1={x} x2={x} y1={-4.5} y2={4.5} className="court-line" />
        ))}
        <line x1={0} x2={0} y1={-5.25} y2={5.25} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {children}
      </svg>
      <div aria-hidden className="grid grid-cols-[1fr_auto_1fr] gap-2 px-[9%] text-xs text-muted-foreground max-sm:px-[3%]">
        <span className="truncate">{ends?.[0]}</span>
        <span>{camera && t('cameraSide')}</span>
        <span className="truncate text-right">{ends?.[1]}</span>
      </div>
    </div>
  );
}

export function Legend({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground', className)} {...props} />;
}
