import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { restarted } from '@/lib/openMatch';
import { post, type Claim } from '@/lib/review';

/** The match changed here and on another machine since this one's copy: the owner keeps one, the other stays saved. */
export function Elsewhere({ claim: { machine, at }, onKept }: { claim: Claim; onKept: () => void }) {
  const { t } = useTranslation();
  // The copy being kept: its button shows a loader, the other waits.
  const [working, setWorking] = useState<'take' | 'keep' | null>(null);
  const [failed, setFailed] = useState(false);
  const keep = async (which: 'take' | 'keep') => {
    setWorking(which);
    setFailed(false);
    try {
      await post(`sync/${which}`);
      if (which === 'take') {
        // The review restarts on the other machine's copy.
        await restarted();
      } else {
        onKept();
        setWorking(null);
      }
    } catch {
      setFailed(true);
      setWorking(null);
    }
  };

  return (
    <Dialog open>
      <DialogContent showCloseButton={false} container={document.fullscreenElement} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('sync.conflict', { machine })}</DialogTitle>
          <DialogDescription>{at ? t('sync.which', { machine, at }) : t('sync.whichNoTime')}</DialogDescription>
        </DialogHeader>
        {failed && <ErrorNote className="text-sm" />}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" busy={working === 'take'} disabled={!!working} onClick={() => void keep('take')}>
            {t('sync.theirs', { machine })}
          </Button>
          <Button busy={working === 'keep'} disabled={!!working} onClick={() => void keep('keep')}>
            {t('sync.mine')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
