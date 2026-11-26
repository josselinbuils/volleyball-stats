import { ArrowRight, Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tip } from '@/components/Tip';
import { cn } from '@/lib/utils';
import { STEPS, type FirstState, type FirstStep } from './helpers/setup';

/** The guided first run on the list: the steps from the club to a shared match, those done ticked, only the next one
 * with its words and its button (`onStep`). */
export function FirstSteps({
  first,
  onStep,
  onHide,
  hiding,
  opening,
  reviewable,
}: {
  first: FirstState;
  onStep: (step: FirstStep) => void;
  onHide: () => void;
  hiding: boolean;
  /** The review opening for its step. */
  opening: boolean;
  /** A match to review is here. */
  reviewable: boolean;
}) {
  const { t } = useTranslation();
  const next = STEPS.find((s) => !first.done.includes(s));
  return (
    <Card className="gap-3 px-4 py-3.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg leading-snug font-semibold">{t('app.first.title')}</h2>
        <Tip label={t('app.first.hide')}>
          <Button variant="ghost" size="icon-sm" aria-label={t('app.first.hide')} busy={hiding} onClick={onHide}>
            <X aria-hidden />
          </Button>
        </Tip>
      </div>
      <ol className="grid gap-2.5">
        {STEPS.map((step, k) => {
          const done = first.done.includes(step);
          const current = step === next;
          return (
            <li key={step} className="flex items-start gap-3" aria-current={current ? 'step' : undefined}>
              <span
                className={cn(
                  'flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold',
                  done ? 'border-primary bg-primary text-primary-foreground' : current ? 'border-primary text-primary' : 'text-muted-foreground',
                )}
              >
                {done ? <Check aria-label={t('app.first.done')} className="size-3.5" /> : k + 1}
              </span>
              <div className="grid min-w-0 gap-1.5 pt-0.5">
                <span className={cn('leading-snug', current ? 'font-medium' : 'text-muted-foreground')}>{t(`app.first.${step}`)}</span>
                {current && (
                  <>
                    <p className="text-sm text-muted-foreground">{t(`app.first.${step}Text`)}</p>
                    {step !== 'analysis' && (step !== 'review' || reviewable) && (
                      <Button size="sm" className="w-fit" busy={step === 'review' && opening} onClick={() => onStep(step)}>
                        {t(step === 'review' ? 'app.first.openMatch' : 'app.first.open')}
                        <ArrowRight aria-hidden />
                      </Button>
                    )}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
