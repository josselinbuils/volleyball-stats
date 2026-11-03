import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

type Tab = 'questions' | 'names' | 'match' | 'progress';

/** The review's steps, each saying only what is left to do. */
export function ReviewTabs({ tab, show, named, players, questions, reports }: { tab: Tab; show: (tab: Tab) => void; named: number; players: number; questions: number; reports: number }) {
  const { t } = useTranslation();
  const tabs: { id: Tab; label: string; left?: number | string; done?: boolean }[] = [
    { id: 'names', label: t('review.tabNames'), left: named < players ? `${named}/${players}` : undefined, done: named === players },
    { id: 'questions', label: t('review.tabQuestions'), left: questions || undefined },
    { id: 'match', label: t('review.tabMatch'), left: reports || undefined },
    { id: 'progress', label: t('review.tabProgress') },
  ];
  return (
    <div role="tablist" aria-label={t('review.tabs')} className="flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_var(--border)]">
      {tabs.map(({ id, label, left, done }) => (
        <button
          key={id}
          role="tab"
          type="button"
          aria-selected={tab === id}
          onClick={() => show(id)}
          className={cn(
            'inline-flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-[15px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset',
            tab === id ? 'border-primary font-semibold text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          {label}
          {done && <Check aria-hidden className="size-4 text-muted-foreground" />}
          {left !== undefined && <span className="rounded-full bg-muted px-1.5 text-xs font-medium text-foreground tabular-nums">{left}</span>}
        </button>
      ))}
    </div>
  );
}
