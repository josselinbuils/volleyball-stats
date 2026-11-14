import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress } from '@/components/JobProgress';
import type { Told } from '@/components/JobLine';
import { ask } from '@/components/ask';
import { Button } from '@/components/ui/button';
import { useRunning } from '@/hooks/useRunning';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';

/** Why a match waits for the update (review.due): answers it has not learned from, or other code or models. */
export type Due = 'answers' | 'rules';

/** The update (app.learn_state): the matches waiting for it and why, and its job. */
export type LearnState = { due: { name: string; why: Due }[]; job: Told | null };

/** Asks before the update of `count` matches, then starts it: null once started, else why it did not. */
export async function startUpdate(t: TFunction, count: number): Promise<Explained | null | 'cancelled'> {
  if (!(await ask({ title: t('update.confirmTitle', { count }), text: t('update.confirm'), confirm: t('update.start') }))) {
    return 'cancelled';
  }
  const started = await call('learn', {});
  return started.ok ? null : explain(t, started.error);
}

/** The update running: its stage (the training, the nth match of how many, the play model's) and the time left. */
export function UpdateProgress({ job, className }: { job: Told; className?: string }) {
  const { t } = useTranslation();
  return (
    <JobProgress label={t('update.running')} fraction={job.progress ?? null} part={job.part} left={job.left} elapsed={job.elapsed} className={className}>
      {job.stage ? t(`update.stage.${job.stage}`, { n: job.n, of: job.of, defaultValue: t('update.running') }) : t('update.running')}
    </JobProgress>
  );
}

/** On the list of the matches: how many wait for the update and the button starting it, the update while it runs, or
 * why it failed. Nothing while every match is up to date. */
export function UpdateLine({ learn, onChange }: { learn: LearnState; onChange: () => void }) {
  const { t } = useTranslation();
  const [starting, run] = useRunning();
  const [startError, setStartError] = useState<Explained | null>(null);
  const failed = learn.job?.failed && !learn.job.running ? explain(t, learn.job.error) : null;
  const count = learn.due.length;
  if (learn.job?.running) {
    return <UpdateProgress job={learn.job} className="px-1" />;
  }
  if (!count) {
    return null;
  }
  return (
    <div className="grid gap-2 rounded-lg border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <span className="font-medium">{t('update.due', { count })}</span>
        <Button
          variant="outline"
          className="bg-card"
          busy={!!starting}
          onClick={() =>
            void run('learn', async () => {
              const result = await startUpdate(t, count);
              if (result !== 'cancelled') {
                setStartError(result);
                onChange();
              }
            })
          }
        >
          <RefreshCw aria-hidden />
          {t('update.start')}
        </Button>
      </div>
      {(startError ?? failed) && <ErrorNote {...(startError ?? failed)!} />}
    </div>
  );
}
