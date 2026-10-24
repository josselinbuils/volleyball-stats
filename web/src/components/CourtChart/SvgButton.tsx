import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

/** An SVG mark acting as a button: focusable, named by its title, Enter and Space click it. */
export function SvgButton({ label, onActivate, className, children, ...props }: { label: string; onActivate: () => void } & ComponentProps<'g'>) {
  return (
    <g
      role="button"
      tabIndex={0}
      className={cn('svg-button', className)}
      onClick={onActivate}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onActivate();
        }
      }}
      {...props}
    >
      <title>{label}</title>
      {children}
    </g>
  );
}
