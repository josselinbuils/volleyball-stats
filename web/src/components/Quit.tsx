import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Power } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tip } from '@/components/Tip';

type Refusal = 'running' | 'busy' | 'failed';

/** The app stopped from its page (no terminal shows it): its window closed, else a screen saying it is. Refused while a
 * task runs or answers apply. `screens` shows the refusal or the closed app. */
export function useQuit() {
  const { t } = useTranslation();
  const [quitting, setQuitting] = useState(false);
  const [refused, setRefused] = useState<Refusal | null>(null);
  const [closed, setClosed] = useState(false);
  const quit = async () => {
    setQuitting(true);
    try {
      const response = await fetch('/app/quit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ app: true }) });
      if (!response.ok) {
        const { error } = (await response.json().catch(() => ({}))) as { error?: string };
        setRefused(error === 'running' || error === 'busy' ? error : 'failed');
        setQuitting(false);
        return;
      }
    } catch {
      setRefused('failed');
      setQuitting(false);
      return;
    }
    // A window the shortcut opened closes; one with a history may not.
    window.close();
    setClosed(true);
  };
  const screens = (
    <>
      {refused && (
        <Dialog open onOpenChange={(open) => !open && setRefused(null)}>
          <DialogContent showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>{t('app.quit.label')}</DialogTitle>
              <DialogDescription>{t(`app.quit.${refused}`)}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={() => setRefused(null)}>{t('app.quit.ok')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {closed &&
        createPortal(
          <div role="status" className="fixed inset-0 z-50 grid place-items-center bg-background p-4 text-muted-foreground">
            <p className="flex items-center gap-2">
              <Power aria-hidden className="size-4" />
              {t('app.quit.closed')}
            </p>
          </div>,
          document.body,
        )}
    </>
  );
  return { quitting, quit, screens };
}

/** Quitter, beside the theme and the language. */
export function QuitButton() {
  const { t } = useTranslation();
  const { quitting, quit, screens } = useQuit();
  return (
    <>
      <Tip label={t('app.quit.label')}>
        <Button variant="outline" size="icon-sm" className="bg-card" aria-label={t('app.quit.label')} busy={quitting} onClick={() => void quit()}>
          <Power aria-hidden className="size-3.5" />
        </Button>
      </Tip>
      {screens}
    </>
  );
}
