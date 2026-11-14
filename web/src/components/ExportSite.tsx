import { useCallback, useEffect, useState } from 'react';
import { Download, FolderDown, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobLine, type Told } from '@/components/JobLine';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { useFormat } from '@/lib/format';
import { useRunning } from '@/hooks/useRunning';

/** A match the export can take (app.export_state). */
interface Ready {
  name: string;
  path: string;
  date: string | null;
  title: string | null;
  teams: { name: string | null }[] | null;
}

interface ExportState {
  matches: Ready[];
  job: Told | null;
  /** The last zip, while no export runs: its size, when, the matches it holds (null: unknown) and its folder. */
  file: { size: number; at: number; matches: string[] | null; folder: string } | null;
}

const POLL_MS = 1500;

/** The site zipped to put on a host of one's own: the matches to take, the export's bar, then the file to download. */
export function ExportSite() {
  const { t } = useTranslation();
  const f = useFormat();
  const [state, setState] = useState<ExportState | null>(null);
  const [unread, setUnread] = useState(false);
  const [chosen, setChosen] = useState<Set<string> | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  const [doing, run] = useRunning();
  const refresh = useCallback(async () => {
    const r = await call<ExportState>('export');
    if (r.ok) {
      setState(r);
      setChosen((c) => c ?? new Set(r.file?.matches ?? r.matches.map((m) => m.path)));
    }
    return r;
  }, []);
  const load = useCallback(() => {
    setUnread(false);
    void refresh().then((r) => setUnread(!r.ok));
  }, [refresh]);
  useEffect(load, [load]);
  const running = !!state?.job?.running;
  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  if (!state || !chosen) {
    return unread ? (
      <ErrorNote
        text={t('error.loadFailed')}
        log
        action={
          <Button size="sm" variant="outline" className="bg-card" onClick={load}>
            {t('error.retry')}
          </Button>
        }
      />
    ) : (
      <p role="status" className="flex items-center gap-2 text-muted-foreground">
        <LoaderCircle aria-hidden className="size-4 animate-spin" />
        {t('export.loading')}
      </p>
    );
  }
  const picked = state.matches.filter((m) => chosen.has(m.path)).map((m) => m.path);
  // The last zip, offered while it holds the matches picked.
  const held = state.file && (!state.file.matches || (state.file.matches.length === picked.length && picked.every((p) => state.file?.matches?.includes(p))));
  const start = () =>
    run('export', async () => {
      const r = await call<ExportState>('export', { matches: picked, folder: t('export.folder') });
      if (r.ok) {
        setState(r);
      }
      setError(r.ok ? null : explain(t, r.error));
    });
  const toggle = (path: string, on: boolean) =>
    setChosen((c) => {
      const next = new Set(c);
      if (on) {
        next.add(path);
      } else {
        next.delete(path);
      }
      return next;
    });

  return (
    <div className="grid gap-3">
      <p className="text-muted-foreground">{t('export.intro')}</p>
      {state.matches.length ? (
        <ul className="grid max-h-64 auto-rows-max divide-y overflow-y-auto overscroll-contain rounded-md border text-sm">
          {state.matches.map((m) => {
            const names = m.teams?.map((team, k) => team.name ?? t('team', { n: k + 1 }));
            return (
              <li key={m.path}>
                <label className="flex min-w-0 items-center gap-3 px-3 py-2">
                  <input type="checkbox" checked={chosen.has(m.path)} disabled={running} onChange={(e) => toggle(m.path, e.target.checked)} />
                  <span className="flex min-w-0 flex-1 flex-wrap justify-between gap-x-3">
                    <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{m.title ?? (names ? t('matchTitle', { one: names[0], two: names[1] }) : m.name)}</span>
                    {m.date && <span className="whitespace-nowrap text-muted-foreground">{f.date(m.date)}</span>}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-muted-foreground">{t('export.none')}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {held && state.file && !running ? (
          <>
            <Button asChild>
              <a href="/app/export/file" download={`${state.file.folder}.zip`}>
                <Download aria-hidden />
                {t('export.download', { size: f.size(state.file.size) })}
              </a>
            </Button>
            <Button variant="outline" className="bg-card" busy={doing === 'export'} disabled={!picked.length} onClick={() => void start()}>
              <FolderDown aria-hidden />
              {t('export.again')}
            </Button>
          </>
        ) : (
          <Button busy={doing === 'export' || running} disabled={!picked.length} onClick={() => void start()}>
            <FolderDown aria-hidden />
            {running ? t('export.running') : t('export.start')}
          </Button>
        )}
      </div>
      {error && <ErrorNote {...error} />}
      {(running || state.job?.failed) && <JobLine job={state.job} running={t('export.running')} />}
      {held && state.file && !running && <p className="text-muted-foreground">{t('export.done', { at: f.when(new Date(state.file.at * 1000).toISOString()) })}</p>}
    </div>
  );
}

/** `ExportSite` in a dialog, for the review's menu. */
export function ExportDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('export.title')}</DialogTitle>
        </DialogHeader>
        <ExportSite />
      </DialogContent>
    </Dialog>
  );
}
