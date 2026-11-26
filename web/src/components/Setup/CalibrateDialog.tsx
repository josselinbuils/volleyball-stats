import { useEffect, useRef, useState } from 'react';
import { CircleCheck, Download, Expand, LoaderCircle, RotateCcw, Square, TriangleAlert } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress } from '@/components/JobProgress';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useRunning } from '@/hooks/useRunning';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { clock, useFormat } from '@/lib/format';
import { SourcePicker, type Found } from './SourcePicker';
import { importError, type Camera, type LensState } from './helpers/setup';

/** A camera in words: its name (or "unknown"), its frame size and rate. */
export function cameraName(t: TFunction, camera: Camera): string {
  return t('app.lens.camera', { name: camera.model ?? t('app.lens.unnamed'), width: camera.size[0], height: camera.size[1], fps: Math.round(camera.fps) });
}

/** The camera's lens calibrated from a video of the board: the cameras known, the board, the video, its job and how it went. */
export function CalibrateDialog({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const percent = (x: number) => new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 0 }).format(x);
  const pixels = (x: number) => x.toLocaleString(i18n.language, { maximumFractionDigits: 1 });
  const [state, setState] = useState<LensState | 'failed' | null>(null);
  const [found, setFound] = useState<Found | null>(null);
  const [recording, setRecording] = useState(0);
  const [error, setError] = useState<Explained | null>(null);
  // A result read: the next calibration's video is picked again.
  const [again, setAgain] = useState(false);
  const [doing, run] = useRunning();
  const board = useRef<HTMLImageElement>(null);
  const job = state && state !== 'failed' ? state.job : null;

  const refresh = async () => {
    const r = await call<LensState>('lens');
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
  const start = () =>
    run('calibrate', async () => {
      setError(null);
      const r = await call<LensState>('lens/calibrate', { source: found?.source, recording: recording + 1 });
      if (r.ok) {
        setState(r);
        setAgain(false);
      } else {
        setError(explain(t, r.error));
      }
    });
  const stop = () =>
    run('stop', async () => {
      const r = await call('stop', { id: job?.id });
      if (!r.ok) {
        setError(explain(t, r.error));
      }
      await refresh();
    });
  const full = () => {
    if (board.current?.requestFullscreen) {
      void board.current.requestFullscreen();
    } else {
      window.open('/app/board', '_blank');
    }
  };

  const result = job && !job.running && !job.failed && !again ? job.result : null;
  const failed = job && !job.running && job.failed && !again && !['stopped', 'interrupted'].includes(job.error ?? '');
  const picking = !job?.running && !result && !failed;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('app.lens.title')}</DialogTitle>
          <DialogDescription>{t('app.lens.why')}</DialogDescription>
        </DialogHeader>
        {state === 'failed' ? (
          <ErrorNote text={t('error.noAnswer')} />
        ) : !state ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
            {t('app.lens.loading')}
          </p>
        ) : (
          <div className="grid gap-1.5">
            <p className="m-0 font-medium">{t('app.lens.known')}</p>
            <ul className="grid gap-1 text-sm text-muted-foreground">
              {state.lenses.map((camera) => (
                <li key={`${camera.model}-${camera.size.join('x')}-${camera.fps}`}>
                  {cameraName(t, camera)}
                  {camera.own && ` · ${t('app.lens.own')}`}
                </li>
              ))}
            </ul>
          </div>
        )}
        {picking && (
          <>
            <ol className="grid list-decimal gap-3 pl-5">
              <li>
                <div className="grid gap-2">
                  {t('app.lens.board')}
                  <img ref={board} src="/app/board" alt={t('app.lens.boardAlt')} className="w-full max-w-xs min-w-0 rounded-md border bg-white object-contain" />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={full}>
                      <Expand aria-hidden />
                      {t('app.lens.full')}
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <a href="/app/board" download="damier.png">
                        <Download aria-hidden />
                        {t('app.lens.print')}
                      </a>
                    </Button>
                  </div>
                </div>
              </li>
              <li>{t('app.lens.film')}</li>
              <li>
                <div className="grid gap-2">
                  {t('app.lens.pick')}
                  <SourcePicker onStart={() => (setError(null), setFound(null))} onFound={(r) => (setFound(r), setRecording(r.recordings.length - 1))} onError={refuse} />
                </div>
              </li>
            </ol>
            {found && found.recordings.length > 1 && (
              <fieldset className="grid gap-1.5">
                <legend className="mb-1.5 font-medium">{t('app.import.recording')}</legend>
                {found.recordings.map((r, k) => (
                  <label key={k} className="flex items-center gap-2">
                    <input type="radio" name="lens-recording" checked={recording === k} onChange={() => setRecording(k)} />
                    <span className="tabular-nums">
                      {r.start ? f.when(r.start) : t('app.import.recordingN', { n: k + 1 })} · {clock(r.duration)}
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <Button busy={doing === 'calibrate'} disabled={!found || !!doing} onClick={() => void start()}>
              {t('app.lens.start')}
            </Button>
          </>
        )}
        {job?.running && (
          <div className="grid gap-3">
            <JobProgress label={t('app.lens.running')} fraction={job.progress ?? null} task={job.id}>
              {t('app.lens.running')}
            </JobProgress>
            <Button variant="outline" className="w-fit" busy={doing === 'stop'} disabled={!!doing} onClick={() => void stop()}>
              <Square aria-hidden />
              {t('app.stop')}
            </Button>
          </div>
        )}
        {result && (
          <div role="status" className="grid gap-1.5">
            <p className="m-0 flex items-center gap-2 font-medium">
              {result.kept ? <CircleCheck aria-hidden className="size-4 shrink-0 text-(--point)" /> : <TriangleAlert aria-hidden className="size-4 shrink-0 text-warning" />}
              {result.kept ? t('app.lens.kept', { camera: cameraName(t, result.camera) }) : t(`app.lens.why_${result.why}`, { coverage: percent(result.coverage ?? 0), rms: pixels(result.rms ?? 0) })}
            </p>
            {result.rms != null && (
              <p className="m-0 text-sm text-muted-foreground">{t('app.lens.measure', { views: result.views, coverage: percent(result.coverage ?? 0), rms: pixels(result.rms) })}</p>
            )}
          </div>
        )}
        {failed && <ErrorNote {...explain(t, job.error, 'app.lens.failed')} />}
        {(result || failed) && (
          <Button variant="outline" className="w-fit" onClick={() => (setAgain(true), setFound(null))}>
            <RotateCcw aria-hidden />
            {t('app.lens.again')}
          </Button>
        )}
        {error && <ErrorNote {...error} />}
      </DialogContent>
    </Dialog>
  );
}
