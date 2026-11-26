import { useEffect, useState } from 'react';
import { Check, CircleOff, HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import type { FirstState } from '@/components/Setup/helpers/setup';

/** The review's first open, before any review was applied: its three tabs in a line each, a question as an example. */
export function ReviewIntro() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    void call<FirstState>('first').then((r) => setOpen(r.ok && !r.review_intro));
  }, []);
  const close = () => {
    setOpen(false);
    // Unsaved, it shows again next time: nothing lost.
    void call('first', { seen: 'review_intro' });
  };
  const tabs = [
    ['tabNames', 'names'],
    ['tabQuestions', 'questions'],
    ['tabMatch', 'match'],
  ] as const;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('review.welcome.title')}</DialogTitle>
        </DialogHeader>
        <ol className="grid gap-3">
          {tabs.map(([tab, text]) => (
            <li key={tab} className="grid gap-1">
              <span className="font-medium">{t(`review.${tab}`)}</span>
              <span className="text-muted-foreground">{t(`review.welcome.${text}`)}</span>
              {text === 'questions' && (
                <div className="mt-1 grid gap-2 rounded-lg border bg-muted/40 p-3">
                  <p className="text-sm font-semibold">{t('review.touchQuestion')}</p>
                  <div aria-hidden className="grid gap-1.5 text-sm">
                    {[
                      [Check, t('review.touchProposed', { name: t('review.welcome.name') })],
                      [CircleOff, t('review.nobody')],
                      [HelpCircle, t('review.skip')],
                    ].map(([Icon, label]) => (
                      <span key={label as string} className="inline-flex items-center gap-2 rounded-md border bg-card px-2.5 py-1.5">
                        <Icon className="size-4" />
                        {label as string}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ol>
        <p className="text-muted-foreground">{t('review.welcome.apply')}</p>
        <Button className="w-fit" onClick={close}>
          {t('review.welcome.start')}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
