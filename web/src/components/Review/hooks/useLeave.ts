import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ask } from '@/components/ask';

/** Leaving (another tab, a reload, the window closed) saves what waits first (`flush`: whether all went): `mayLeave` asks
 * only when that failed, `leaving` holds that losing it was agreed to, until the page stays after all. `waiting`: corrections
 * not saved yet, a reload or a closed window asked about. */
export function useLeave(flush: () => Promise<boolean>, waiting: boolean) {
  const { t } = useTranslation();
  const leaving = useRef(false);
  const flushNow = useRef(flush);
  flushNow.current = flush;
  const mayLeave = async () => {
    if (!(await flush()) && !(await ask({ title: t('review.unsaved'), confirm: t('review.unsavedLeave'), danger: true }))) {
      return false;
    }
    leaving.current = true;
    return true;
  };
  useEffect(() => {
    if (!waiting) {
      return;
    }
    const onLeave = (event: BeforeUnloadEvent) => {
      if (!leaving.current) {
        void flushNow.current();
        event.preventDefault();
      }
    };
    window.addEventListener('beforeunload', onLeave);
    return () => window.removeEventListener('beforeunload', onLeave);
  }, [waiting]);
  return { mayLeave, leaving };
}
