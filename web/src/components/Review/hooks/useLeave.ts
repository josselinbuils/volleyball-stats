import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ask } from '@/components/ask';

/** Leaving with `unsaved` rallies (another tab, a reload, the window closed) asks first: `mayLeave` asks, `leaving` holds
 * that losing them was agreed to, until the page stays after all. */
export function useLeave(unsaved: number) {
  const { t } = useTranslation();
  const leaving = useRef(false);
  const mayLeave = async () => {
    if (unsaved && !(await ask({ title: t('review.unsaved'), confirm: t('review.unsavedLeave'), danger: true }))) {
      return false;
    }
    leaving.current = true;
    return true;
  };
  useEffect(() => {
    if (!unsaved) {
      return;
    }
    const onLeave = (event: BeforeUnloadEvent) => {
      if (!leaving.current) {
        event.preventDefault();
      }
    };
    window.addEventListener('beforeunload', onLeave);
    return () => window.removeEventListener('beforeunload', onLeave);
  }, [unsaved]);
  return { mayLeave, leaving };
}
