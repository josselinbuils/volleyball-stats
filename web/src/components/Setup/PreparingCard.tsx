import { useState } from 'react';
import { ArrowLeftRight, Crosshair, Play, RotateCcw, Square, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useFormat } from '@/lib/format';
import { CourtDialog } from './CourtDialog';
import { call, imageUrl, teamNames, type Check, type Preparing } from './helpers/setup';

/** A match on its way to the review: the copy, the court, a look at both before the analysis, the analysis, or why it
 * stopped. */
export function PreparingCard({ item, onChange }: { item: Preparing; onChange: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const [placing, setPlacing] = useState(false);
  const [confirm, setConfirm] = useState<'stop' | 'delete' | null>(null);
  const [busy, setBusy] = useState<Check | null>(null);
  const [error, setError] = useState(false);
  // The pictures change when the sides swap or the court is placed again.
  const [version, setVersion] = useState(0);
  const names = teamNames(item);
  const job = item.job;
  const act = async (path: string, body: object = {}) => {
    setError(false);
    const r = await call<{ busy?: Check }>(path, { match: item.name, ...body });
    if (r.status === 409 && r.busy) {
      setBusy(r.busy);
    } else if (!r.ok) {
      setError(true);
    } else {
      setBusy(null);
    }
    setVersion((v) => v + 1);
    await onChange();
  };
  const minutes = (s: number) =>
    s < 60 ? t('review.lessThanMinute') : s < 3600 ? t('review.minutes', { count: Math.round(s / 60) }) : t('app.hours', { h: Math.floor(s / 3600), m: Math.round((s % 3600) / 60) });
  const left =
    item.left != null && item.left > 0
      ? t('app.left', { left: minutes(item.left), end: new Date(Date.now() + item.left * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' }) })
      : null;
  const status = {
    importing: t('app.state.importing'),
    court: item.searching ? t('app.state.searching') : t('app.state.court'),
    check: t('app.state.check'),
    running: [t('app.state.running'), job?.stage && t(`review.stage.${job.stage}`, { defaultValue: job.stage })].filter(Boolean).join(' · '),
    failed: t(job?.error === 'stopped' ? 'app.state.stopped' : 'app.state.failed', { step: t(`app.step.${job?.failed}`, { defaultValue: job?.failed }) }),
    elsewhere: t('app.state.elsewhere'),
  }[item.state];
  const fraction = job?.running ? (job.progress ?? null) : null;

  return (
    <Card className="h-full gap-3 px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {item.date && (
            <time dateTime={item.date} className="text-sm font-medium text-muted-foreground">
              {f.date(item.date)}
            </time>
          )}
          <h3 className="text-lg leading-snug font-semibold [overflow-wrap:anywhere]">{names ? t('matchTitle', { one: names[0], two: names[1] }) : item.name}</h3>
        </div>
        {!job?.running && item.state !== 'elsewhere' && (
          <Button variant="ghost" size="icon-sm" aria-label={t('app.delete')} onClick={() => setConfirm('delete')}>
            <Trash2 aria-hidden />
          </Button>
        )}
      </div>
      <p className={item.state === 'failed' ? 'text-destructive' : undefined}>{status}</p>
      {item.state === 'failed' && job?.error && !['stopped', 'interrupted'].includes(job.error) && <p className="text-xs [overflow-wrap:anywhere] text-muted-foreground">{job.error}</p>}
      {job?.running && (
        <div className="grid gap-1">
          <div
            role="progressbar"
            aria-label={status}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={fraction == null ? undefined : Math.round(fraction * 100)}
            className="h-2 overflow-hidden rounded-full bg-muted"
          >
            <div
              className={fraction == null ? 'h-full w-1/3 animate-pulse bg-primary/60' : 'h-full bg-primary transition-[width] duration-300'}
              style={fraction == null ? undefined : { width: `${fraction * 100}%` }}
            />
          </div>
          {left && <p className="text-xs text-muted-foreground tabular-nums">{left}</p>}
        </div>
      )}
      {item.state === 'check' && (
        <div className="grid gap-3 sm:grid-cols-2">
          {item.start && names && (
            <figure className="grid gap-1.5">
              <img src={imageUrl(item.name, 'start', version)} alt="" className="w-full rounded-md" />
              <figcaption className="grid gap-1.5 text-sm">
                {t('app.check.sides', { left: names[0], right: names[1] })}
                <Button size="sm" variant="outline" className="w-fit" onClick={() => void act('swap')}>
                  <ArrowLeftRight aria-hidden />
                  {t('app.check.swap')}
                </Button>
              </figcaption>
            </figure>
          )}
          {item.court && (
            <figure className="grid gap-1.5">
              <img src={imageUrl(item.name, 'court', version)} alt="" className="w-full rounded-md" />
              <figcaption className="grid gap-1.5 text-sm">
                {t('app.check.court')}
                <Button size="sm" variant="outline" className="w-fit" onClick={() => setPlacing(true)}>
                  <Crosshair aria-hidden />
                  {t('app.check.replace')}
                </Button>
              </figcaption>
            </figure>
          )}
        </div>
      )}
      {busy && (
        <p role="alert" className="text-sm">
          {t(busy.nice ? 'app.busyNice' : 'app.busy', { load: busy.load, cores: busy.cores })}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t('review.error')}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {item.state === 'court' && !item.searching && (
          <Button onClick={() => setPlacing(true)}>
            <Crosshair aria-hidden />
            {t('app.court.open')}
          </Button>
        )}
        {(item.state === 'check' || (item.state === 'failed' && job?.failed === 'pipeline')) && (
          <Button onClick={() => void act('run', { anyway: !!busy })}>
            {item.state === 'check' ? <Play aria-hidden /> : <RotateCcw aria-hidden />}
            {busy ? t('app.runAnyway') : item.state === 'check' ? t('app.run') : t('app.retry')}
          </Button>
        )}
        {item.state === 'failed' && job?.failed === 'court' && (
          <Button onClick={() => void act('court/auto')}>
            <RotateCcw aria-hidden />
            {t('app.retry')}
          </Button>
        )}
        {job?.running && (
          <Button variant="outline" onClick={() => setConfirm('stop')}>
            <Square aria-hidden />
            {t('app.stop')}
          </Button>
        )}
      </div>
      {placing && (
        <CourtDialog
          match={item.name}
          onClose={(placed) => {
            setPlacing(false);
            if (placed) {
              setVersion((v) => v + 1);
              void onChange();
            }
          }}
        />
      )}
      {confirm && (
        <Dialog open onOpenChange={(open) => !open && setConfirm(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t(confirm === 'stop' ? 'app.stopTitle' : 'app.deleteTitle')}</DialogTitle>
              <DialogDescription>{t(confirm === 'stop' ? 'app.stopText' : 'app.deleteText')}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirm(null)}>
                {t('app.cancel')}
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  setConfirm(null);
                  void (confirm === 'stop' ? act('stop', { id: item.name }) : act('delete'));
                }}
              >
                {t(confirm === 'stop' ? 'app.stop' : 'app.delete')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}
