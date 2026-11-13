import { useEffect, useState } from 'react';
import { RefreshCw, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { restarted } from '@/lib/openMatch';
import { readBehind } from '@/lib/review';

const EVERY_MS = 10 * 60_000;

/** In the review: a notice while the code lacks commits of its remote, asked again now and then for the other machine's
 * pushes, with the update: the code and its dependencies brought up to date, then the server restarted on them. */
export function Behind() {
  const { t } = useTranslation();
  const [behind, setBehind] = useState(0);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<Explained | null>(null);
  useEffect(() => {
    const read = () => void readBehind().then(setBehind);
    read();
    const timer = setInterval(read, EVERY_MS);
    return () => clearInterval(timer);
  }, []);
  const update = async () => {
    setUpdating(true);
    setError(null);
    const r = await call('update', {});
    if (!r.ok) {
      setError(explain(t, r.error, 'review.updateFailed'));
      setUpdating(false);
      return;
    }
    try {
      await restarted();
    } catch {
      // Not back after minutes.
      setError(explain(t, null, 'review.updateFailed'));
      setUpdating(false);
    }
  };

  return (
    behind > 0 && (
      <Alert variant="warning">
        <TriangleAlert aria-hidden />
        <AlertDescription className="grid gap-2">
          <span>{t('review.behind', { count: behind })}</span>
          <Button size="sm" variant="outline" className="w-fit bg-card" busy={updating} onClick={() => void update()}>
            <RefreshCw aria-hidden />
            {updating ? t('review.updating') : t('review.update')}
          </Button>
          {error && <ErrorNote {...error} />}
        </AlertDescription>
      </Alert>
    )
  );
}
