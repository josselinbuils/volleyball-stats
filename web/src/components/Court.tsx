import type { ComponentProps, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/** A top view of the court in court metres: x along the length, net at 0, y toward the camera,
 * which films from beyond the near sideline (bottom). `ends` names the halves (default: left and
 * right), `camera` marks the camera's side. */
export function Court({
  zones = false,
  ends,
  camera = true,
  className,
  children,
  ...props
}: { zones?: boolean; ends?: [ReactNode, ReactNode]; camera?: boolean } & ComponentProps<'svg'>) {
  const { t } = useTranslation();
  return (
    <div className={className}>
      <svg viewBox="-12.5 -6.5 25 13" className="block h-auto w-full overflow-visible" {...props}>
        <rect x={-9} y={-4.5} width={18} height={9} className="fill-court" />
        {zones && [-1.5, 1.5].map((y) => <line key={y} x1={-9} x2={9} y1={y} y2={y} className="court-line opacity-50" strokeWidth={1} />)}
        <rect x={-9} y={-4.5} width={18} height={9} className="court-line" />
        {[-3, 3, 0].map((x) => (
          <line key={x} x1={x} x2={x} y1={-4.5} y2={4.5} className="court-line" />
        ))}
        <line x1={0} x2={0} y1={-5.25} y2={5.25} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {children}
      </svg>
      <div aria-hidden className="grid grid-cols-[1fr_auto_1fr] gap-2 px-[9%] text-xs text-muted-foreground">
        <span className="truncate">{ends?.[0] ?? t('leftEnd')}</span>
        <span>{camera && t('cameraSide')}</span>
        <span className="truncate text-right">{ends?.[1] ?? t('rightEnd')}</span>
      </div>
    </div>
  );
}

export function Legend({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground', className)} {...props} />;
}
