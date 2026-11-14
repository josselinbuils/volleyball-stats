import type { ComponentProps, ReactNode } from 'react';
import { Tip } from '@/components/Tip';
import { cn } from '@/lib/utils';

/** A button of a video's control bar (the match page's, the review's): an icon or a short text, `label` its name and
 * tooltip (`tip` when the tooltip says more), lit while `pressed`; `light` on a light bar, else on black. */
export function VideoButton({
  label,
  tip,
  pressed,
  light = false,
  className,
  children,
  ...props
}: { label: string; tip?: ReactNode; pressed?: boolean; light?: boolean } & Omit<ComponentProps<'button'>, 'aria-label' | 'aria-pressed'>) {
  return (
    <Tip label={tip ?? label}>
      <button
        type="button"
        className={cn(
          'inline-flex h-9 min-w-9 shrink-0 items-center justify-center rounded-md text-sm font-medium tabular-nums outline-none focus-visible:ring-3 disabled:pointer-events-none disabled:opacity-40 max-sm:h-8 max-sm:min-w-8 [&_svg]:size-5',
          light ? 'hover:bg-foreground/10 focus-visible:ring-ring/50' : 'hover:bg-white/15 focus-visible:ring-white/70',
          pressed && (light ? 'bg-foreground/15' : 'bg-white/25'),
          className,
        )}
        aria-label={label}
        aria-pressed={pressed}
        {...props}
      >
        {children}
      </button>
    </Tip>
  );
}
