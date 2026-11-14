import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tabs } from '@/components/Tabs';

type Tab = 'questions' | 'names' | 'match';

/** The review's steps, each saying only what is left to do. */
export function ReviewTabs({
  tab,
  show,
  named,
  players,
  questions,
  reports,
  matchDone,
}: {
  tab: Tab;
  show: (tab: Tab) => void;
  named: number;
  players: number;
  questions: number;
  reports: number;
  matchDone: boolean;
}) {
  const { t } = useTranslation();
  const tabs: { id: Tab; label: string; left?: number | string; done?: boolean }[] = [
    { id: 'names', label: t('review.tabNames'), left: named < players ? `${named}/${players}` : undefined, done: named === players },
    { id: 'questions', label: t('review.tabQuestions'), left: questions || undefined, done: !questions },
    { id: 'match', label: t('review.tabMatch'), left: reports || undefined, done: matchDone },
  ];
  return (
    <Tabs
      label={t('review.tabs')}
      value={tab}
      onChange={show}
      tabs={tabs.map(({ id, label, left, done }) => ({
        id,
        label: (
          <>
            {label}
            {done && <Check aria-hidden className="size-4 text-muted-foreground" />}
            {left !== undefined && <span className="rounded-full bg-muted px-1.5 text-xs font-medium text-foreground tabular-nums">{left}</span>}
          </>
        ),
      }))}
    />
  );
}
