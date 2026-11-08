import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { restarted } from '@/lib/openMatch';
import type { Claim } from '@/lib/review';

/** The match changed here and on another machine since this one's copy: the owner keeps one, the other stays saved. */
export function Elsewhere({ claim: { machine, at }, onKept }: { claim: Claim; onKept: () => void }) {
  const { t } = useTranslation();
  const [working, setWorking] = useState(false);
  const [failed, setFailed] = useState(false);
  const keep = async (which: 'take' | 'keep') => {
    setWorking(true);
    setFailed(false);
    try {
      const response = await fetch(`sync/${which}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok) {
        throw new Error(`${which}: ${response.status}`);
      }
      if (which === 'take') {
        // The review restarts on the other machine's copy.
        await restarted();
      } else {
        onKept();
        setWorking(false);
      }
    } catch {
      setFailed(true);
      setWorking(false);
    }
  };

  return (
    <Dialog open>
      <DialogContent showCloseButton={false} container={document.fullscreenElement} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('sync.conflict', { machine })}</DialogTitle>
          <DialogDescription>{at ? t('sync.which', { machine, at }) : t('sync.whichNoTime')}</DialogDescription>
        </DialogHeader>
        {failed && (
          <p role="alert" className="text-sm text-destructive">
            {t('sync.failed')}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" disabled={working} onClick={() => void keep('take')}>
            {working ? t('sync.working') : t('sync.theirs', { machine })}
          </Button>
          <Button disabled={working} onClick={() => void keep('keep')}>
            {working ? t('sync.working') : t('sync.mine')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
