import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Check, Copy, Eye, EyeOff, LoaderCircle, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { PasswordField } from '@/components/PasswordField';
import { Tip } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { keyLink, VIDEO_MIN } from '@/lib/videoPassword';
import { useRunning } from '@/hooks/useRunning';

// The "Copié" mark this long on a link's button.
const COPIED_MS = 2000;

/** The "Site" tab's card of the videos' password: shown on request and changed, then the links opening the videos without
 * it, to the list (`list`, its address) and to each match online with its video (`matches`). `busy` while an upload runs
 * (no change then), `onState` given the server's state after a change. */
export function VideoPassword({ matches, list, busy, onState }: { matches: { name: string; label: string; url: string }[]; list: string | null; busy: boolean; onState: (state: unknown) => void }) {
  const { t } = useTranslation();
  // undefined while it loads, null before it is chosen.
  const [password, setPassword] = useState<string | null | undefined | 'failed'>(undefined);
  const [key, setKey] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  // The password and its fingerprint together, the server's (a page on the local network cannot make it): the links
  // appear with it.
  const load = useCallback(async () => {
    const r = await call<{ password: string | null; key: string | null }>('server/password/get', {});
    if (!r.ok) {
      setPassword('failed');
      return;
    }
    setKey(r.key);
    setPassword(r.password);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(null), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

  if (password === undefined) {
    return (
      <p role="status" className="flex items-center gap-2 text-muted-foreground">
        <LoaderCircle aria-hidden className="size-4 animate-spin" />
        {t('passwords.loading')}
      </p>
    );
  }
  if (password === 'failed') {
    return (
      <ErrorNote
        text={t('error.loadFailed')}
        log
        action={
          <Button size="sm" variant="outline" className="bg-card" onClick={() => void load()}>
            {t('error.retry')}
          </Button>
        }
      />
    );
  }
  const links = [...(list ? [{ name: '', label: t('passwords.list'), url: list }] : []), ...matches];
  const copy = async (name: string, url: string) => {
    try {
      await navigator.clipboard.writeText(keyLink(url, key!));
      setCopied(name);
      setCopyFailed(false);
    } catch {
      setCopyFailed(true);
    }
  };

  return (
    <>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {password ? (
          <>
            <span className={`min-w-0 [overflow-wrap:anywhere] ${shown ? 'font-mono select-all' : ''}`}>{shown ? password : '••••••••'}</span>
            <Tip label={t(shown ? 'passwords.hide' : 'passwords.show')}>
              <Button variant="ghost" size="icon-sm" aria-label={t(shown ? 'passwords.hide' : 'passwords.show')} onClick={() => setShown((s) => !s)}>
                {shown ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
              </Button>
            </Tip>
          </>
        ) : (
          <span className="text-muted-foreground">{t('passwords.none')}</span>
        )}
        <Button variant="outline" className="ml-auto bg-card" disabled={busy} onClick={() => setEditing(true)}>
          <Pencil aria-hidden />
          {t(password ? 'passwords.change' : 'passwords.choose')}
        </Button>
      </div>
      {saved && (
        <p role="status" className="text-muted-foreground">
          {t('passwords.saved')}
        </p>
      )}
      {password && key && links.length > 0 && (
        <div className="grid gap-2">
          <h3 className="text-sm font-medium">{t('passwords.links')}</h3>
          <ul className="grid max-h-80 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm">
            {links.map((m) => {
              const done = copied === m.name;
              const label = t(done ? 'passwords.copied' : 'passwords.copy');
              return (
                <li key={m.name || '/'} className="flex min-h-11 min-w-0 items-center gap-3 py-1 pr-1 pl-3">
                  <span className={`min-w-0 flex-1 [overflow-wrap:anywhere] ${m.name ? '' : 'font-medium'}`}>{m.label}</span>
                  <Tip label={label}>
                    <Button variant="ghost" size="icon-sm" aria-label={label} onClick={() => void copy(m.name, m.url)}>
                      {done ? <Check aria-hidden /> : <Copy aria-hidden />}
                    </Button>
                  </Tip>
                </li>
              );
            })}
          </ul>
          <p role="status" className="sr-only">
            {copied !== null ? t('passwords.copied') : ''}
          </p>
          {copyFailed && <ErrorNote text={t('passwords.copyFailed')} />}
        </div>
      )}
      {editing && (
        <EditDialog
          current={password}
          onSaved={async (state) => {
            onState(state);
            await load();
            setEditing(false);
            setSaved(true);
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}

/** The videos' password chosen or changed: online at once for every match with its video. */
function EditDialog({ current, onSaved, onClose }: { current: string | null; onSaved: (state: unknown) => Promise<void>; onClose: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState(current ?? '');
  const [error, setError] = useState<Explained | null>(null);
  const [doing, run] = useRunning<'save'>();
  const ready = password.trim().length >= VIDEO_MIN && password !== current;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) {
      return;
    }
    void run('save', async () => {
      const r = await call('server/password', { password });
      if (!r.ok) {
        setError(explain(t, r.error));
        return;
      }
      await onSaved(r);
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !doing && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('passwords.title')}</DialogTitle>
          {current && <DialogDescription>{t('passwords.changeNote')}</DialogDescription>}
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <PasswordField label={t('passwords.password')} value={password} onChange={setPassword} min={VIDEO_MIN} generate autoFocus />
          {error && <ErrorNote {...error} />}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={!!doing} onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" busy={doing === 'save'} disabled={!ready}>
              {t('passwords.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
