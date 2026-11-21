import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';

/** The review server's list while the app's script that shows it (app.js) loads, or its failure. */
export function ListLoading({ failed = false }: { failed?: boolean }) {
  const { t } = useTranslation();
  return (
    <main className="mx-auto grid w-full max-w-6xl justify-items-center px-4 pt-16 pb-16">
      {failed ? <ErrorNote text={t('error.loadFailed')} /> : <LoaderCircle role="status" aria-label={t('matches.loading')} className="size-6 animate-spin text-muted-foreground" />}
    </main>
  );
}
