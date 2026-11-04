import { useState, type FormEvent } from 'react';
import { CloudUpload, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

/** The first upload of a match: with its video behind a password the owner picks, or without it. */
export function HostChoice({ onChoose, onCancel }: { onChoose: (body: { video: boolean; password?: string }) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const ready = password.trim() !== '';
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (ready) {
      onChoose({ video: true, password });
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('review.host')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <label className="grid gap-1 text-sm font-medium">
            {t('review.hostPassword')}
            <input
              type="text"
              autoComplete="off"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-9 rounded-md border border-input bg-transparent px-2.5 text-base font-normal shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </label>
          <div className="grid gap-2">
            <Button type="submit" disabled={!ready}>
              <Lock aria-hidden />
              {t('review.hostWithVideo')}
            </Button>
            <Button type="button" variant="outline" className="bg-card" onClick={() => onChoose({ video: false })}>
              <CloudUpload aria-hidden />
              {t('review.hostWithoutVideo')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
