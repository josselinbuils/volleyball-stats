import { useEffect, useState, type FormEvent } from 'react';
import { CloudUpload, LoaderCircle, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { PasswordField } from '@/components/PasswordField';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { VIDEO_MIN } from '@/lib/videoPassword';

/** What the first upload sends: the video, behind the videos' password (`password` when none is chosen yet), or no video. */
export type HostBody = { video: true; password?: string } | { video: false };

/** The first upload of a match: with its video behind the videos' password (chosen here for the first one), or without it. */
export function HostChoice({ onChoose, onCancel }: { onChoose: (body: HostBody) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  // Whether the videos' password is chosen; null while it loads.
  const [chosen, setChosen] = useState<boolean | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  useEffect(() => {
    void call<{ password: string | null }>('server/password/get', {}).then((r) => {
      if (r.ok) {
        setChosen(!!r.password);
      } else {
        setError(explain(t, r.error, 'error.loadFailed'));
      }
    });
  }, [t]);
  const ready = chosen === true || (chosen === false && password.trim().length >= VIDEO_MIN);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (ready) {
      onChoose(chosen ? { video: true } : { video: true, password });
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('review.host')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          {chosen === null && !error && (
            <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle aria-hidden className="size-4 animate-spin" />
              {t('passwords.loading')}
            </p>
          )}
          {chosen === false && <PasswordField label={t('passwords.title')} value={password} onChange={setPassword} min={VIDEO_MIN} generate autoFocus />}
          {error && <ErrorNote {...error} />}
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
