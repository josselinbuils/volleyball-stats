import { useEffect, useState } from 'react';
import { TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { readBehind } from '@/lib/review';

const EVERY_MS = 10 * 60_000;

/** In the review: a notice while the code lacks commits of its remote, asked again now and then for the other machine's pushes. */
export function Behind() {
  const { t } = useTranslation();
  const [behind, setBehind] = useState(0);
  useEffect(() => {
    const read = () => void readBehind().then(setBehind);
    read();
    const timer = setInterval(read, EVERY_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    behind > 0 && (
      <Alert variant="warning">
        <TriangleAlert aria-hidden />
        <AlertDescription>{t('review.behind', { count: behind })}</AlertDescription>
      </Alert>
    )
  );
}
