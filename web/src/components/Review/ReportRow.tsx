import { useTranslation } from 'react-i18next';
import { Check, Flag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clock, useFormat } from '@/lib/format';
import type { Question } from '@/lib/review';

/** A rally's reports in its list: what each said, the moment to replay, and marking them handled. */
export function ReportRow({ question, onPlay, onHandled }: { question: Question; onPlay: (time: number) => void; onHandled: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const at = question.reports?.[0]?.time ?? question.clip.start;
  return (
    <li className="grid grid-cols-[minmax(0,1fr)] gap-1.5 rounded-md border border-l-4 border-primary bg-primary/5 p-1.5 text-sm">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          title={t('review.reportGo')}
          aria-label={`${t('review.reportGo')} ${clock(at)}`}
          onClick={() => onPlay(at)}
          className="flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 tabular-nums outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <Flag aria-hidden className="size-3.5 text-primary" />
          {clock(at)}
        </button>
        <Button variant="outline" size="xs" className="ml-auto bg-card" title={t('review.reportHandledNote')} onClick={onHandled}>
          <Check aria-hidden />
          {t('review.reportHandled')}
        </Button>
      </div>
      {question.reports?.map((r, k) => (
        <p key={k} className="m-0 px-1.5">
          {r.kind?.startsWith('auto.') && <span className="mr-1.5 rounded-sm bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t('review.autoReport')}</span>}
          <span className="font-medium">{t(`feedback.kinds.${r.kind}`, { defaultValue: r.kind ?? '' })}</span>
          {r.shown && <span className="text-muted-foreground">{` · ${r.shown}`}</span>}
          {r.comment && <span>{` · « ${r.comment} »`}</span>}
          {r.received && <span className="text-muted-foreground">{` · ${t('review.reportReceived', { when: f.when(r.received) })}`}</span>}
        </p>
      ))}
    </li>
  );
}
