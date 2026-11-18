import { useEffect, useState, type FormEvent } from 'react';
import { CloudUpload, LoaderCircle, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { PasswordField } from '@/components/PasswordField';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { fingerprint, MASTER_MIN, seal, unlock, VIDEO_MIN, type Sealed } from '@/lib/vault';

/** What the first upload sends: the video behind a password (its fingerprint, and the password sealed by the master one for
 * the "Site" tab to show it), or no video. */
export type HostBody = { video: true; videoKey: string; sealed: Sealed } | { video: false };

/** The first upload of a match: with its video behind a password the owner picks, kept under the master password (chosen
 * here when none is yet), or without it. */
export function HostChoice({ onChoose, onCancel }: { onChoose: (body: HostBody) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [master, setMaster] = useState('');
  const [again, setAgain] = useState('');
  // The passwords already sealed, whose master password this one must be.
  const [kept, setKept] = useState<Sealed[] | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  const [sealing, setSealing] = useState(false);
  useEffect(() => {
    void call<{ sealed: Record<string, Sealed | null> }>('server/password/sealed', {}).then((r) => {
      if (r.ok) {
        setKept(Object.values(r.sealed).filter((s): s is Sealed => !!s));
      } else {
        setError(r.error === 'local' ? { text: t('passwords.local'), detail: null, log: false } : explain(t, r.error, 'error.loadFailed'));
      }
    });
  }, [t]);
  const fresh = kept !== null && !kept.length;
  const ready = kept !== null && password.trim().length >= VIDEO_MIN && master.trim().length >= MASTER_MIN && (!fresh || again === master);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) {
      return;
    }
    setSealing(true);
    try {
      const vault = await unlock(master, kept);
      if (!vault) {
        setError({ text: t('passwords.wrong'), detail: null, log: false });
        return;
      }
      onChoose({ video: true, videoKey: await fingerprint(password), sealed: await seal(vault, password) });
    } catch {
      setError(explain(t, null));
    } finally {
      setSealing(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && !sealing && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('review.host')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={(e) => void submit(e)} className="grid gap-4">
          {kept === null && !error ? (
            <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle aria-hidden className="size-4 animate-spin" />
              {t('passwords.loading')}
            </p>
          ) : (
            kept !== null && (
              <>
                <PasswordField label={t('review.hostPassword')} value={password} onChange={setPassword} min={VIDEO_MIN} generate autoFocus />
                <PasswordField label={t('passwords.master')} value={master} onChange={setMaster} min={MASTER_MIN} />
                {fresh && <PasswordField label={t('passwords.confirm')} value={again} onChange={setAgain} min={0} />}
                {fresh && again !== '' && again !== master && <p className="m-0 text-xs text-muted-foreground">{t('passwords.mismatch')}</p>}
              </>
            )
          )}
          {error && <ErrorNote {...error} />}
          <div className="grid gap-2">
            <Button type="submit" busy={sealing} disabled={!ready}>
              <Lock aria-hidden />
              {t('review.hostWithVideo')}
            </Button>
            <Button type="button" variant="outline" className="bg-card" disabled={sealing} onClick={() => onChoose({ video: false })}>
              <CloudUpload aria-hidden />
              {t('review.hostWithoutVideo')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
