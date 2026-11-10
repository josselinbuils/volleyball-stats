import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { CloudUpload, DatabaseBackup, ExternalLink, LoaderCircle, PlugZap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { INPUT, call } from '@/lib/app';
import { useFormat } from '@/lib/format';
import type { Job } from '@/components/Setup/helpers/setup';

/** The hosting server as server.py reads it. */
interface Server {
  address: string;
  folder: string;
  key: string;
  url: string;
}

interface ServerState {
  server: Server | null;
  auto: boolean;
  hosting: Job | null;
  backup: Job | null;
}

interface Copies {
  free: number;
  days: { day: string; matches: string[] }[];
  /** The automatic copies' choice as the server holds it. */
  auto: boolean;
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

/** A job's last run: running, failed with its reason, or done and when. */
function JobLine({ job, running }: { job: Job | null; running: string }) {
  const { t } = useTranslation();
  if (!job) {
    return null;
  }
  if (job.running) {
    return <p className="text-muted-foreground">{running}</p>;
  }
  if (job.failed) {
    return (
      <p role="alert" className="text-destructive [overflow-wrap:anywhere]">
        {t('server.failed', { error: job.error ?? '' })}
      </p>
    );
  }
  const at = new Date((job.ended ?? job.started) * 1000);
  return <p className="text-muted-foreground">{t('server.done', { at: at.toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) })}</p>;
}

/** The "Serveur" tab of the review's list: the hosting server, the matches online and the backups. */
export function ServerTab() {
  const { t } = useTranslation();
  const f = useFormat();
  const [state, setState] = useState<ServerState | null>(null);
  const [form, setForm] = useState<Server>(EMPTY);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [copies, setCopies] = useState<Copies | null | 'failed'>(null);
  const [listing, setListing] = useState(false);
  // The choice saved here only: the server could not take it.
  const [autoLocal, setAutoLocal] = useState(false);
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
      setState((s) => s && { ...s, auto: r.auto });
    }
  }, []);
  useEffect(() => {
    void refresh().then((r) => {
      if (r.ok) {
        setForm(r.server ?? EMPTY);
        if (r.server) {
          void listCopies();
        }
      }
    });
  }, [refresh, listCopies]);
  const running = !!(state?.hosting?.running || state?.backup?.running);
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

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const r = await call<ServerState>('server', form);
    if (r.ok) {
      setState(r);
      setForm(r.server ?? EMPTY);
    }
    setNote({ ok: r.ok, text: t(r.ok ? 'server.saved' : 'server.invalid') });
  };
  const test = async () => {
    setNote(null);
    const r = await call('server/test', {});
    const missing = r.error?.startsWith('missing:');
    setNote({ ok: r.ok, text: r.ok ? t('server.reached') : missing ? t('server.missing') : t('server.unreached', { error: r.error ?? '' }) });
  };
  const setAuto = async (on: boolean) => {
    const r = await call<ServerState & { shared: boolean }>('server/auto', { on });
    if (r.ok) {
      setState(r);
      setAutoLocal(!r.shared);
    }
  };
  const start = async (path: 'server/host' | 'server/backup') => {
    const r = await call<ServerState>(path, {});
    if (r.ok) {
      setState(r);
    }
  };
  const saved = state?.server;
  const changed = FIELDS.some(({ key }) => form[key].trim() !== (saved?.[key] ?? ''));
  if (!state) {
    return <Loading text={t('server.loading')} />;
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card className="gap-3 px-4 py-3.5 lg:row-span-2">
        <h2 className="text-lg font-semibold">{t('server.connection')}</h2>
        <form onSubmit={(e) => void save(e)} className="grid gap-3">
          {FIELDS.map(({ key, placeholder }) => (
            <label key={key} className="grid gap-1 font-medium">
              {t(`server.${key}`)}
              <input required={key !== 'url'} value={form[key]} placeholder={placeholder} onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))} className={INPUT} />
            </label>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!changed}>
              {t('server.save')}
            </Button>
            <Button type="button" variant="outline" className="bg-card" disabled={!saved || changed} onClick={() => void test()}>
              <PlugZap aria-hidden />
              {t('server.test')}
            </Button>
          </div>
          {note && (
            <p role="status" className={note.ok ? 'text-muted-foreground' : 'text-destructive [overflow-wrap:anywhere]'}>
              {note.text}
            </p>
          )}
        </form>
      </Card>
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('server.online')}</h2>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!saved || !!state?.hosting?.running} onClick={() => void start('server/host')}>
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
        <JobLine job={state?.hosting ?? null} running={t('server.hosting')} />
      </Card>
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('server.backups')}</h2>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={!!state?.auto} disabled={!saved} onChange={(e) => void setAuto(e.target.checked)} />
          {t('server.auto')}
        </label>
        {autoLocal && <p className="text-sm text-destructive">{t('server.autoLocal')}</p>}
        <Button variant="outline" className="w-fit bg-card" disabled={!saved || !!state?.backup?.running} onClick={() => void start('server/backup')}>
          <DatabaseBackup aria-hidden />
          {t('server.backUp')}
        </Button>
        <JobLine job={state?.backup ?? null} running={t('server.backingUp')} />
        {listing && !(copies && copies !== 'failed') && <Loading text={t('server.listing')} />}
        {copies === 'failed' && !listing && <p className="text-destructive">{t('server.copiesFailed')}</p>}
        {copies && copies !== 'failed' && (
          <div className="grid gap-1">
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              {t('server.free', { gb: copies.free })}
              {listing && <LoaderCircle aria-label={t('server.listing')} className="size-3.5 animate-spin" />}
            </p>
            <ol className="grid gap-0.5 text-sm tabular-nums">
              {copies.days.map(({ day, matches }) => (
                <li key={day} className="flex justify-between gap-3">
                  <span>{f.date(day)}</span>
                  <span className="text-muted-foreground">{t('server.matchesN', { count: matches.length })}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
    </div>
  );
}
