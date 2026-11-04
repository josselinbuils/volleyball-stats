import { Scissors, UserCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { clock } from '@/lib/format';

/** An answer `chosen` on a piece earlier answers give to the other of `names`: the new answer replaces
 * them on the whole piece, or the piece shows both and is cut at `cutAt`. */
export function PieceConflict({
  names,
  chosen,
  cutAt,
  onReplace,
  onCut,
  onCancel,
}: {
  names: string[];
  chosen: string | null;
  cutAt: number;
  onReplace: () => void;
  onCut: () => void;
  onCancel: () => void;
}) {
  const { t, i18n } = useTranslation();
  const list = new Intl.ListFormat(i18n.language, { type: 'conjunction' });
  const earlier = list.format(names.filter((n) => n !== chosen));

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent showCloseButton={false} container={document.fullscreenElement}>
        <DialogHeader>
          <DialogTitle>{t('review.pieceConflict', { name: earlier })}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-2">
          <Button onClick={onReplace}>
            <UserCheck aria-hidden />
            {t('review.pieceConflictReplace', { name: chosen })}
          </Button>
          <Button variant="outline" onClick={onCut}>
            <Scissors aria-hidden />
            {t('review.pieceConflictCut', { time: clock(cutAt) })}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            {t('review.pieceConflictCancel')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
