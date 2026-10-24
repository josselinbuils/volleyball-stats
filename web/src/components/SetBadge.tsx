import { useTranslation } from 'react-i18next';
import { useSet } from '@/lib/sets';

/** The set the page is filtered on, beside a section's title. */
export function SetBadge() {
  const { t } = useTranslation();
  const { set } = useSet();
  if (set === null) {
    return null;
  }
  return <span className="ml-2 rounded-md bg-primary px-2 py-0.5 align-[2px] text-sm font-semibold text-primary-foreground">{t('set', { n: set })}</span>;
}
