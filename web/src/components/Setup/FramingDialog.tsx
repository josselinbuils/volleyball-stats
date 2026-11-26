import { useEffect, useState } from 'react';
import { CircleCheck, LoaderCircle, RotateCcw, Square, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress } from '@/components/JobProgress';
import { Zoomable } from '@/components/Zoomable';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useRunning } from '@/hooks/useRunning';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { clock, useFormat } from '@/lib/format';
import { CourtPlacer, type Clicks } from './CourtDialog';
import { SourcePicker, type Found } from './SourcePicker';
import { importError, type Framing, type PlacementState } from './helpers/setup';

/** What is out of the picture and what to change, else that the framing is fine. */
export function FramingVerdict({ framing }: { framing: Framing }) {
  const { t, i18n } = useTranslation();
  const list = new Intl.ListFormat(i18n.language, { type: 'conjunction' });
  return (
    <div role="status" className="grid gap-1.5">
      <p className="m-0 flex items-center gap-2 font-medium">
        {framing.ok ? <CircleCheck aria-hidden className="size-4 shrink-0 text-(--point)" /> : <TriangleAlert aria-hidden className="size-4 shrink-0 text-warning" />}
        {framing.ok ? t('app.framing.ok') : framing.out.length ? t('app.framing.out', { lines: list.format(framing.out.map((line) => t(`app.framing.line.${line}`))) }) : t('app.framing.better')}
      </p>
      {framing.advice.length > 0 && (
        <ul className="m-0 grid list-disc gap-1 pl-5">
          {framing.advice.map((advice) => (
            <li key={advice}>{t(`app.framing.advice.${advice}`)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Before a match in a gym: a few seconds filmed from the camera's planned spot, its court found (or clicked the first
 * time, then stored for the matches) and drawn, with what to change. */
export function FramingDialog({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const metres = (x: number) => x.toLocaleString(i18n.language, { maximumFractionDigits: 1 });
  const [state, setState] = useState<PlacementState | 'failed' | null>(null);
  const [found, setFound] = useState<Found | null>(null);
  const [recording, setRecording] = useState(0);
  const [error, setError] = useState<Explained | null>(null);
  // A verdict read: the next test's video is picked again.
  const [again, setAgain] = useState(false);
  const [doing, run] = useRunning();
  const job = state && state !== 'failed' ? state.job : null;
  // Each test's or fit's pictures, for the browser not to show the last one's.
  const version = job?.started ?? 0;

  const refresh = async () => {
    const r = await call<PlacementState>('placement');
    setState((was) => (r.ok ? r : was && was !== 'failed' ? was : 'failed'));
  };
  useEffect(() => {
    void refresh();
  }, []);
  useEffect(() => {
    if (!job?.running) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [job?.running]);

  const refuse = (code: string | undefined) => {
    const [key, values, detail] = importError(code);
    setError({ text: t(key, values), detail: detail ?? null, log: key === 'app.import.failed' });
  };
  const started = (r: PlacementState & { ok: boolean; error?: string }) => {
    if (!r.ok) {
      return explain(t, r.error);
    }
    setState(r);
    setAgain(false);
    return null;
  };
  const start = () =>
    run('test', async () => {
      setError(null);
      setError(started(await call<PlacementState>('placement/test', { source: found?.source, recording: recording + 1 })));
    });
  const fit = async (clicks: Clicks, court: string) => started(await call<PlacementState>('placement/fit', { clicks, court }));
  const stop = () =>
    run('stop', async () => {
      const r = await call('stop', { id: job?.id });
      if (!r.ok) {
        setError(explain(t, r.error));
      }
      await refresh();
    });

  const ready = state && state !== 'failed' && !job?.running && !again;
  const verdict = ready ? state.verdict : null;
  const placing = ready && state.court;
  const failed = ready && !placing && job?.failed && !['stopped', 'interrupted'].includes(job.error ?? '');
  const picking = state && state !== 'failed' && !job?.running && !verdict && !placing && !failed;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={`max-h-[calc(100dvh-2rem)] overflow-y-auto ${placing ? 'sm:max-w-5xl' : 'sm:max-w-2xl'}`}>
        <DialogHeader>
          <DialogTitle>{t('app.framing.title')}</DialogTitle>
          <DialogDescription>{placing ? t('app.framing.place') : t('app.framing.why')}</DialogDescription>
        </DialogHeader>
        {state === 'failed' && <ErrorNote text={t('error.noAnswer')} />}
        {!state && (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
            {t('app.framing.loading')}
          </p>
        )}
        {picking && (
          <>
            <SourcePicker onStart={() => (setError(null), setFound(null))} onFound={(r) => (setFound(r), setRecording(r.recordings.length - 1))} onError={refuse} />
            {found && found.recordings.length > 1 && (
              <fieldset className="grid gap-1.5">
                <legend className="mb-1.5 font-medium">{t('app.import.recording')}</legend>
                {found.recordings.map((r, k) => (
                  <label key={k} className="flex items-center gap-2">
                    <input type="radio" name="framing-recording" checked={recording === k} onChange={() => setRecording(k)} />
                    <span className="tabular-nums">
                      {r.start ? f.when(r.start) : t('app.import.recordingN', { n: k + 1 })} · {clock(r.duration)}
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <Button busy={doing === 'test'} disabled={!found || !!doing} onClick={() => void start()}>
              {t('app.framing.start')}
            </Button>
          </>
        )}
        {job?.running && (
          <div className="grid gap-3">
            <JobProgress label={t('app.framing.running')} fraction={job.progress ?? null} task={job.id}>
              {t('app.framing.running')}
            </JobProgress>
            <Button variant="outline" className="w-fit" busy={doing === 'stop'} disabled={!!doing} onClick={() => void stop()}>
              <Square aria-hidden />
              {t('app.stop')}
            </Button>
          </div>
        )}
        {placing && (
          <>
            {job?.failed === 'fit' && <ErrorNote text={t('app.state.fitFailed')} />}
            <CourtPlacer key={version} src={`/app/placement/image?kind=background&v=${version}`} onFit={fit} />
          </>
        )}
        {verdict && (
          <div className="grid gap-3">
            <Zoomable>
              <img src={`/app/placement/image?kind=picture&v=${version}`} alt={t('app.framing.picture')} draggable={false} className="w-full" />
            </Zoomable>
            <FramingVerdict framing={verdict} />
            {verdict.camera && <p className="m-0 text-sm text-muted-foreground">{t('app.framing.camera', { back: metres(verdict.camera[1]), high: metres(verdict.camera[2]) })}</p>}
          </div>
        )}
        {failed && <ErrorNote {...explain(t, job.error, 'app.framing.failed')} />}
        {(verdict || placing || failed) && (
          <Button variant="outline" className="w-fit" onClick={() => (setAgain(true), setFound(null))}>
            <RotateCcw aria-hidden />
            {t('app.framing.again')}
          </Button>
        )}
        {error && <ErrorNote {...error} />}
      </DialogContent>
    </Dialog>
  );
}
