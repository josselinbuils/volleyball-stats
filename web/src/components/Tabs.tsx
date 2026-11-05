import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** A tab bar, the open tab underlined. */
export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (id: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_var(--border)]">
      {tabs.map(({ id, label: shown }) => (
        <button
          key={id}
          role="tab"
          type="button"
          aria-selected={value === id}
          onClick={() => onChange(id)}
          className={cn(
            'inline-flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-[15px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset',
            value === id ? 'border-primary font-semibold text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          {shown}
        </button>
      ))}
    </div>
  );
}
