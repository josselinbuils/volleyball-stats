import { useEffect, useState, useSyncExternalStore } from 'react';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { onServerBusy, serverBusy } from '@/lib/review';

// A request answered faster than this feels instant: no indicator for it.
const DELAY_MS = 150;

/** A badge at the bottom of the screen while the review server works on what the user did, else the
 * `notice` of what was done. */
export function Status({ notice }: { notice: string | null }) {
  const { t } = useTranslation();
  const busy = useSyncExternalStore(onServerBusy, serverBusy);
  const [shown, setShown] = useState<typeof busy>(null);
  useEffect(() => {
    if (!busy) {
      setShown(null);
      return;
    }
    const timer = window.setTimeout(() => setShown(busy), DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [busy]);

  return (
    <div role="status" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center px-4">
      {(shown || notice) && (
        <span className="flex items-center gap-2 rounded-full bg-foreground px-3 py-1.5 text-sm text-background shadow-lg">
          {shown && <LoaderCircle aria-hidden className="size-4 animate-spin" />}
          {shown ? t(shown === 'saving' ? 'review.saving' : 'review.loading') : notice}
        </span>
      )}
    </div>
  );
}
