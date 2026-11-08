import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { restarted } from '@/lib/openMatch';
import type { Claim } from '@/lib/review';

/** The match held by another machine, or newer on the server: nothing to do here until it is taken. */
export function Elsewhere({ claim: { machine, at, changed } }: { claim: Claim }) {
  const { t } = useTranslation();
  const [taking, setTaking] = useState(false);
  const [failed, setFailed] = useState(false);
  const take = async () => {
    setTaking(true);
    setFailed(false);
    try {
      const response = await fetch('sync/take', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok) {
        throw new Error(`take: ${response.status}`);
      }
      await restarted();
    } catch {
      setFailed(true);
      setTaking(false);
    }
  };

  return (
    <Dialog open>
      <DialogContent showCloseButton={false} container={document.fullscreenElement} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('sync.elsewhere', { machine })}</DialogTitle>
          <DialogDescription>{[at && t('sync.copy', { at }), changed && t('sync.aside')].filter(Boolean).join(' ')}</DialogDescription>
        </DialogHeader>
        {failed && (
          <p role="alert" className="text-sm text-destructive">
            {t('sync.failed')}
          </p>
        )}
        <Button disabled={taking} onClick={() => void take()}>
          {taking ? t('sync.taking') : t('sync.take')}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
