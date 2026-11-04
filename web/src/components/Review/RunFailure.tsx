import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { Failure } from '@/lib/review';

export function RunFailure({ failure: { step, error }, onClose }: { failure: Failure; onClose: () => void }) {
  const { t } = useTranslation();

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent showCloseButton={false} container={document.fullscreenElement}>
        <DialogHeader>
          <DialogTitle>{t('review.failed', { step: t(`review.step.${step}`).replace(/( \(.*\))?…$/, '') })}</DialogTitle>
        </DialogHeader>
        <p className="font-mono text-xs break-words text-muted-foreground">{error}</p>
        <Button onClick={onClose}>{t('review.failedClose')}</Button>
      </DialogContent>
    </Dialog>
  );
}
