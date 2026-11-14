import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { usePlayer } from '@/lib/player';
import { cn } from '@/lib/utils';

/** The player in the page; on a phone, once something plays out of its sight (`usePlayer().sheet`), in a sheet from the
 * bottom over the page. The same elements move there, the video playing on, and their place keeps its height: the page
 * stays where the viewer was. */
export function PlayerSheet({ title, className, children }: { title: string; className?: string; children: ReactNode }) {
  const { t } = useTranslation();
  const { sheet, closeSheet } = usePlayer();
  const place = useRef<HTMLDivElement>(null);
  const height = useRef(0);
  const closeButton = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    const box = place.current;
    if (!box) {
      return;
    }
    const observer = new ResizeObserver(() => {
      height.current = box.offsetHeight;
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);
  // Focus goes to "Fermer", then back to what played it; Escape closes.
  useEffect(() => {
    if (!sheet) {
      return;
    }
    const before = document.activeElement as HTMLElement | null;
    closeButton.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeSheet();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      before?.focus({ preventScroll: true });
    };
  }, [sheet, closeSheet]);

  return (
    <div ref={place} style={sheet ? { height: height.current } : undefined}>
      {sheet && <div aria-hidden className="fixed inset-0 z-40 touch-none bg-black/50 animate-in fade-in-0" onClick={closeSheet} />}
      <div
        role={sheet ? 'dialog' : undefined}
        aria-modal={sheet || undefined}
        aria-labelledby={sheet ? id : undefined}
        className={cn(
          sheet &&
            'fixed inset-x-0 bottom-0 z-50 max-h-[calc(100dvh-1.5rem)] overflow-y-auto overscroll-contain rounded-t-xl bg-card px-4 pb-4 shadow-lg animate-in slide-in-from-bottom duration-200 motion-reduce:animate-none',
        )}
      >
        {sheet && (
          <div className="sticky top-0 z-20 -mx-4 mb-1 flex items-center justify-between gap-3 bg-card px-4 py-3">
            <p id={id} className="truncate text-lg font-semibold">
              {title}
            </p>
            <Button ref={closeButton} variant="outline" size="lg" className="bg-card" onClick={closeSheet}>
              <X aria-hidden />
              {t('sheetClose')}
            </Button>
          </div>
        )}
        <div className={className}>{children}</div>
      </div>
    </div>
  );
}
