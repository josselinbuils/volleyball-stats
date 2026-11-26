import { useCallback, useEffect, useState } from 'react';
import { CircleCheck, Copy, ExternalLink, LoaderCircle, LogIn, LogOut, QrCode, Square, SquareCheck, TriangleAlert, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ask } from '@/components/ask';
import { ErrorNote } from '@/components/ErrorNote';
import { JobLine, type Told } from '@/components/JobLine';
import { LateCauses } from '@/components/LateCauses';
import { Tip } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useRunning } from '@/hooks/useRunning';
import { call } from '@/lib/app';
import { copyText } from '@/lib/clipboard';
import { explain, type Explained } from '@/lib/errors';
import { useFormat } from '@/lib/format';
import type { PageChange } from '@/lib/hostedChanges';

/** A match that can go on the site (netlify.state): `new` before its first deploy, else when and whether it is late. */
interface NetlifyMatch {
  name: string;
  date: string | null;
  title: string | null;
  teams: (string | null)[] | null;
  url: string | null;
  at: string | null;
  day: string | null;
  behind: boolean;
  changes: PageChange[] | null;
  new: boolean;
}

interface NetlifyState {
  /** Whether the app can sign in (its Netlify application set). */
  available: boolean;
  /** A sign-in waiting for the user's consent on Netlify's page. */
  connecting: boolean;
  url: string | null;
  matches: NetlifyMatch[];
  /** Deploys in the last 30 days, the free plan's a month, and from how many the card warns. */
  deploys: number;
  free: number;
  warn: number;
  job: Told | null;
}

const POLL_MS = 2000;

const due = (m: NetlifyMatch) => m.new || m.behind;

/** Netlify refused the app's token (`netlify.request`'s PermissionError). Here, not in `lib/errors.ts`: the public page shares that one. */
const refused = (error: string | null | undefined) => error?.replace(/^\w+Error: /, '') === 'netlify';

/** The Site tab's "Sans serveur" card: the matches' public pages on a free Netlify site, signed in from the app. Nothing while
 * the app cannot sign in. */
