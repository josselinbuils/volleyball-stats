import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { LoaderCircle, Lock, LockOpen, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { ask } from '@/components/ask';
import { ErrorNote } from '@/components/ErrorNote';
import { PasswordField } from '@/components/PasswordField';
import { Tip } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { fingerprint, MASTER_MIN, open, seal, unlock, VIDEO_MIN, type Sealed, type Vault } from '@/lib/vault';
import { useRunning } from '@/hooks/useRunning';

// Unlocked this long at most: the passwords hidden again after it.
const UNLOCKED_MS = 5 * 60_000;

/** A refusal in words: "local" says where the passwords are seen. */
function refused(t: TFunction, error: string | undefined): Explained {
  return error === 'local' ? { text: t('passwords.local'), detail: null, log: false } : explain(t, error);
}

/** The "Site" tab's card of the videos' passwords, for the matches online with the video (`matches`, named by `label`):
 * hidden until the master password unlocks them, then shown and changed one by one or for all. `busy` while an upload
 * runs (no change then), `onState` given the server's state after a change. Only on the app's own computer (`here`). */
export function VideoPasswords({ matches, here, busy, onState }: { matches: { name: string; label: string }[]; here: boolean; busy: boolean; onState: (state: unknown) => void }) {
  const { t } = useTranslation();
  // Every match's with the video, online or not (null: only its fingerprint is known).
  const [sealed, setSealed] = useState<Record<string, Sealed | null> | null | 'failed'>(null);
  const [vault, setVault] = useState<Vault | null>(null);
  const [opened, setOpened] = useState<Record<string, string | null>>({});
  const [asking, setAsking] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const load = useCallback(async () => {
    const r = await call<{ sealed: Record<string, Sealed | null> }>('server/password/sealed', {});
    setSealed(r.ok ? r.sealed : 'failed');
    return r.ok ? r.sealed : null;
  }, []);
  useEffect(() => {
    if (here) {
      void load();
    }
  }, [here, load]);
  const lock = useCallback(() => {
    setVault(null);
    setOpened({});
    setEditing(null);
    setSaved(false);
  }, []);
  useEffect(() => {
    if (!vault) {
      return;
    }
    const timer = window.setTimeout(lock, UNLOCKED_MS);
    return () => window.clearTimeout(timer);
  }, [vault, opened, lock]);
  const openAll = async (with_: Vault, all: Record<string, Sealed | null>) => {
    const pairs = await Promise.all(Object.entries(all).map(async ([name, s]) => [name, s ? await open(with_, s) : null] as const));
    setOpened(Object.fromEntries(pairs));
  };

  if (!here) {
    return <p className="text-muted-foreground">{t('passwords.local')}</p>;
  }
  if (sealed === null) {
    return (
      <p role="status" className="flex items-center gap-2 text-muted-foreground">
        <LoaderCircle aria-hidden className="size-4 animate-spin" />
        {t('passwords.loading')}
      </p>
    );
  }
  if (sealed === 'failed') {
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
  if (!matches.length) {
    return <p className="text-muted-foreground">{t('passwords.none')}</p>;
  }
  const kept = Object.values(sealed).filter((s): s is Sealed => !!s);
  const edited = matches.find((m) => m.name === editing);

  return (
    <>
      <ul className="grid max-h-80 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm">
        {matches.map((m) => {
          const shown = vault ? opened[m.name] : null;
          return (
            <li key={m.name} className={`flex min-h-11 min-w-0 items-center gap-3 py-1 pl-3 ${vault ? 'pr-1' : 'pr-3'}`}>
              <span className="min-w-0 flex-1 font-medium [overflow-wrap:anywhere]">{m.label}</span>
              {shown ? (
                <span className="font-mono [overflow-wrap:anywhere] select-all">{shown}</span>
              ) : (
                <span className="whitespace-nowrap text-muted-foreground">{vault || !sealed[m.name] ? t('passwords.unknown') : '••••••••'}</span>
              )}
              {vault && (
                <Tip label={t('passwords.change')}>
                  <span>
                    <Button variant="ghost" size="icon-sm" aria-label={t('passwords.change')} disabled={busy} onClick={() => setEditing(m.name)}>
                      <Pencil aria-hidden />
                    </Button>
                  </span>
                </Tip>
              )}
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-2">
        {vault ? (
          <Button variant="outline" className="bg-card" onClick={lock}>
            <Lock aria-hidden />
            {t('passwords.lock')}
          </Button>
        ) : (
          <Button variant="outline" className="bg-card" onClick={() => setAsking(true)}>
            <LockOpen aria-hidden />
            {t('passwords.unlock')}
          </Button>
        )}
      </div>
      {saved && (
        <p role="status" className="text-muted-foreground">
          {t('passwords.saved')}
        </p>
      )}
      {asking && (
        <MasterDialog
          sealed={kept}
          onUnlocked={async (v) => {
            await openAll(v, sealed);
            setVault(v);
            setAsking(false);
          }}
          onForgot={async () => {
            lock();
            await load();
          }}
          onClose={() => setAsking(false)}
        />
      )}
      {vault && edited && (
        <EditDialog
          match={edited}
          current={opened[edited.name] ?? null}
          others={matches.filter((m) => m.name !== edited.name).map((m) => m.name)}
          vault={vault}
          onSaved={async (state, names, password) => {
            onState(state);
            setOpened((o) => ({ ...o, ...Object.fromEntries(names.map((n) => [n, password])) }));
            setEditing(null);
            setSaved(true);
            await load();
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

/** The master password asked, or chosen (twice) when none seals a password yet; forgotten, every sealed password goes. */
function MasterDialog({ sealed, onUnlocked, onForgot, onClose }: { sealed: Sealed[]; onUnlocked: (vault: Vault) => Promise<void>; onForgot: () => Promise<void>; onClose: () => void }) {
  const { t } = useTranslation();
  const fresh = !sealed.length;
  const [master, setMaster] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState<Explained | null>(null);
  const [doing, run] = useRunning<'unlock' | 'forget'>();
  const ready = master.trim().length >= MASTER_MIN && (!fresh || again === master);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) {
      return;
    }
    void run('unlock', async () => {
      const vault = await unlock(master, sealed).catch(() => null);
      if (!vault) {
        setError({ text: t('passwords.wrong'), detail: null, log: false });
        return;
      }
      await onUnlocked(vault);
    });
  };
  const forget = async () => {
    if (!(await ask({ title: t('passwords.forgetTitle'), text: t('passwords.forgetText'), confirm: t('passwords.forget'), danger: true }))) {
      return;
    }
    await run('forget', async () => {
      const r = await call('server/password/forget', {});
      setError(r.ok ? null : refused(t, r.error));
      if (r.ok) {
        setMaster('');
        await onForgot();
      }
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !doing && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('passwords.title')}</DialogTitle>
          {fresh && <DialogDescription>{t('passwords.masterNew')}</DialogDescription>}
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <PasswordField label={t('passwords.master')} value={master} onChange={setMaster} min={MASTER_MIN} autoFocus />
          {fresh && <PasswordField label={t('passwords.confirm')} value={again} onChange={setAgain} min={0} />}
          {fresh && again !== '' && again !== master && <p className="m-0 text-xs text-muted-foreground">{t('passwords.mismatch')}</p>}
          {error && <ErrorNote {...error} />}
          <DialogFooter className="items-center">
            {!fresh && (
              <Button type="button" variant="link" className="mr-auto px-0" disabled={!!doing} onClick={() => void forget()}>
                {t('passwords.forgot')}
              </Button>
            )}
            <Button type="button" variant="outline" disabled={!!doing} onClick={onClose}>
              {t('app.cancel')}
            </Button>
            <Button type="submit" busy={doing === 'unlock'} disabled={!ready || doing === 'forget'}>
              <LockOpen aria-hidden />
              {t('passwords.unlock')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** A match's video password changed, for the other matches with the video too when asked: online at once. */
function EditDialog({
  match,
  current,
  others,
  vault,
  onSaved,
  onClose,
}: {
  match: { name: string; label: string };
  current: string | null;
  others: string[];
  vault: Vault;
  onSaved: (state: unknown, names: string[], password: string) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [password, setPassword] = useState(current ?? '');
  const [all, setAll] = useState(false);
  const [error, setError] = useState<Explained | null>(null);
  const [doing, run] = useRunning<'save'>();
  const ready = password.trim().length >= VIDEO_MIN && (password !== current || all);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) {
      return;
    }
    void run('save', async () => {
      const names = [match.name, ...(all ? others : [])];
      const key = await fingerprint(password);
      const chosen = await Promise.all(names.map(async (name) => ({ name, key, sealed: await seal(vault, password) })));
      const r = await call('server/password', { matches: chosen });
      if (!r.ok) {
        setError(refused(t, r.error));
        return;
      }
      await onSaved(r, names, password);
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !doing && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('passwords.edit')}</DialogTitle>
          <DialogDescription>{match.label}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <PasswordField
            label={t('passwords.password')}
            value={password}
            onChange={setPassword}
            min={VIDEO_MIN}
            placeholder={current === null ? t('passwords.unknown') : undefined}
            generate
            autoFocus
          />
          {others.length > 0 && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={all} disabled={!!doing} onChange={(e) => setAll(e.target.checked)} />
              {t('passwords.others', { count: others.length })}
            </label>
          )}
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
