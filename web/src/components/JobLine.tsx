import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress } from '@/components/JobProgress';
import { explain } from '@/lib/errors';
import { useFormat } from '@/lib/format';
import type { Job } from '@/components/Setup/helpers/setup';

/** A job of the Site tab, with its stage ("match": the `n`th of `of`) and the seconds spent and left while it runs. */
export type Told = Job & { n?: number | null; of?: number | null; elapsed?: number; left?: number | null };

/** A job's last run: running (its bar, what it does and the time left), failed with its reason, or done and when
 * (unless `quiet`: the card already says it). */
export function JobLine({ job, running, quiet }: { job: Told | null; running: string; quiet?: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  if (!job || (quiet && !job.running && !job.failed)) {
    return null;
  }
  if (job.running) {
    return (
      <JobProgress label={running} fraction={job.progress ?? null} part={job.part} left={job.left} elapsed={job.elapsed}>
        {job.stage ? t(`server.stage.${job.stage}`, { n: job.n, of: job.of, defaultValue: running }) : running}
      </JobProgress>
    );
  }
  if (job.failed) {
    return <ErrorNote {...explain(t, job.error)} />;
  }
  return <p className="text-muted-foreground">{t('server.done', { at: f.when(new Date((job.ended ?? job.started) * 1000).toISOString()) })}</p>;
}