export function NetlifyCard() {
  const { t } = useTranslation();
  const f = useFormat();
  const [state, setState] = useState<NetlifyState | null>(null);
  const [unread, setUnread] = useState<Explained | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [copied, setCopied] = useState<boolean | null>(null);
  const [showQr, setShowQr] = useState(false);
  const [doing, run] = useRunning();
  const refresh = useCallback(async () => {
    const r = await call<NetlifyState>('netlify');
    if (r.ok) {
      setState(r);
      setUnread(null);
      // At first the newest match due.
      setPicked(
        (p) =>
          p ??
          (r.url
            ? new Set(
                r.matches
                  .filter(due)
                  .slice(0, 1)
                  .map((m) => m.name),
              )
            : null),
      );
    } else {
      setUnread(explain(t, r.error, 'error.loadFailed'));
    }
    return r;
  }, [t]);
  useEffect(() => void refresh(), [refresh]);
  const running = !!state?.job?.running;
  const waiting = running || !!state?.connecting;
  useEffect(() => {
    if (!waiting) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, refresh]);
  // A deploy that ends shows its matches up to date.
  const [wasRunning, setWasRunning] = useState(false);
  if (wasRunning !== running) {
    setWasRunning(running);
    if (!running) {
      setPicked(null);
    }
  }

  if (!state) {
    return unread ? (
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('netlify.title')}</h2>
        <ErrorNote
          {...unread}
          action={
            <Button size="sm" variant="outline" className="bg-card" onClick={() => void refresh()}>
              {t('error.retry')}
            </Button>
          }
        />
      </Card>
    ) : (
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('netlify.title')}</h2>
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden className="size-4 animate-spin" />
          {t('server.loading')}
        </p>
      </Card>
    );
  }
  if (!state.available) {
    return null;
  }

  // Netlify's page opened at once, in the click: a tab opened after an answer is blocked.
  const connect = () => {
    const tab = window.open('', '_blank');
    return run('connect', async () => {
      setError(null);
      const r = await call<{ url: string }>('netlify/connect', {});
      if (r.ok) {
        if (tab) {
          tab.location.href = r.url;
        } else {
          window.open(r.url, '_blank');
        }
        await refresh();
      } else {
        tab?.close();
        setError(explain(t, r.error));
      }
    });
  };
  const disconnect = (confirmed: boolean) =>
    run('disconnect', async () => {
      if (!confirmed && !(await ask({ title: t('netlify.disconnectTitle'), text: t('netlify.disconnectText'), confirm: t('netlify.disconnect') }))) {
        return;
      }
      setError(null);
      const r = await call<NetlifyState>('netlify/disconnect', {});
      if (r.ok) {
        setState(r);
        setPicked(null);
      } else {
        setError(explain(t, r.error));
      }
    });
  const signedOut: Explained = { text: t('netlify.signedOut'), detail: null, log: false };
  const late = state.matches.filter(due).map((m) => m.name);
  const chosen = late.filter((name) => picked?.has(name));
  const allPicked = late.length > 0 && chosen.length === late.length;
  const publishing = doing === 'publish' || running;
  const publish = () =>
    run('publish', async () => {
      setError(null);
      const r = await call<NetlifyState>('netlify/publish', { matches: chosen });
      if (r.ok) {
        setState(r);
      } else {
        setError(refused(r.error) ? signedOut : explain(t, r.error));
      }
    });
  const pick = (name: string, on: boolean) =>
    setPicked((p) => {
      const next = new Set(p);
      if (on) {
        next.add(name);
      } else {
        next.delete(name);
      }
      return next;
    });
  const copy = async (url: string) => {
    try {
      await copyText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  const nameOf = (m: NetlifyMatch) => m.title ?? (m.teams ? t('matchTitle', { one: m.teams[0] ?? t('team', { n: 1 }), two: m.teams[1] ?? t('team', { n: 2 }) }) : m.name);

  if (!state.url) {
    return (
      <Card className="gap-3 px-4 py-3.5">
        <h2 className="text-lg font-semibold">{t('netlify.title')}</h2>
        <p className="text-muted-foreground">{t('netlify.intro')}</p>
        <div className="flex flex-wrap gap-2">
          <Button busy={doing === 'connect' || state.connecting} disabled={doing === 'disconnect'} onClick={() => void connect()}>
            <LogIn aria-hidden />
            {t('netlify.connect')}
          </Button>
          {state.connecting && (
            <Button variant="outline" className="bg-card" busy={doing === 'disconnect'} onClick={() => void disconnect(true)}>
              {t('app.cancel')}
            </Button>
          )}
        </div>
        {state.connecting && <p className="text-muted-foreground">{t('netlify.consent')}</p>}
        {error && <ErrorNote {...error} />}
      </Card>
    );
  }

  return (
    <Card className="gap-3 px-4 py-3.5">
      <h2 className="text-lg font-semibold">{t('netlify.title')}</h2>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <a href={state.url} target="_blank" rel="noreferrer" className="min-w-0 font-medium [overflow-wrap:anywhere] hover:underline">
          {state.url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
          <ExternalLink aria-hidden className="ml-1.5 inline size-3.5 align-[-2px] text-muted-foreground" />
        </a>
        <div className="ml-auto flex">
          <Tip label={t(copied ? 'passwords.copied' : 'passwords.copy')}>
            <Button variant="ghost" size="icon-sm" aria-label={t(copied ? 'passwords.copied' : 'passwords.copy')} onClick={() => void copy(state.url!)}>
              {copied ? <CircleCheck aria-hidden /> : <Copy aria-hidden />}
            </Button>
          </Tip>
          <Tip label={t('netlify.qr')}>
            <Button variant="ghost" size="icon-sm" aria-label={t('netlify.qr')} onClick={() => setShowQr(true)}>
              <QrCode aria-hidden />
            </Button>
          </Tip>
        </div>
      </div>
      {copied === false && <ErrorNote text={t('passwords.copyFailed')} />}
      {state.matches.length ? (
        <ul className="grid max-h-80 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm">
          {state.matches.map((m) => {
            const name = nameOf(m);
            return (
              <li key={m.name} className="flex min-w-0 items-center gap-3 px-3 py-2">
                <input type="checkbox" aria-label={name} checked={due(m) && !!picked?.has(m.name)} disabled={publishing || !due(m)} onChange={(e) => pick(m.name, e.target.checked)} />
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
                  <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap ${due(m) ? '' : 'text-muted-foreground'}`}>
                    {due(m) ? <span aria-hidden className="size-2 rounded-full bg-primary" /> : <CircleCheck aria-hidden className="size-4" />}
                    {t(m.new ? 'server.notOnline' : m.behind ? 'server.late' : 'server.upToDate')}
                  </span>
                </Tip>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-muted-foreground">{t('netlify.none')}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button busy={publishing} disabled={!chosen.length || doing === 'disconnect'} onClick={() => void publish()}>
          <Upload aria-hidden />
          {allPicked ? t('netlify.publishAll') : t('netlify.publish', { count: chosen.length })}
        </Button>
        {late.length > 1 && (
          <Button variant="outline" className="bg-card" disabled={publishing} onClick={() => setPicked(new Set(allPicked ? [] : late))}>
            {allPicked ? <Square aria-hidden /> : <SquareCheck aria-hidden />}
            {t(allPicked ? 'server.pickNone' : 'server.pickAll')}
          </Button>
        )}
        <Button variant="ghost" className="ml-auto" busy={doing === 'disconnect'} disabled={publishing} onClick={() => void disconnect(false)}>
          <LogOut aria-hidden />
          {t('netlify.disconnect')}
        </Button>
      </div>
      {state.deploys >= state.warn && (
        <p role="status" className="flex gap-2 text-sm text-muted-foreground">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('netlify.deploys', { count: state.deploys, free: state.free })}
        </p>
      )}
      {error && <ErrorNote {...error} />}
      {state.job?.failed && refused(state.job.error) ? <ErrorNote {...signedOut} /> : <JobLine job={state.job} running={t('netlify.publishing')} />}
      {showQr && (
        <Dialog open onOpenChange={setShowQr}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>{t('netlify.qr')}</DialogTitle>
            </DialogHeader>
            {/* Black on white in both themes: a phone's camera reads it so. */}
            <img src="/app/netlify/qr" alt={state.url} className="mx-auto aspect-square w-full max-w-64 rounded-md bg-white [image-rendering:pixelated]" />
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}
