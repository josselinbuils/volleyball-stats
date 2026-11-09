import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeftRight, Download, FolderInput, Stethoscope, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Doctor, checkText } from './Doctor';
import { ImportDialog } from './ImportDialog';
import { PreparingCard } from './PreparingCard';
import { VideosDialog } from './VideosDialog';
import { call, type AppState, type Check } from './helpers/setup';

// Polled faster while something runs.
const BUSY_MS = 3000;
const IDLE_MS = 20_000;

/** On the review's list of the matches: what used to need a command. The machine's problems, importing a match, the
 * matches being prepared until their review opens, and the videos of the other machine. */
export function Setup() {
  const { t } = useTranslation();
  const [state, setState] = useState<AppState | null>(null);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [dialog, setDialog] = useState<'import' | 'doctor' | 'videos' | null>(null);
  const refresh = useCallback(async () => {
    try {
      const found = await call<AppState>('state');
      if (found.ok) {
        setState(found);
      }
    } catch {
      // The server restarts: the next poll reads it.
    }
  }, []);
  const recheck = useCallback(async () => {
    try {
      const found = await fetch('/app/doctor');
      setChecks(found.ok ? ((await found.json()) as Check[]) : null);
    } catch {
      setChecks(null);
    }
  }, []);
  useEffect(() => {
    void refresh();
    void recheck();
  }, [refresh, recheck]);
  const running = !!state && (state.preparing.some((p) => p.job?.running) || !!state.videos?.running || !!state.models?.running);
  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), running || dialog ? BUSY_MS : IDLE_MS);
    return () => window.clearInterval(timer);
  }, [refresh, running, dialog]);
  // A match whose pipeline ends opens from the list: the page reloads to show it there.
  const wasRunning = useRef<string[]>([]);
  useEffect(() => {
    if (!state) {
      return;
    }
    if (wasRunning.current.some((name) => !state.preparing.some((p) => p.name === name))) {
      location.reload();
    }
    wasRunning.current = state.preparing.filter((p) => p.state === 'running').map((p) => p.name);
  }, [state]);
  // Models downloaded: their check passes.
  const modelsRunning = !!state?.models?.running;
  useEffect(() => {
    if (!modelsRunning) {
      void recheck();
    }
  }, [modelsRunning, recheck]);

  // The code's version has its own notice (Behind), the machine's load only matters when a pipeline starts.
  const problems = (checks ?? []).filter((c) => c.status !== 'ok' && c.id !== 'code' && c.id !== 'busy');

  return (
    <section className="grid gap-3" aria-label={t('app.setup')}>
      {problems.map((check) => (
        <Alert key={check.id} variant={check.status === 'error' ? 'destructive' : 'warning'}>
          <TriangleAlert aria-hidden />
          <AlertDescription className="grid gap-2">
            <span>{checkText(t, check)}</span>
            {check.command && <code className="w-fit rounded-md bg-muted px-2 py-1 font-mono text-xs select-all">{check.command}</code>}
            {check.id === 'models' && (
              <Button size="sm" variant="outline" className="w-fit bg-card" disabled={modelsRunning} onClick={() => void call('models', {}).then(refresh)}>
                <Download aria-hidden />
                {modelsRunning ? t('app.doctor.downloading') : t('app.doctor.download')}
              </Button>
            )}
            {state?.models?.failed && !modelsRunning && <span className="text-destructive">{t('app.doctor.downloadFailed')}</span>}
          </AlertDescription>
        </Alert>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => setDialog('import')}>
          <FolderInput aria-hidden />
          {t('app.import.open')}
        </Button>
        <Button variant="outline" className="bg-card" onClick={() => setDialog('videos')}>
          <ArrowLeftRight aria-hidden />
          {t('app.videos.open')}
        </Button>
        <Button variant="outline" className="bg-card" onClick={() => setDialog('doctor')}>
          <Stethoscope aria-hidden />
          {t('app.doctor.open')}
        </Button>
      </div>
      {state && state.preparing.length > 0 && (
        <div className="grid gap-3">
          <h2 className="px-1 text-lg font-semibold">{t('app.preparing')}</h2>
          <ol className="grid gap-3 lg:grid-cols-2">
            {state.preparing.map((item) => (
              <li key={item.name}>
                <PreparingCard item={item} onChange={refresh} />
              </li>
            ))}
          </ol>
        </div>
      )}
      {dialog === 'import' && (
        <ImportDialog
          onClose={(started) => {
            setDialog(null);
            if (started) {
              void refresh();
            }
          }}
        />
      )}
      {dialog === 'doctor' && <Doctor checks={checks} onRecheck={recheck} onClose={() => setDialog(null)} />}
      {dialog === 'videos' && state && <VideosDialog job={state.videos} system={state.system} onChange={refresh} onClose={() => setDialog(null)} />}
    </section>
  );
}
