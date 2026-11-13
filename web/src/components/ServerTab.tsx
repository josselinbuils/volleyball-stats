import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { CircleCheck, CloudUpload, DatabaseBackup, ExternalLink, LoaderCircle, PlugZap, RotateCcw, ShieldCheck, Trash2, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tip } from '@/components/Tip';
import { JobProgress } from '@/components/JobProgress';
import { LateCauses } from '@/components/LateCauses';
import { INPUT, call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { useFormat } from '@/lib/format';
import type { PageChange } from '@/lib/hostedChanges';
import { useRunning } from '@/hooks/useRunning';
import type { Job } from '@/components/Setup/helpers/setup';

/** The hosting server as server.py reads it. */
interface Server {
  address: string;
  folder: string;
  key: string;
  url: string;
}

/** A job of the tab, with its stage ("match": the `n`th of `of`) and the seconds spent and left while it runs. */
type Told = Job & { n?: number | null; of?: number | null; elapsed?: number; left?: number | null };

/** A match online: its page's address, and when it last went up (`day` when not today), whether it changed since and what. */
interface Online {
  name: string;
  date: string | null;
  title: string | null;
  teams: (string | null)[] | null;
  url: string | null;
  at: string | null;
  day: string | null;
  behind: boolean;
  changes: PageChange[] | null;
}

interface ServerState {
  server: Server | null;
  online: Online[];
  auto: boolean;
  /** How this machine's last copy and check went. */
  last: { at: string | null; error: string | null; verified: string | null; problems: string[] };
  hosting: Told | null;
  backup: Told | null;
  verify: Told | null;
}

// What sits beside the matches, restored as one.
const SHARED = 'shared';

interface Copies {
  /** GB free on the server, and bytes the backups use. */
  free: number;
  used: number;
  /** How many copies the server keeps, besides each match's newest. */
  keep: number;
  /** Newest first: its last save's time when known, its own size (what removing it frees) and the matches it holds the newest copy of. */
  days: { day: string; saved: string | null; matches: string[]; size: number; newest: string[] }[];
}

const EMPTY: Server = { address: '', folder: '', key: '', url: '' };
const FIELDS = [
  { key: 'address', placeholder: 'root@192.0.2.1' },
  { key: 'folder', placeholder: '/var/www/volleyball/' },
  { key: 'key', placeholder: '~/.ssh/id_ed25519' },
  { key: 'url', placeholder: 'https://' },
] as const;
const BUSY_MS = 3000;

function Loading({ text }: { text: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-muted-foreground">
      <LoaderCircle aria-hidden className="size-4 animate-spin" />
      {text}
    </p>
  );
}

/** A job's last run: running (its bar, what it does and the time left), failed with its reason, or done and when
 * (unless `quiet`: the card already says it). */
function JobLine({ job, running, quiet }: { job: Told | null; running: string; quiet?: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  if (!job || (quiet && !job.running && !job.failed)) {
    return null;
  }
  if (job.running) {
    return (
      <JobProgress label={running} fraction={job.progress ?? null} part={job.part} left={job.left} elapsed={job.elapsed}>
        {job.stage ? t(`server.stage.${job.stage}`, { n: job.n, of: job.of, defaultValue: running }) : running}
      </JobProgress>
    );
  }
  if (job.failed) {
    return <ErrorNote {...explain(t, job.error)} />;
  }
  return <p className="text-muted-foreground">{t('server.done', { at: f.when(new Date((job.ended ?? job.started) * 1000).toISOString()) })}</p>;
}

/** A line of the backups' state: fine (muted, a check) or wrong (red, a warning), with what it adds below. */
function Status({ ok, children }: { ok: boolean; children: ReactNode }) {
  const Icon = ok ? CircleCheck : TriangleAlert;
  return (
    <div role={ok ? undefined : 'alert'} className={`flex gap-2 [overflow-wrap:anywhere] ${ok ? 'text-muted-foreground' : 'text-destructive'}`}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** The "Serveur" tab of the review's list: the hosting server, the matches online and the backups. */
export function ServerTab() {
  const { t } = useTranslation();
  const f = useFormat();
  const [state, setState] = useState<ServerState | null>(null);
  const [form, setForm] = useState<Server>(EMPTY);
  const [note, setNote] = useState<{ ok: true; text: string } | { ok: false; error: Explained } | null>(null);
  // The server's state unread: the tab says so, with a retry.
  const [unread, setUnread] = useState(false);
  // What failed to start in the hosting's card and in the backups'.
  const [hostError, setHostError] = useState<Explained | null>(null);
  const [backupError, setBackupError] = useState<Explained | null>(null);
  const [copies, setCopies] = useState<Copies | null | 'failed'>(null);
  const [listing, setListing] = useState(false);
  const [keep, setKeep] = useState('');
  // A removal waiting for its confirmation: one copy, or those a new count removes.
  const [confirm, setConfirm] = useState<{ day: string } | { keep: number; removes: string[] } | null>(null);
  const [copiesError, setCopiesError] = useState(false);
  // A copy to restore from, and what of it.
  const [restoring, setRestoring] = useState<{ day: string; matches: string[]; what: string } | null>(null);
  const [restored, setRestored] = useState<boolean | null>(null);
  // The action running: saving, testing, starting a job, switching the automatic copies, a count or a copy removed.
  const [doing, run] = useRunning();
  const removing = doing === 'keep' || !!doing?.startsWith('delete:');
  const refresh = useCallback(async () => {
    const r = await call<ServerState>('server');
    if (r.ok) {
      setState(r);
    }
    return r;
  }, []);
  const listCopies = useCallback(async () => {
    setListing(true);
    const r = await call<Copies>('server/copies');
    setListing(false);
    setCopies(r.ok ? r : 'failed');
    if (r.ok) {
      setKeep(String(r.keep));
    }
  }, []);
  const load = useCallback(() => {
    setUnread(false);
    void refresh().then((r) => {
      if (r.ok) {
        setForm(r.server ?? EMPTY);
        if (r.server) {
          void listCopies();
        }
      } else {
        setUnread(true);
      }
    });
  }, [refresh, listCopies]);
  useEffect(load, [load]);
  const running = !!(state?.hosting?.running || state?.backup?.running || state?.verify?.running);
  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), BUSY_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);
  // A backup that ends adds its copy to the list.
  const backingUp = useRef(false);
  useEffect(() => {
    const now = !!state?.backup?.running;
    if (backingUp.current && !now) {
      void listCopies();
    }
    backingUp.current = now;
  }, [state?.backup?.running, listCopies]);

  const save = (event: FormEvent) => {
    event.preventDefault();
    void run('save', async () => {
      const r = await call<ServerState>('server', form);
      if (r.ok) {
        setState(r);
        setForm(r.server ?? EMPTY);
      }
      setNote(r.ok ? { ok: true, text: t('server.saved') } : { ok: false, error: r.error === 'network' ? explain(t, r.error) : { text: t('server.invalid'), detail: null, log: false } });
    });
  };
  const test = () =>
    run('test', async () => {
      setNote(null);
      const r = await call('server/test', {});
      setNote(
        r.ok
          ? { ok: true, text: t('server.reached') }
          : { ok: false, error: r.error?.startsWith('missing:') ? { text: t('server.missing'), detail: null, log: false } : explain(t, r.error, 'server.unreached') },
      );
    });
  const setAuto = (on: boolean) =>
    run('auto', async () => {
      const r = await call<ServerState>('server/auto', { on });
      if (r.ok) {
        setState(r);
      }
      setBackupError(r.ok ? null : explain(t, r.error));
    });
  const remove = (body: { day: string } | { keep: number; apply: true }) => {
    setConfirm(null);
    return run('day' in body ? `delete:${body.day}` : 'keep', async () => {
      const r = await call('day' in body ? 'server/delete' : 'server/keep', body);
      setCopiesError(!r.ok);
      await listCopies();
    });
  };
  const applyKeep = async () => {
    const count = Number(keep);
    const r = await run('keep', () => call<{ removes: string[] }>('server/keep', { keep: count, apply: false }));
    if (!r.ok) {
      setCopiesError(true);
    } else if (r.removes.length) {
      setConfirm({ keep: count, removes: r.removes });
    } else {
      void remove({ keep: count, apply: true });
    }
  };
  const start = (key: 'host' | 'backup' | 'verify') =>
    run(key, async () => {
      const r = await call<ServerState>(`server/${key}`, {});
      if (r.ok) {
        setState(r);
      }
      (key === 'host' ? setHostError : setBackupError)(r.ok ? null : explain(t, r.error));
    });
  const restore = (body: { day: string; what: string }) => {
    setRestoring(null);
    return run(`restore:${body.day}`, async () => {
      const r = await call('server/restore', { copy: body.day, what: body.what });
      setRestored(r.ok);
      await refresh();
    });
  };
  // A copy is named by its last save, else by its day, and its hour since copies are hourly.
  const copyName = (day: string) => {
    const saved = copies && copies !== 'failed' ? copies.days.find((d) => d.day === day)?.saved : null;
    return saved ? f.when(saved) : day.includes('T') ? f.when(`${day}:00`) : f.date(day);
  };
  const saved = state?.server;
  const changed = FIELDS.some(({ key }) => form[key].trim() !== (saved?.[key] ?? ''));
  if (!state) {
    return unread ? (
      <ErrorNote
        text={t('error.loadFailed')}
        log
        className="px-1"
        action={
          <Button size="sm" variant="outline" className="bg-card" onClick={load}>
            {t('error.retry')}
          </Button>
        }
      />
    ) : (
      <Loading text={t('server.loading')} />
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card className="gap-3 px-4 py-3.5 lg:row-span-2">
        <h2 className="text-lg font-semibold">{t('server.connection')}</h2>
        <form onSubmit={save} className="grid gap-3">
          {FIELDS.map(({ key, placeholder }) => (
            <label key={key} className="grid gap-1 font-medium">
              {t(`server.${key}`)}
              <input required={key !== 'url'} value={form[key]} placeholder={placeholder} onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))} className={INPUT} />
            </label>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" busy={doing === 'save'} disabled={!changed || doing === 'test'}>
              {t('server.save')}
            </Button>
            <Button type="button" variant="outline" className="bg-card" busy={doing === 'test'} disabled={!saved || changed || doing === 'save'} onClick={() => void test()}>
              <PlugZap aria-hidden />
              {t('server.test')}
            </Button>
          </div>
          {note?.ok && (
            <p role="status" className="text-muted-foreground">
              {note.text}
            </p>
          )}
          {note && !note.ok && <ErrorNote {...note.error} />}
        </form>
      </Card>
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('server.online')}</h2>
        {state.online.length ? (
          <ul className="grid max-h-80 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm">
            {state.online.map((m) => {
              const name = m.title ?? (m.teams ? t('matchTitle', { one: m.teams[0] ?? t('team', { n: 1 }), two: m.teams[1] ?? t('team', { n: 2 }) }) : m.name);
              return (
                <li key={m.name} className="flex min-w-0 items-center gap-3 px-3 py-2">
                  {/* The date goes under the match when the row is narrow. */}
                  <span className="flex min-w-0 flex-1 flex-wrap justify-between gap-x-3">
                    {m.url ? (
                      <a href={m.url} target="_blank" rel="noreferrer" className="min-w-0 font-medium [overflow-wrap:anywhere] hover:underline">
                        {name}
                        <ExternalLink aria-hidden className="ml-1.5 inline size-3.5 align-[-2px] text-muted-foreground" />
                      </a>
                    ) : (
                      <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{name}</span>
                    )}
                    {m.date && <span className="whitespace-nowrap text-muted-foreground">{f.date(m.date)}</span>}
                  </span>
                  <Tip
                    label={
                      m.at || m.changes?.length ? (
                        <div className="grid gap-1">
                          {m.at && <p className="m-0">{m.day ? t('review.hostedDay', { day: f.date(m.day), at: m.at }) : t('review.hosted', { at: m.at })}</p>}
                          {m.behind && <LateCauses changes={m.changes} />}
                        </div>
                      ) : undefined
                    }
                  >
                    <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap ${m.behind ? '' : 'text-muted-foreground'}`}>
                      {m.behind ? <span aria-hidden className="size-2 rounded-full bg-primary" /> : <CircleCheck aria-hidden className="size-4" />}
                      {t(m.behind ? 'server.late' : 'server.upToDate')}
                    </span>
                  </Tip>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-muted-foreground">{t('server.noneOnline')}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button busy={doing === 'host' || !!state.hosting?.running} disabled={!saved || !state.online.length} onClick={() => void start('host')}>
            <CloudUpload aria-hidden />
            {t('server.hostAll')}
          </Button>
          {saved?.url && (
            <Button variant="outline" className="bg-card" asChild>
              <a href={saved.url} target="_blank" rel="noreferrer">
                <ExternalLink aria-hidden />
                {t('server.openOnline')}
              </a>
            </Button>
          )}
        </div>
        {hostError && <ErrorNote {...hostError} />}
        <JobLine job={state.hosting} running={t('server.hosting')} />
      </Card>
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('server.backups')}</h2>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!state.auto} disabled={!saved || doing === 'auto'} onChange={(e) => void setAuto(e.target.checked)} />
          {t('server.auto')}
        </label>
        <div className="grid gap-1">
          {state.last.error ? (
            <Status ok={false}>
              <p>{t('server.lastFailed')}</p>
              <p className="text-xs text-muted-foreground">{state.last.error}</p>
            </Status>
          ) : (
            <Status ok={!!state.last.at}>{state.last.at ? t('server.lastAt', { at: f.when(state.last.at) }) : t('server.never')}</Status>
          )}
          {!state.verify?.running && state.last.verified && (
            <Status ok={!state.last.problems.length}>
              <p>{state.last.problems.length ? t('server.differ', { at: f.when(state.last.verified) }) : t('server.same', { at: f.when(state.last.verified) })}</p>
              {state.last.problems.length > 0 && (
                <ul className="list-disc pl-5 text-sm">
                  {state.last.problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              )}
            </Status>
          )}
          {restored !== null && <Status ok={restored}>{t(restored ? 'server.restored' : 'error.failed')}</Status>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="bg-card" busy={doing === 'backup' || !!state.backup?.running} disabled={!saved} onClick={() => void start('backup')}>
            <DatabaseBackup aria-hidden />
            {t('server.backUp')}
          </Button>
          <Button variant="outline" className="bg-card" busy={doing === 'verify' || !!state.verify?.running} disabled={!saved} onClick={() => void start('verify')}>
            <ShieldCheck aria-hidden />
            {t('server.verify')}
          </Button>
        </div>
        {backupError && <ErrorNote {...backupError} />}
        <JobLine job={state.backup} running={t('server.backingUp')} quiet />
        {state.verify?.running && <JobLine job={state.verify} running={t('server.verifying')} />}
        {listing && !(copies && copies !== 'failed') && <Loading text={t('server.listing')} />}
        {copies === 'failed' && !listing && (
          <ErrorNote
            text={t('server.copiesFailed')}
            log
            action={
              <Button size="sm" variant="outline" className="bg-card" onClick={() => void listCopies()}>
                {t('error.retry')}
              </Button>
            }
          />
        )}
        {copiesError && <ErrorNote />}
        {copies && copies !== 'failed' && (
          <div className="grid gap-2">
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              {t('server.room', { used: f.size(copies.used), free: f.size(copies.free * 1024 ** 3) })}
              {listing && <LoaderCircle aria-label={t('server.listing')} className="size-3.5 animate-spin" />}
            </p>
            <ol className="grid max-h-80 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm tabular-nums">
              {copies.days.map(({ day, matches, size, newest }) => (
                <li key={day} className="flex items-center gap-3 py-1 pr-1 pl-3">
                  {/* The count goes under the day when the row is narrow. */}
                  <span className="flex min-w-0 flex-1 flex-wrap justify-between gap-x-3">
                    <span className="whitespace-nowrap">{copyName(day)}</span>
                    <span className="whitespace-nowrap text-muted-foreground">{t('server.matchesN', { count: matches.length })}</span>
                  </span>
                  <Tip label={t('server.sizeTip')}>
                    <span className="w-16 text-right">{f.size(size)}</span>
                  </Tip>
                  <div className="flex">
                    <Tip label={t('server.restore')}>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('server.restore')}
                        busy={doing === `restore:${day}`}
                        disabled={!!doing}
                        onClick={() => setRestoring({ day, matches, what: matches[0] ?? SHARED })}
                      >
                        <RotateCcw aria-hidden />
                      </Button>
                    </Tip>
                    <Tip label={newest.length ? t('server.newest') : t('server.delete')}>
                      {/* A disabled button gets no pointer events: the tip sits on its wrapper. */}
                      <span>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t('server.delete')}
                          busy={doing === `delete:${day}`}
                          disabled={newest.length > 0 || removing}
                          onClick={() => setConfirm({ day })}
                        >
                          <Trash2 aria-hidden />
                        </Button>
                      </span>
                    </Tip>
                  </div>
                </li>
              ))}
            </ol>
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void applyKeep();
              }}
            >
              <label htmlFor="server-keep">{t('server.keep')}</label>
              <input id="server-keep" type="number" min={1} max={365} required value={keep} onChange={(e) => setKeep(e.target.value)} className={`${INPUT} w-20 tabular-nums`} />
              <Button type="submit" size="sm" variant="outline" className="bg-card" busy={doing === 'keep'} disabled={Number(keep) === copies.keep || removing}>
                {t('server.apply')}
              </Button>
            </form>
          </div>
        )}
      </Card>
      {restoring && (
        <Dialog open onOpenChange={(open) => !open && setRestoring(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('server.restoreTitle', { date: copyName(restoring.day) })}</DialogTitle>
              <DialogDescription>{t('server.restoreText')}</DialogDescription>
            </DialogHeader>
            <fieldset className="grid gap-2">
              {[...restoring.matches, SHARED].map((what) => (
                <label key={what} className="flex items-center gap-2 [overflow-wrap:anywhere]">
                  <input type="radio" name="restore" checked={restoring.what === what} onChange={() => setRestoring({ ...restoring, what })} />
                  {what === SHARED ? t('server.shared') : what}
                </label>
              ))}
            </fieldset>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRestoring(null)}>
                {t('app.cancel')}
              </Button>
              <Button onClick={() => void restore(restoring)}>
                <RotateCcw aria-hidden />
                {t('server.restore')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {confirm && (
        <Dialog open onOpenChange={(open) => !open && setConfirm(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{'day' in confirm ? t('server.deleteTitle', { date: copyName(confirm.day) }) : t('server.keepTitle', { count: confirm.removes.length })}</DialogTitle>
              <DialogDescription>{t('server.deleteText')}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirm(null)}>
                {t('app.cancel')}
              </Button>
              <Button variant="destructive" onClick={() => void remove('day' in confirm ? { day: confirm.day } : { keep: confirm.keep, apply: true })}>
                {t('app.delete')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
