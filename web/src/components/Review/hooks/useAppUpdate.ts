import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Told } from '@/components/JobLine';
import type { AppState } from '@/components/Setup/helpers/setup';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';

// How often the review asks how the app's update goes.
const UPDATE_POLL_MS = 3000;

/** The app's update (learn.update): it may make this match again, so the page waits for it (`follow`, at once when
 * `updating`), then reloads on what it made; `busy` says it runs. */
export function useAppUpdate(updating: boolean, busy: (on: 'update' | null) => void) {
  const { t } = useTranslation();
  const [update, setUpdate] = useState<Told | null>(null);
  const [updateError, setUpdateError] = useState<Explained | null>(null);
  const follow = useCallback(() => {
    busy('update');
    setUpdateError(null);
    const check = async () => {
      const found = await call<AppState>('state');
      if (!found.ok) {
        return;
      }
      const job = found.learn.job;
      if (job?.running) {
        setUpdate(job);
        return;
      }
      window.clearInterval(timer);
      if (job?.failed) {
        setUpdate(null);
        busy(null);
        setUpdateError(explain(t, job.error));
        return;
      }
      location.reload();
    };
    const timer = window.setInterval(() => void check(), UPDATE_POLL_MS);
    void check();
  }, [t, busy]);
  useEffect(() => {
    if (updating) {
      follow();
    }
  }, [updating, follow]);
  return { update, updateError, setUpdateError, follow };
}
